# Copyright 2011 OpenStack Foundation
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

from sqlalchemy import Index, MetaData

from glance.db.sqlalchemy.migrate_repo.schema import from_migration_import


def get_images_table(meta):
    """
    No changes to the image properties table from 002...
    """
    (get_images_table,) = from_migration_import(
        '004_add_checksum', ['get_images_table'])

    images = get_images_table(meta)
    return images


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    (get_image_properties_table,) = from_migration_import(
        '004_add_checksum', ['get_image_properties_table'])
    image_properties = get_image_properties_table(meta)

    if migrate_engine.name == "ibm_db_sa":
        # NOTE(dperaza) ibm db2 does not allow ALTER INDEX so we will drop
        # the index, rename the column, then re-create the index
        sql_commands = [
            """ALTER TABLE image_properties DROP UNIQUE
                ix_image_properties_image_id_key;""",
            """ALTER TABLE image_properties RENAME COLUMN \"key\" to name;""",
            """ALTER TABLE image_properties ADD CONSTRAINT
                ix_image_properties_image_id_name UNIQUE(image_id, name);""",
        ]
        for command in sql_commands:
            meta.bind.execute(command)
    else:
        index = Index('ix_image_properties_image_id_key',
                      image_properties.c.image_id,
                      image_properties.c.key)
        index.rename('ix_image_properties_image_id_name')

        image_properties = get_image_properties_table(meta)
        image_properties.columns['key'].alter(name="name")
