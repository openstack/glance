# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
# Copyright 2013 OpenStack Foundation
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

import json
import os
from os.path import isfile
from os.path import join
import re

from oslo.config import cfg
import six
import sqlalchemy
from sqlalchemy.schema import MetaData
from sqlalchemy.sql import select

from glance.common import utils
from glance import i18n
import glance.openstack.common.log as logging
from glance.openstack.common import timeutils

LOG = logging.getLogger(__name__)
_LE = i18n._LE
_LW = i18n._LW
_LI = i18n._LI

metadata_opts = [
    cfg.StrOpt('metadata_source_path', default='/etc/glance/metadefs/',
               help=_('Path to the directory where json metadata '
                      'files are stored'))
]

CONF = cfg.CONF
CONF.register_opts(metadata_opts)


def get_metadef_namespaces_table(meta):
    return sqlalchemy.Table('metadef_namespaces', meta, autoload=True)


def get_metadef_resource_types_table(meta):
    return sqlalchemy.Table('metadef_resource_types', meta, autoload=True)


def get_metadef_namespace_resource_types_table(meta):
    return sqlalchemy.Table('metadef_namespace_resource_types', meta,
                            autoload=True)


def get_metadef_properties_table(meta):
    return sqlalchemy.Table('metadef_properties', meta, autoload=True)


def get_metadef_objects_table(meta):
    return sqlalchemy.Table('metadef_objects', meta, autoload=True)


def _get_resource_type_id(meta, name):
    resource_types_table = get_metadef_resource_types_table(meta)
    return resource_types_table.select().\
        where(resource_types_table.c.name == name).execute().fetchone().id


def _get_resource_type(meta, resource_type_id):
    resource_types_table = get_metadef_resource_types_table(meta)
    return resource_types_table.select().\
        where(resource_types_table.c.id == resource_type_id).\
        execute().fetchone()


def _get_namespace_resource_types(meta, namespace_id):
    namespace_resource_types_table =\
        get_metadef_namespace_resource_types_table(meta)
    return namespace_resource_types_table.select().\
        where(namespace_resource_types_table.c.namespace_id == namespace_id).\
        execute().fetchall()


def _get_properties(meta, namespace_id):
    properties_table = get_metadef_properties_table(meta)
    return properties_table.select().\
        where(properties_table.c.namespace_id == namespace_id).\
        execute().fetchall()


def _get_objects(meta, namespace_id):
    objects_table = get_metadef_objects_table(meta)
    return objects_table.select().\
        where(objects_table.c.namespace_id == namespace_id).\
        execute().fetchall()


def _populate_metadata(meta, metadata_path=None):
    if not metadata_path:
        metadata_path = CONF.metadata_source_path

    try:
        json_schema_files = [f for f in os.listdir(metadata_path)
                             if isfile(join(metadata_path, f))
                             and f.endswith('.json')]
    except OSError as e:
        LOG.error(utils.exception_to_str(e))
        return

    metadef_namespaces_table = get_metadef_namespaces_table(meta)
    metadef_namespace_resource_types_tables =\
        get_metadef_namespace_resource_types_table(meta)
    metadef_objects_table = get_metadef_objects_table(meta)
    metadef_properties_table = get_metadef_properties_table(meta)
    metadef_resource_types_table = get_metadef_resource_types_table(meta)

    if not json_schema_files:
        LOG.error(_LE("Json schema files not found in %s. Aborting."),
                  metadata_path)
        return

    for json_schema_file in json_schema_files:
        try:
            file = join(metadata_path, json_schema_file)
            with open(file) as json_file:
                metadata = json.load(json_file)
        except Exception as e:
            LOG.error(utils.exception_to_str(e))
            continue

        values = {
            'namespace': metadata.get('namespace', None),
            'display_name': metadata.get('display_name', None),
            'description': metadata.get('description', None),
            'visibility': metadata.get('visibility', None),
            'protected': metadata.get('protected', None),
            'owner': metadata.get('owner', 'admin'),
            'created_at': timeutils.utcnow()
        }

        temp = metadef_namespaces_table.select(
            whereclause='namespace = \'%s\'' % values['namespace'])\
            .execute().fetchone()

        if temp == None:
            _insert_data_to_db(metadef_namespaces_table, values)

            db_namespace = select(
                [metadef_namespaces_table.c.id]
            ).where(
                metadef_namespaces_table.c.namespace == values['namespace']
            ).select_from(
                metadef_namespaces_table
            ).execute().fetchone()
            namespace_id = db_namespace['id']

            for resource_type in metadata.get('resource_type_associations',
                                              []):
                try:
                    resource_type_id = \
                        _get_resource_type_id(meta, resource_type['name'])
                except AttributeError:
                    values = {
                        'name': resource_type['name'],
                        'protected': True,
                        'created_at': timeutils.utcnow()
                    }
                    _insert_data_to_db(metadef_resource_types_table,
                                       values)
                    resource_type_id =\
                        _get_resource_type_id(meta, resource_type['name'])

                values = {
                    'resource_type_id': resource_type_id,
                    'namespace_id': namespace_id,
                    'created_at': timeutils.utcnow(),
                    'properties_target': resource_type.get(
                        'properties_target'),
                    'prefix': resource_type.get('prefix', None)
                }
                _insert_data_to_db(metadef_namespace_resource_types_tables,
                                   values)

            for property, schema in six.iteritems(metadata.get('properties',
                                                               {})):
                values = {
                    'name': property,
                    'namespace_id': namespace_id,
                    'json_schema': json.dumps(schema),
                    'created_at': timeutils.utcnow()
                }
                _insert_data_to_db(metadef_properties_table, values)

            for object in metadata.get('objects', []):
                values = {
                    'name': object.get('name', None),
                    'description': object.get('description', None),
                    'namespace_id': namespace_id,
                    'json_schema': json.dumps(object.get('properties', None)),
                    'created_at': timeutils.utcnow()
                }
                _insert_data_to_db(metadef_objects_table, values)

            LOG.info(_LI("File %s loaded to database."), file)
        else:
            LOG.info(_LI("Skipping  namespace %s. It already exists in the "
                         "database."), values['namespace'])

    LOG.info(_LI("Metadata loading finished"))


