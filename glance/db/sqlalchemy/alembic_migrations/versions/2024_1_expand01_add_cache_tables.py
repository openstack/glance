# Copyright (C) 2023 RedHat Inc
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

"""adds cache_node_reference and cached_images table(s)

Revision ID: 2024_1_expand01
Revises: 2023_1_expand01
Create Date: 2023-10-31 11:55:16.657499

"""

from alembic import op
from sqlalchemy.schema import (
    Column, PrimaryKeyConstraint, ForeignKeyConstraint, UniqueConstraint)

from glance.db.sqlalchemy.schema import (
    Integer, BigInteger, DateTime, String)  # noqa

# revision identifiers, used by Alembic.
revision = '2024_1_expand01'
down_revision = '2023_1_expand01'
branch_labels = None
depends_on = None


def _add_node_reference_table():
    op.create_table('node_reference',
                    Column('node_reference_id',
                           BigInteger().with_variant(Integer, 'sqlite'),
                           nullable=False,
                           autoincrement=True),
                    Column('node_reference_url', String(length=255),
                           nullable=False),
                    PrimaryKeyConstraint('node_reference_id'),
                    UniqueConstraint(
                        'node_reference_url',
                        name='uq_node_reference_node_reference_url'),
                    mysql_engine='InnoDB',
                    mysql_charset='utf8',
                    extend_existing=True)


def _add_cached_images_table():
    op.create_table('cached_images',
                    Column('id', BigInteger().with_variant(Integer, 'sqlite'),
                           autoincrement=True,
                           nullable=False),
                    Column('image_id', String(length=36), nullable=False),
                    Column('last_accessed', DateTime(), nullable=False),
                    Column('last_modified', DateTime(), nullable=False),
                    Column('size', BigInteger(), nullable=False),
                    Column('hits', Integer(), nullable=False),
                    Column('checksum', String(length=32), nullable=True),
                    Column('node_reference_id',
                           BigInteger().with_variant(Integer, 'sqlite'),
                           nullable=False),
                    PrimaryKeyConstraint('id'),
                    ForeignKeyConstraint(
                        ['node_reference_id'],
                        ['node_reference.node_reference_id'], ),
                    UniqueConstraint(
                        'image_id',
                        'node_reference_id',
                        name='ix_cached_images_image_id_node_reference_id'),
                    mysql_engine='InnoDB',
                    mysql_charset='utf8',
                    extend_existing=True)


def upgrade():
    _add_node_reference_table()
    _add_cached_images_table()
