# Copyright (c) 2014 Hewlett-Packard Development Company, L.P.
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
from sqlalchemy.schema import (
    Column, ForeignKey, Index, MetaData, Table, UniqueConstraint)  # noqa

from glance.common import timeutils
from glance.db.sqlalchemy.migrate_repo.schema import (
    Boolean, DateTime, Integer, String, Text, create_tables)  # noqa


RESOURCE_TYPES = [u'OS::Glance::Image', u'OS::Cinder::Volume',
                  u'OS::Nova::Flavor', u'OS::Nova::Aggregate',
                  u'OS::Nova::Server']


def _get_metadef_resource_types_table(meta):
    return sqlalchemy.Table('metadef_resource_types', meta, autoload=True)


def _populate_resource_types(resource_types_table):
    now = timeutils.utcnow()
    for resource_type in RESOURCE_TYPES:
        values = {
            'name': resource_type,
            'protected': True,
            'created_at': now,
            'updated_at': now
        }
        resource_types_table.insert(values=values).execute()


def define_metadef_namespaces_table(meta):

    # NOTE: For DB2 if UniqueConstraint is used when creating a table
    # an index will automatically be created. So, for DB2 specify the
    # index name up front. If not DB2 then create the Index.
    _constr_kwargs = {}
    if meta.bind.name == 'ibm_db_sa':
        _constr_kwargs['name'] = 'ix_namespaces_namespace'

    namespaces = Table('metadef_namespaces',
                       meta,
                       Column('id', Integer(), primary_key=True,
                              nullable=False),
                       Column('namespace', String(80), nullable=False),
                       Column('display_name', String(80)),
                       Column('description', Text()),
                       Column('visibility', String(32)),
                       Column('protected', Boolean()),
                       Column('owner', String(255), nullable=False),
                       Column('created_at', DateTime(), nullable=False),
                       Column('updated_at', DateTime()),
                       UniqueConstraint('namespace', **_constr_kwargs),
                       mysql_engine='InnoDB',
                       mysql_charset='utf8',
                       extend_existing=True)

    if meta.bind.name != 'ibm_db_sa':
        Index('ix_namespaces_namespace', namespaces.c.namespace)

    return namespaces


def define_metadef_objects_table(meta):

    _constr_kwargs = {}
    if meta.bind.name == 'ibm_db_sa':
        _constr_kwargs['name'] = 'ix_objects_namespace_id_name'

    objects = Table('metadef_objects',
                    meta,
                    Column('id', Integer(), primary_key=True, nullable=False),
                    Column('namespace_id', Integer(),
                           ForeignKey('metadef_namespaces.id'),
                           nullable=False),
                    Column('name', String(80), nullable=False),
                    Column('description', Text()),
                    Column('required', Text()),
                    Column('schema', Text(), nullable=False),
                    Column('created_at', DateTime(), nullable=False),
                    Column('updated_at', DateTime()),
                    UniqueConstraint('namespace_id', 'name',
                                     **_constr_kwargs),
                    mysql_engine='InnoDB',
                    mysql_charset='utf8',
                    extend_existing=True)

    if meta.bind.name != 'ibm_db_sa':
        Index('ix_objects_namespace_id_name',
              objects.c.namespace_id,
              objects.c.name)

    return objects


def define_metadef_properties_table(meta):

    _constr_kwargs = {}
    if meta.bind.name == 'ibm_db_sa':
        _constr_kwargs['name'] = 'ix_metadef_properties_namespace_id_name'

    metadef_properties = Table(
        'metadef_properties',
        meta,
        Column('id', Integer(), primary_key=True, nullable=False),
        Column('namespace_id', Integer(), ForeignKey('metadef_namespaces.id'),
               nullable=False),
        Column('name', String(80), nullable=False),
        Column('schema', Text(), nullable=False),
        Column('created_at', DateTime(), nullable=False),
        Column('updated_at', DateTime()),
        UniqueConstraint('namespace_id', 'name', **_constr_kwargs),
        mysql_engine='InnoDB',
        mysql_charset='utf8',
        extend_existing=True)

    if meta.bind.name != 'ibm_db_sa':
        Index('ix_metadef_properties_namespace_id_name',
              metadef_properties.c.namespace_id,
              metadef_properties.c.name)

    return metadef_properties


def define_metadef_resource_types_table(meta):

    _constr_kwargs = {}
    if meta.bind.name == 'ibm_db_sa':
        _constr_kwargs['name'] = 'ix_metadef_resource_types_name'

    metadef_res_types = Table(
        'metadef_resource_types',
        meta,
        Column('id', Integer(), primary_key=True, nullable=False),
        Column('name', String(80), nullable=False),
        Column('protected', Boolean(), nullable=False, default=False),
        Column('created_at', DateTime(), nullable=False),
        Column('updated_at', DateTime()),
        UniqueConstraint('name', **_constr_kwargs),
        mysql_engine='InnoDB',
        mysql_charset='utf8',
        extend_existing=True)

    if meta.bind.name != 'ibm_db_sa':
        Index('ix_metadef_resource_types_name',
              metadef_res_types.c.name)

    return metadef_res_types


def define_metadef_namespace_resource_types_table(meta):

    _constr_kwargs = {}
    if meta.bind.name == 'ibm_db_sa':
        _constr_kwargs['name'] = 'ix_metadef_ns_res_types_res_type_id_ns_id'

    metadef_associations = Table(
        'metadef_namespace_resource_types',
        meta,
        Column('resource_type_id', Integer(),
               ForeignKey('metadef_resource_types.id'),
               primary_key=True, nullable=False),
        Column('namespace_id', Integer(),
               ForeignKey('metadef_namespaces.id'),
               primary_key=True, nullable=False),
        Column('properties_target', String(80)),
        Column('prefix', String(80)),
        Column('created_at', DateTime(), nullable=False),
        Column('updated_at', DateTime()),
        UniqueConstraint('resource_type_id', 'namespace_id',
                         **_constr_kwargs),
        mysql_engine='InnoDB',
        mysql_charset='utf8',
        extend_existing=True)

    if meta.bind.name != 'ibm_db_sa':
        Index('ix_metadef_ns_res_types_res_type_id_ns_id',
              metadef_associations.c.resource_type_id,
              metadef_associations.c.namespace_id)

    return metadef_associations


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine
    tables = [define_metadef_namespaces_table(meta),
              define_metadef_objects_table(meta),
              define_metadef_properties_table(meta),
              define_metadef_resource_types_table(meta),
              define_metadef_namespace_resource_types_table(meta)]
    create_tables(tables)

    resource_types_table = _get_metadef_resource_types_table(meta)
    _populate_resource_types(resource_types_table)
