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
