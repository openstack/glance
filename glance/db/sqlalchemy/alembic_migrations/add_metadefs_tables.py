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
    Column, PrimaryKeyConstraint, ForeignKeyConstraint, UniqueConstraint)

from glance.db.sqlalchemy.schema import (
    Boolean, DateTime, Integer, String, Text)  # noqa
from glance.db.sqlalchemy.models import JSONEncodedDict


def _add_metadef_namespaces_table():
    op.create_table('metadef_namespaces',
                    Column('id', Integer(), nullable=False),
                    Column('namespace', String(length=80), nullable=False),
                    Column('display_name', String(length=80), nullable=True),
                    Column('description', Text(), nullable=True),
                    Column('visibility', String(length=32), nullable=True),
                    Column('protected', Boolean(), nullable=True),
                    Column('owner', String(length=255), nullable=False),
                    Column('created_at', DateTime(), nullable=False),
                    Column('updated_at', DateTime(), nullable=True),
                    PrimaryKeyConstraint('id'),
                    UniqueConstraint('namespace',
                                     name='uq_metadef_namespaces_namespace'),
                    mysql_engine='InnoDB',
                    mysql_charset='utf8',
                    extend_existing=True)

    op.create_index('ix_metadef_namespaces_owner',
                    'metadef_namespaces',
                    ['owner'],
                    unique=False)


def _add_metadef_resource_types_table():
    op.create_table('metadef_resource_types',
                    Column('id', Integer(), nullable=False),
                    Column('name', String(length=80), nullable=False),
                    Column('protected', Boolean(), nullable=False),
                    Column('created_at', DateTime(), nullable=False),
                    Column('updated_at', DateTime(), nullable=True),
                    PrimaryKeyConstraint('id'),
                    UniqueConstraint('name',
                                     name='uq_metadef_resource_types_name'),
                    mysql_engine='InnoDB',
                    mysql_charset='utf8',
                    extend_existing=True)


def _add_metadef_namespace_resource_types_table():
    op.create_table('metadef_namespace_resource_types',
                    Column('resource_type_id', Integer(), nullable=False),
                    Column('namespace_id', Integer(), nullable=False),
                    Column('properties_target',
                           String(length=80),
                           nullable=True),
                    Column('prefix', String(length=80), nullable=True),
                    Column('created_at', DateTime(), nullable=False),
                    Column('updated_at', DateTime(), nullable=True),
                    ForeignKeyConstraint(['namespace_id'],
                                         ['metadef_namespaces.id'], ),
                    ForeignKeyConstraint(['resource_type_id'],
                                         ['metadef_resource_types.id'], ),
                    PrimaryKeyConstraint('resource_type_id', 'namespace_id'),
                    mysql_engine='InnoDB',
                    mysql_charset='utf8',
                    extend_existing=True)

    op.create_index('ix_metadef_ns_res_types_namespace_id',
                    'metadef_namespace_resource_types',
                    ['namespace_id'],
                    unique=False)


def _add_metadef_objects_table():
    ns_id_name_constraint = 'uq_metadef_objects_namespace_id_name'

    op.create_table('metadef_objects',
                    Column('id', Integer(), nullable=False),
                    Column('namespace_id', Integer(), nullable=False),
                    Column('name', String(length=80), nullable=False),
                    Column('description', Text(), nullable=True),
                    Column('required', Text(), nullable=True),
                    Column('json_schema', JSONEncodedDict(), nullable=False),
                    Column('created_at', DateTime(), nullable=False),
                    Column('updated_at', DateTime(), nullable=True),
                    ForeignKeyConstraint(['namespace_id'],
                                         ['metadef_namespaces.id'], ),
                    PrimaryKeyConstraint('id'),
                    UniqueConstraint('namespace_id',
                                     'name',
                                     name=ns_id_name_constraint),
                    mysql_engine='InnoDB',
                    mysql_charset='utf8',
                    extend_existing=True)

    op.create_index('ix_metadef_objects_name',
                    'metadef_objects',
                    ['name'],
                    unique=False)


def _add_metadef_properties_table():
    ns_id_name_constraint = 'uq_metadef_properties_namespace_id_name'
    op.create_table('metadef_properties',
                    Column('id', Integer(), nullable=False),
                    Column('namespace_id', Integer(), nullable=False),
                    Column('name', String(length=80), nullable=False),
                    Column('json_schema', JSONEncodedDict(), nullable=False),
                    Column('created_at', DateTime(), nullable=False),
                    Column('updated_at', DateTime(), nullable=True),
                    ForeignKeyConstraint(['namespace_id'],
                                         ['metadef_namespaces.id'], ),
                    PrimaryKeyConstraint('id'),
                    UniqueConstraint('namespace_id',
                                     'name',
                                     name=ns_id_name_constraint),
                    mysql_engine='InnoDB',
                    mysql_charset='utf8',
                    extend_existing=True)

    op.create_index('ix_metadef_properties_name',
                    'metadef_properties',
                    ['name'],
                    unique=False)


def _add_metadef_tags_table():
    op.create_table('metadef_tags',
                    Column('id', Integer(), nullable=False),
                    Column('namespace_id', Integer(), nullable=False),
                    Column('name', String(length=80), nullable=False),
                    Column('created_at', DateTime(), nullable=False),
                    Column('updated_at', DateTime(), nullable=True),
                    ForeignKeyConstraint(['namespace_id'],
                                         ['metadef_namespaces.id'], ),
                    PrimaryKeyConstraint('id'),
                    UniqueConstraint('namespace_id',
                                     'name',
                                     name='uq_metadef_tags_namespace_id_name'),
                    mysql_engine='InnoDB',
                    mysql_charset='utf8',
                    extend_existing=True)

    op.create_index('ix_metadef_tags_name',
                    'metadef_tags',
                    ['name'],
                    unique=False)


def upgrade():
    _add_metadef_namespaces_table()
    _add_metadef_resource_types_table()
    _add_metadef_namespace_resource_types_table()
    _add_metadef_objects_table()
    _add_metadef_properties_table()
    _add_metadef_tags_table()
