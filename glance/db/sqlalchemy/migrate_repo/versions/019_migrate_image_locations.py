# Copyright 2013 OpenStack Foundation
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


def get_images_table(meta):
    return sqlalchemy.Table('images', meta, autoload=True)


def get_image_locations_table(meta):
    return sqlalchemy.Table('image_locations', meta, autoload=True)


def upgrade(migrate_engine):
    meta = sqlalchemy.schema.MetaData(migrate_engine)

    images_table = get_images_table(meta)
    image_locations_table = get_image_locations_table(meta)

    image_records = images_table.select().execute().fetchall()
    for image in image_records:
        if image.location is not None:
            values = {
                'image_id': image.id,
                'value': image.location,
                'created_at': image.created_at,
                'updated_at': image.updated_at,
                'deleted': image.deleted,
                'deleted_at': image.deleted_at,
            }
            image_locations_table.insert(values=values).execute()
