# Copyright 2012 OpenStack Foundation
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

from sqlalchemy import schema

from glance.db.sqlalchemy.migrate_repo import schema as glance_schema


def define_image_tags_table(meta):
    # Load the images table so the foreign key can be set up properly
    schema.Table('images', meta, autoload=True)

    image_tags = schema.Table('image_tags',
                              meta,
                              schema.Column('id',
                                            glance_schema.Integer(),
                                            primary_key=True,
                                            nullable=False),
                              schema.Column('image_id',
                                            glance_schema.String(36),
                                            schema.ForeignKey('images.id'),
                                            nullable=False),
                              schema.Column('value',
                                            glance_schema.String(255),
                                            nullable=False),
                              schema.Column('created_at',
                                            glance_schema.DateTime(),
                                            nullable=False),
                              schema.Column('updated_at',
                                            glance_schema.DateTime()),
                              schema.Column('deleted_at',
                                            glance_schema.DateTime()),
                              schema.Column('deleted',
                                            glance_schema.Boolean(),
                                            nullable=False,
                                            default=False),
                              mysql_engine='InnoDB',
                              mysql_charset='utf8')

    schema.Index('ix_image_tags_image_id',
                 image_tags.c.image_id)

    schema.Index('ix_image_tags_image_id_tag_value',
                 image_tags.c.image_id,
                 image_tags.c.value)

    return image_tags


def upgrade(migrate_engine):
    meta = schema.MetaData()
    meta.bind = migrate_engine
    tables = [define_image_tags_table(meta)]
    glance_schema.create_tables(tables)


def downgrade(migrate_engine):
    meta = schema.MetaData()
    meta.bind = migrate_engine
    tables = [define_image_tags_table(meta)]
    glance_schema.drop_tables(tables)
