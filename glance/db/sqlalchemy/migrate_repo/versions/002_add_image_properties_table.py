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

from sqlalchemy.schema import (
    Column, ForeignKey, Index, MetaData, Table, UniqueConstraint)

from glance.db.sqlalchemy.migrate_repo.schema import (
    Boolean, DateTime, Integer, String, Text, create_tables,
    from_migration_import)  # noqa


def define_image_properties_table(meta):
    (define_images_table,) = from_migration_import(
        '001_add_images_table', ['define_images_table'])

    images = define_images_table(meta)  # noqa

    # NOTE(dperaza) DB2: specify the UniqueConstraint option when creating the
    # table will cause an index being created to specify the index
    # name and skip the step of creating another index with the same columns.
    # The index name is needed so it can be dropped and re-created later on.

    constr_kwargs = {}
    if meta.bind.name == 'ibm_db_sa':
        constr_kwargs['name'] = 'ix_image_properties_image_id_key'

    image_properties = Table('image_properties',
                             meta,
                             Column('id',
                                    Integer(),
                                    primary_key=True,
                                    nullable=False),
                             Column('image_id',
                                    Integer(),
                                    ForeignKey('images.id'),
                                    nullable=False,
                                    index=True),
                             Column('key', String(255), nullable=False),
                             Column('value', Text()),
                             Column('created_at', DateTime(), nullable=False),
                             Column('updated_at', DateTime()),
                             Column('deleted_at', DateTime()),
                             Column('deleted',
                                    Boolean(),
                                    nullable=False,
                                    default=False,
                                    index=True),
                             UniqueConstraint('image_id', 'key',
                                              **constr_kwargs),
                             mysql_engine='InnoDB',
                             mysql_charset='utf8',
                             extend_existing=True)

    if meta.bind.name != 'ibm_db_sa':
        Index('ix_image_properties_image_id_key',
              image_properties.c.image_id,
              image_properties.c.key)

    return image_properties


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine
    tables = [define_image_properties_table(meta)]
    create_tables(tables)
