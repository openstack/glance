# Copyright 2016 Rackspace
# Copyright 2013 Intel Corporation
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

from alembic import op
from sqlalchemy import sql
from sqlalchemy.schema import (
    Column, PrimaryKeyConstraint, ForeignKeyConstraint, UniqueConstraint)

from glance.db.sqlalchemy.schema import (
    Boolean, DateTime, Integer, BigInteger, String, Text)  # noqa
from glance.db.sqlalchemy.models import JSONEncodedDict


def _add_images_table():
    op.create_table('images',
                    Column('id', String(length=36), nullable=False),
                    Column('name', String(length=255), nullable=True),
                    Column('size',
                           BigInteger().with_variant(Integer, "sqlite"),
                           nullable=True),
                    Column('status', String(length=30), nullable=False),
                    Column('is_public', Boolean(), nullable=False),
                    Column('created_at', DateTime(), nullable=False),
                    Column('updated_at', DateTime(), nullable=True),
                    Column('deleted_at', DateTime(), nullable=True),
                    Column('deleted', Boolean(), nullable=False),
                    Column('disk_format', String(length=20), nullable=True),
                    Column('container_format',
                           String(length=20),
                           nullable=True),
                    Column('checksum', String(length=32), nullable=True),
                    Column('owner', String(length=255), nullable=True),
                    Column('min_disk', Integer(), nullable=False),
                    Column('min_ram', Integer(), nullable=False),
                    Column('protected',
                           Boolean(),
                           server_default=sql.false(),
                           nullable=False),
                    Column('virtual_size',
                           BigInteger().with_variant(Integer, "sqlite"),
                           nullable=True),
                    PrimaryKeyConstraint('id'),
                    mysql_engine='InnoDB',
                    mysql_charset='utf8',
                    extend_existing=True)

    op.create_index('checksum_image_idx',
                    'images',
                    ['checksum'],
                    unique=False)
    op.create_index('ix_images_deleted',
                    'images',
                    ['deleted'],
                    unique=False)
    op.create_index('ix_images_is_public',
                    'images',
                    ['is_public'],
                    unique=False)
    op.create_index('owner_image_idx',
                    'images',
                    ['owner'],
                    unique=False)


def _add_image_properties_table():
    op.create_table('image_properties',
                    Column('id', Integer(), nullable=False),
                    Column('image_id', String(length=36), nullable=False),
                    Column('name', String(length=255), nullable=False),
                    Column('value', Text(), nullable=True),
                    Column('created_at', DateTime(), nullable=False),
                    Column('updated_at', DateTime(), nullable=True),
                    Column('deleted_at', DateTime(), nullable=True),
                    Column('deleted', Boolean(), nullable=False),
                    PrimaryKeyConstraint('id'),
                    ForeignKeyConstraint(['image_id'], ['images.id'], ),
                    UniqueConstraint('image_id',
                                     'name',
                                     name='ix_image_properties_image_id_name'),
                    mysql_engine='InnoDB',
                    mysql_charset='utf8',
                    extend_existing=True)

    op.create_index('ix_image_properties_deleted',
                    'image_properties',
                    ['deleted'],
                    unique=False)
    op.create_index('ix_image_properties_image_id',
                    'image_properties',
                    ['image_id'],
                    unique=False)


def _add_image_locations_table():
    op.create_table('image_locations',
                    Column('id', Integer(), nullable=False),
                    Column('image_id', String(length=36), nullable=False),
                    Column('value', Text(), nullable=False),
                    Column('created_at', DateTime(), nullable=False),
                    Column('updated_at', DateTime(), nullable=True),
                    Column('deleted_at', DateTime(), nullable=True),
                    Column('deleted', Boolean(), nullable=False),
                    Column('meta_data', JSONEncodedDict(), nullable=True),
                    Column('status',
                           String(length=30),
                           server_default='active',
                           nullable=False),
                    PrimaryKeyConstraint('id'),
                    ForeignKeyConstraint(['image_id'], ['images.id'], ),
                    mysql_engine='InnoDB',
                    mysql_charset='utf8',
                    extend_existing=True)

    op.create_index('ix_image_locations_deleted',
                    'image_locations',
                    ['deleted'],
                    unique=False)
    op.create_index('ix_image_locations_image_id',
                    'image_locations',
                    ['image_id'],
                    unique=False)


def _add_image_members_table():
    deleted_member_constraint = 'image_members_image_id_member_deleted_at_key'
    op.create_table('image_members',
                    Column('id', Integer(), nullable=False),
                    Column('image_id', String(length=36), nullable=False),
                    Column('member', String(length=255), nullable=False),
                    Column('can_share', Boolean(), nullable=False),
                    Column('created_at', DateTime(), nullable=False),
                    Column('updated_at', DateTime(), nullable=True),
                    Column('deleted_at', DateTime(), nullable=True),
                    Column('deleted', Boolean(), nullable=False),
                    Column('status',
                           String(length=20),
                           server_default='pending',
                           nullable=False),
                    ForeignKeyConstraint(['image_id'], ['images.id'], ),
                    PrimaryKeyConstraint('id'),
                    UniqueConstraint('image_id',
                                     'member',
                                     'deleted_at',
                                     name=deleted_member_constraint),
                    mysql_engine='InnoDB',
                    mysql_charset='utf8',
                    extend_existing=True)

    op.create_index('ix_image_members_deleted',
                    'image_members',
                    ['deleted'],
                    unique=False)
    op.create_index('ix_image_members_image_id',
                    'image_members',
                    ['image_id'],
                    unique=False)
    op.create_index('ix_image_members_image_id_member',
                    'image_members',
                    ['image_id', 'member'],
                    unique=False)


def _add_images_tags_table():
    op.create_table('image_tags',
                    Column('id', Integer(), nullable=False),
                    Column('image_id', String(length=36), nullable=False),
                    Column('value', String(length=255), nullable=False),
                    Column('created_at', DateTime(), nullable=False),
                    Column('updated_at', DateTime(), nullable=True),
                    Column('deleted_at', DateTime(), nullable=True),
                    Column('deleted', Boolean(), nullable=False),
                    ForeignKeyConstraint(['image_id'], ['images.id'], ),
                    PrimaryKeyConstraint('id'),
                    mysql_engine='InnoDB',
                    mysql_charset='utf8',
                    extend_existing=True)

    op.create_index('ix_image_tags_image_id',
                    'image_tags',
                    ['image_id'],
                    unique=False)
    op.create_index('ix_image_tags_image_id_tag_value',
                    'image_tags',
                    ['image_id', 'value'],
                    unique=False)


def upgrade():
    _add_images_table()
    _add_image_properties_table()
    _add_image_locations_table()
    _add_image_members_table()
    _add_images_tags_table()
