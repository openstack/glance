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

from migrate.changeset import *  # noqa
from sqlalchemy import *  # noqa

from glance.db.sqlalchemy.migrate_repo.schema import from_migration_import


def get_images_table(meta):
    """
    No changes to the images table from 008...
    """
    (get_images_table,) = from_migration_import(
        '008_add_image_members_table', ['get_images_table'])

    images = get_images_table(meta)
    return images


def get_image_properties_table(meta):
    """
    No changes to the image properties table from 008...
    """
    (get_image_properties_table,) = from_migration_import(
        '008_add_image_members_table', ['get_image_properties_table'])

    image_properties = get_image_properties_table(meta)
    return image_properties


def get_image_members_table(meta):
    """
    No changes to the image members table from 008...
    """
    (get_image_members_table,) = from_migration_import(
        '008_add_image_members_table', ['get_image_members_table'])

    images = get_image_members_table(meta)
    return images


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    images_table = get_images_table(meta)

    # set updated_at to created_at if equal to None
    conn = migrate_engine.connect()
    conn.execute(
        images_table.update(
            images_table.c.updated_at == None,
            {images_table.c.updated_at: images_table.c.created_at}))


def downgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    images_table = get_images_table(meta)

    # set updated_at to None if equal to created_at
    conn = migrate_engine.connect()
    conn.execute(
        images_table.update(
            images_table.c.updated_at == images_table.c.created_at,
            {images_table.c.updated_at: None}))
