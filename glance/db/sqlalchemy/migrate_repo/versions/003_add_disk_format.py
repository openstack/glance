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

from sqlalchemy import Column, MetaData, Table, and_, select

from glance.db.sqlalchemy.migrate_repo.schema import (
    Boolean, DateTime, Integer, String, Text, from_migration_import)  # noqa


def get_images_table(meta):
    """
    Returns the Table object for the images table that
    corresponds to the images table definition of this version.
    """
    images = Table('images',
                   meta,
                   Column('id', Integer(), primary_key=True, nullable=False),
                   Column('name', String(255)),
                   Column('disk_format', String(20)),
                   Column('container_format', String(20)),
                   Column('size', Integer()),
                   Column('status', String(30), nullable=False),
                   Column('is_public',
                          Boolean(),
                          nullable=False,
                          default=False,
                          index=True),
                   Column('location', Text()),
                   Column('created_at', DateTime(), nullable=False),
                   Column('updated_at', DateTime()),
                   Column('deleted_at', DateTime()),
                   Column('deleted',
                          Boolean(),
                          nullable=False,
                          default=False,
                          index=True),
                   mysql_engine='InnoDB',
                   extend_existing=True)

    return images


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine
    (define_images_table,) = from_migration_import(
        '001_add_images_table', ['define_images_table'])
    (define_image_properties_table,) = from_migration_import(
        '002_add_image_properties_table', ['define_image_properties_table'])

    conn = migrate_engine.connect()
    images = define_images_table(meta)
    image_properties = define_image_properties_table(meta)

    # Steps to take, in this order:
    # 1) Move the existing type column from Image into
    #    ImageProperty for all image records that have a non-NULL
    #    type column
    # 2) Drop the type column in images
    # 3) Add the new columns to images

    # The below wackiness correlates to the following ANSI SQL:
    #   SELECT images.* FROM images
    #   LEFT JOIN image_properties
    #   ON images.id = image_properties.image_id
    #   AND image_properties.key = 'type'
    #   WHERE image_properties.image_id IS NULL
    #   AND images.type IS NOT NULL
    #
    # which returns all the images that have a type set
    # but that DO NOT yet have an image_property record
    # with key of type.
    from_stmt = [
        images.outerjoin(image_properties,
                         and_(images.c.id == image_properties.c.image_id,
                              image_properties.c.key == 'type'))
    ]
    and_stmt = and_(image_properties.c.image_id == None,
                    images.c.type != None)
    sel = select([images], from_obj=from_stmt).where(and_stmt)
    image_records = conn.execute(sel).fetchall()
    property_insert = image_properties.insert()
    for record in image_records:
        conn.execute(property_insert,
                     image_id=record.id,
                     key='type',
                     created_at=record.created_at,
                     deleted=False,
                     value=record.type)
    conn.close()

    disk_format = Column('disk_format', String(20))
    disk_format.create(images)
    container_format = Column('container_format', String(20))
    container_format.create(images)

    images.columns['type'].drop()
