# Copyright 2013 Red Hat, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import re

from migrate.changeset import UniqueConstraint
from oslo_db import exception as db_exception
from sqlalchemy import and_, func, orm
from sqlalchemy import MetaData, Table
from sqlalchemy.exc import OperationalError, ProgrammingError


NEW_KEYNAME = 'image_members_image_id_member_deleted_at_key'
ORIGINAL_KEYNAME_RE = re.compile('image_members_image_id.*_key')


def upgrade(migrate_engine):
    image_members = _get_image_members_table(migrate_engine)

    if migrate_engine.name in ('mysql', 'postgresql'):
        try:
            UniqueConstraint('image_id',
                             name=_get_original_keyname(migrate_engine.name),
                             table=image_members).drop()
        except (OperationalError, ProgrammingError, db_exception.DBError):
            UniqueConstraint('image_id',
                             name=_infer_original_keyname(image_members),
                             table=image_members).drop()
        UniqueConstraint('image_id',
                         'member',
                         'deleted_at',
                         name=NEW_KEYNAME,
                         table=image_members).create()


def downgrade(migrate_engine):
    image_members = _get_image_members_table(migrate_engine)

    if migrate_engine.name in ('mysql', 'postgresql'):
        _sanitize(migrate_engine, image_members)
        UniqueConstraint('image_id',
                         name=NEW_KEYNAME,
                         table=image_members).drop()
        UniqueConstraint('image_id',
                         'member',
                         name=_get_original_keyname(migrate_engine.name),
                         table=image_members).create()


def _get_image_members_table(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine
    return Table('image_members', meta, autoload=True)


def _get_original_keyname(db):
    return {'mysql': 'image_id',
            'postgresql': 'image_members_image_id_member_key'}[db]


def _infer_original_keyname(table):
    for i in table.indexes:
        if ORIGINAL_KEYNAME_RE.match(i.name):
            return i.name


def _sanitize(migrate_engine, table):
    """
    Avoid possible integrity error by removing deleted rows
    to accommodate less restrictive uniqueness constraint
    """
    session = orm.sessionmaker(bind=migrate_engine)()
    # find the image_member rows containing duplicate combinations
    # of image_id and member
    qry = (session.query(table.c.image_id, table.c.member)
                  .group_by(table.c.image_id, table.c.member)
                  .having(func.count() > 1))
    for image_id, member in qry:
        # only remove duplicate rows already marked deleted
        d = table.delete().where(and_(table.c.deleted == True,
                                      table.c.image_id == image_id,
                                      table.c.member == member))
        d.execute()
    session.close()