def _clear_metadata(meta):
    metadef_tables = [get_metadef_properties_table(meta),
                      get_metadef_objects_table(meta),
                      get_metadef_namespace_resource_types_table(meta),
                      get_metadef_namespaces_table(meta)]

    for table in metadef_tables:
        table.delete().execute()
        LOG.info(_LI("Table %s has been cleared"), table)


def _insert_data_to_db(table, values, log_exception=True):
    try:
        table.insert(values=values).execute()
    except sqlalchemy.exc.IntegrityError:
        if log_exception:
            LOG.warning(_LW("Duplicate entry for values: %s"), values)


def _export_data_to_file(meta, path):
    if not path:
        path = CONF.metadata_source_path

    namespace_table = get_metadef_namespaces_table(meta)
    namespaces = namespace_table.select().execute().fetchall()

    pattern = re.compile('[\W_]+', re.UNICODE)

    for id, namespace in enumerate(namespaces, start=1):
        namespace_id = namespace['id']
        namespace_file_name = pattern.sub('', namespace['display_name'])

        values = {
            'namespace': namespace['namespace'],
            'display_name': namespace['display_name'],
            'description': namespace['description'],
            'visibility': namespace['visibility'],
            'protected': namespace['protected'],
            'owner': namespace['owner'],
            'resource_type_associations': [],
            'properties': {},
            'objects': []
        }

        namespace_resource_types = _get_namespace_resource_types(meta,
                                                                 namespace_id)
        db_objects = _get_objects(meta, namespace_id)
        db_properties = _get_properties(meta, namespace_id)

        resource_types = []
        for namespace_resource_type in namespace_resource_types:
            resource_type =\
                _get_resource_type(meta,
                                   namespace_resource_type['resource_type_id'])
            resource_types.append({
                'name': resource_type['name'],
                'protected': resource_type['protected']
            })
        values.update({
            'resource_type_associations': resource_types
        })

        objects = []
        for object in db_objects:
            objects.append({
                "name": object['name'],
                "description": object['description'],
                "properties": json.loads(object['json_schema'])
            })
        values.update({
            'objects': objects
        })

        properties = {}
        for property in db_properties:
            properties.update({
                property['name']: json.loads(property['json_schema'])
            })
        values.update({
            'properties': properties
        })

        try:
            file_name = ''.join([path, namespace_file_name, '.json'])
            with open(file_name, 'w') as json_file:
                json_file.write(json.dumps(values))
        except Exception as e:
            LOG.exception(utils.exception_to_str(e))
        LOG.info(_LI("Namespace %s saved in %s"),
                 namespace_file_name, file_name)


def db_load_metadefs(engine, metadata_path=None):
    meta = MetaData()
    meta.bind = engine

    _populate_metadata(meta, metadata_path)


def db_unload_metadefs(engine):
    meta = MetaData()
    meta.bind = engine

    _clear_metadata(meta)


def db_export_metadefs(engine, metadata_path=None):
    meta = MetaData()
    meta.bind = engine

    _export_data_to_file(meta, metadata_path)
