#    Copyright 2014 IBM Corp.
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

import six
import sqlalchemy

from glance.db.sqlalchemy.migrate_repo import schema


def upgrade(migrate_engine):
    meta = sqlalchemy.schema.MetaData()
    meta.bind = migrate_engine

    images_table = sqlalchemy.Table('images', meta, autoload=True)
    image_locations_table = sqlalchemy.Table('image_locations', meta,
                                             autoload=True)

    # Create 'status' column for image_locations table
    status = sqlalchemy.Column('status', schema.String(30),
                               server_default='active', nullable=False)
    status.create(image_locations_table)

    # Set 'status' column initial value for image_locations table
    mapping = {'active': 'active', 'pending_delete': 'pending_delete',
               'deleted': 'deleted', 'killed': 'deleted'}
    for src, dst in six.iteritems(mapping):
        subq = sqlalchemy.sql.select([images_table.c.id]).where(
            images_table.c.status == src)
        image_locations_table.update(values={'status': dst}).where(
            image_locations_table.c.image_id.in_(subq)).execute()
