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
from sqlalchemy.schema import (
    Column, PrimaryKeyConstraint, ForeignKeyConstraint)

from glance.db.sqlalchemy.schema import (
    Boolean, DateTime, Integer, BigInteger, String, Text, Numeric)  # noqa


def _add_artifacts_table():
    op.create_table('artifacts',
                    Column('id', String(length=36), nullable=False),
                    Column('name', String(length=255), nullable=False),
                    Column('type_name', String(length=255), nullable=False),
                    Column('type_version_prefix',
                           BigInteger(),
                           nullable=False),
                    Column('type_version_suffix',
                           String(length=255),
                           nullable=True),
                    Column('type_version_meta',
                           String(length=255),
                           nullable=True),
                    Column('version_prefix', BigInteger(), nullable=False),
                    Column('version_suffix',
                           String(length=255),
                           nullable=True),
                    Column('version_meta', String(length=255), nullable=True),
                    Column('description', Text(), nullable=True),
                    Column('visibility', String(length=32), nullable=False),
                    Column('state', String(length=32), nullable=False),
                    Column('owner', String(length=255), nullable=False),
                    Column('created_at', DateTime(), nullable=False),
                    Column('updated_at', DateTime(), nullable=False),
                    Column('deleted_at', DateTime(), nullable=True),
                    Column('published_at', DateTime(), nullable=True),
                    PrimaryKeyConstraint('id'),
                    mysql_engine='InnoDB',
                    mysql_charset='utf8',
                    extend_existing=True)

    op.create_index('ix_artifact_name_and_version',
                    'artifacts',
                    ['name', 'version_prefix', 'version_suffix'],
                    unique=False)
    op.create_index('ix_artifact_owner', 'artifacts', ['owner'], unique=False)
    op.create_index('ix_artifact_state', 'artifacts', ['state'], unique=False)
    op.create_index('ix_artifact_type',
                    'artifacts',
                    ['type_name',
                     'type_version_prefix',
                     'type_version_suffix'],
                    unique=False)
    op.create_index('ix_artifact_visibility',
                    'artifacts',
                    ['visibility'],
                    unique=False)


def _add_artifact_blobs_table():
    op.create_table('artifact_blobs',
                    Column('id', String(length=36), nullable=False),
                    Column('artifact_id', String(length=36), nullable=False),
                    Column('size', BigInteger(), nullable=False),
                    Column('checksum', String(length=32), nullable=True),
                    Column('name', String(length=255), nullable=False),
                    Column('item_key', String(length=329), nullable=True),
                    Column('position', Integer(), nullable=True),
                    Column('created_at', DateTime(), nullable=False),
                    Column('updated_at', DateTime(), nullable=False),
                    ForeignKeyConstraint(['artifact_id'], ['artifacts.id'], ),
                    PrimaryKeyConstraint('id'),
                    mysql_engine='InnoDB',
                    mysql_charset='utf8',
                    extend_existing=True)

    op.create_index('ix_artifact_blobs_artifact_id',
                    'artifact_blobs',
                    ['artifact_id'],
                    unique=False)
    op.create_index('ix_artifact_blobs_name',
                    'artifact_blobs',
                    ['name'],
                    unique=False)


