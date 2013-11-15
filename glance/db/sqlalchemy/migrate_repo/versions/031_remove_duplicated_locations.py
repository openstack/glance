# vim: tabstop=4 shiftwidth=4 softtabstop=4

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

import sqlalchemy
from sqlalchemy import func
from sqlalchemy import orm
from sqlalchemy import Table


def upgrade(migrate_engine):
    meta = sqlalchemy.schema.MetaData(migrate_engine)
    image_locations = Table('image_locations', meta, autoload=True)

    session = orm.sessionmaker(bind=migrate_engine)()

    # NOTE(flaper87): Lets group by
    # image_id, location and metadata.
    grp = [image_locations.c.image_id,
           image_locations.c.value,
           image_locations.c.meta_data]

    # NOTE(flaper87): Get all duplicated rows
    qry = (session.query(*grp)
                  .filter(image_locations.c.deleted == False)
                  .group_by(*grp)
                  .having(func.count() > 1))

    for row in qry:
        # NOTE(flaper87): Not the fastest way to do it.
        # This is the best way to do it since sqlalchemy
        # has a bug around delete + limit.
        s = (sqlalchemy.sql.select([image_locations.c.id])
             .where(image_locations.c.image_id == row[0])
             .where(image_locations.c.value == row[1])
             .where(image_locations.c.meta_data == row[2])
             .where(image_locations.c.deleted == False)
             .limit(1).execute())
        stmt = (image_locations.delete()
                .where(image_locations.c.id == s.first()[0]))
        stmt.execute()

    session.close()


def downgrade(migrate_engine):
    # NOTE(flaper87): There's no downgrade
    # path for this.
    return
