# Copyright 2013 Rackspace Hosting
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

import pickle

import sqlalchemy
from sqlalchemy import Table, Column  # noqa
from glance.db.sqlalchemy import models


def upgrade(migrate_engine):
    meta = sqlalchemy.schema.MetaData(migrate_engine)
    image_locations = Table('image_locations', meta, autoload=True)
    new_meta_data = Column('storage_meta_data', models.JSONEncodedDict,
                           default={})
    new_meta_data.create(image_locations)

    noe = pickle.dumps({})
    s = sqlalchemy.sql.select([image_locations]).where(
        image_locations.c.meta_data != noe)
    conn = migrate_engine.connect()
    res = conn.execute(s)

    for row in res:
        meta_data = row['meta_data']
        x = pickle.loads(meta_data)
        if x != {}:
            stmt = image_locations.update().where(
                image_locations.c.id == row['id']).values(storage_meta_data=x)
            conn.execute(stmt)
    conn.close()
    image_locations.columns['meta_data'].drop()
    image_locations.columns['storage_meta_data'].alter(name='meta_data')