def _add_artifact_dependencies_table():
    op.create_table('artifact_dependencies',
                    Column('id', String(length=36), nullable=False),
                    Column('artifact_source',
                           String(length=36),
                           nullable=False),
                    Column('artifact_dest', String(length=36), nullable=False),
                    Column('artifact_origin',
                           String(length=36),
                           nullable=False),
                    Column('is_direct', Boolean(), nullable=False),
                    Column('position', Integer(), nullable=True),
                    Column('name', String(length=36), nullable=True),
                    Column('created_at', DateTime(), nullable=False),
                    Column('updated_at', DateTime(), nullable=False),
                    ForeignKeyConstraint(['artifact_dest'],
                                         ['artifacts.id'], ),
                    ForeignKeyConstraint(['artifact_origin'],
                                         ['artifacts.id'], ),
                    ForeignKeyConstraint(['artifact_source'],
                                         ['artifacts.id'], ),
                    PrimaryKeyConstraint('id'),
                    mysql_engine='InnoDB',
                    mysql_charset='utf8',
                    extend_existing=True)

    op.create_index('ix_artifact_dependencies_dest_id',
                    'artifact_dependencies',
                    ['artifact_dest'],
                    unique=False)
    op.create_index('ix_artifact_dependencies_direct_dependencies',
                    'artifact_dependencies',
                    ['artifact_source', 'is_direct'],
                    unique=False)
    op.create_index('ix_artifact_dependencies_origin_id',
                    'artifact_dependencies',
                    ['artifact_origin'],
                    unique=False)
    op.create_index('ix_artifact_dependencies_source_id',
                    'artifact_dependencies',
                    ['artifact_source'],
                    unique=False)


def _add_artifact_properties_table():
    op.create_table('artifact_properties',
                    Column('id', String(length=36), nullable=False),
                    Column('artifact_id', String(length=36), nullable=False),
                    Column('name', String(length=255), nullable=False),
                    Column('string_value', String(length=255), nullable=True),
                    Column('int_value', Integer(), nullable=True),
                    Column('numeric_value', Numeric(), nullable=True),
                    Column('bool_value', Boolean(), nullable=True),
                    Column('text_value', Text(), nullable=True),
                    Column('created_at', DateTime(), nullable=False),
                    Column('updated_at', DateTime(), nullable=False),
                    Column('position', Integer(), nullable=True),
                    ForeignKeyConstraint(['artifact_id'], ['artifacts.id'], ),
                    PrimaryKeyConstraint('id'),
                    mysql_engine='InnoDB',
                    mysql_charset='utf8',
                    extend_existing=True)

    op.create_index('ix_artifact_properties_artifact_id',
                    'artifact_properties',
                    ['artifact_id'],
                    unique=False)
    op.create_index('ix_artifact_properties_name',
                    'artifact_properties',
                    ['name'],
                    unique=False)


def _add_artifact_tags_table():
    op.create_table('artifact_tags',
                    Column('id', String(length=36), nullable=False),
                    Column('artifact_id', String(length=36), nullable=False),
                    Column('value', String(length=255), nullable=False),
                    Column('created_at', DateTime(), nullable=False),
                    Column('updated_at', DateTime(), nullable=False),
                    ForeignKeyConstraint(['artifact_id'], ['artifacts.id'], ),
                    PrimaryKeyConstraint('id'),
                    mysql_engine='InnoDB',
                    mysql_charset='utf8',
                    extend_existing=True)

    op.create_index('ix_artifact_tags_artifact_id',
                    'artifact_tags',
                    ['artifact_id'],
                    unique=False)
    op.create_index('ix_artifact_tags_artifact_id_tag_value',
                    'artifact_tags',
                    ['artifact_id', 'value'],
                    unique=False)


def _add_artifact_blob_locations_table():
    op.create_table('artifact_blob_locations',
                    Column('id', String(length=36), nullable=False),
                    Column('blob_id', String(length=36), nullable=False),
                    Column('value', Text(), nullable=False),
                    Column('created_at', DateTime(), nullable=False),
                    Column('updated_at', DateTime(), nullable=False),
                    Column('position', Integer(), nullable=True),
                    Column('status', String(length=36), nullable=True),
                    ForeignKeyConstraint(['blob_id'], ['artifact_blobs.id'], ),
                    PrimaryKeyConstraint('id'),
                    mysql_engine='InnoDB',
                    mysql_charset='utf8',
                    extend_existing=True)

    op.create_index('ix_artifact_blob_locations_blob_id',
                    'artifact_blob_locations',
                    ['blob_id'],
                    unique=False)


def upgrade():
    _add_artifacts_table()
    _add_artifact_blobs_table()
    _add_artifact_dependencies_table()
    _add_artifact_properties_table()
    _add_artifact_tags_table()
    _add_artifact_blob_locations_table()
