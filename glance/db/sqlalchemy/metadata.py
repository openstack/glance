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

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import encodeutils
import sqlalchemy
from sqlalchemy import and_
from sqlalchemy.schema import MetaData
from sqlalchemy.sql import select

from glance.common import timeutils
from glance.i18n import _, _LE, _LI, _LW

LOG = logging.getLogger(__name__)

metadata_opts = [
    cfg.StrOpt('metadata_source_path',
               default='/etc/glance/metadefs/',
               help=_("""
Absolute path to the directory where JSON metadefs files are stored.

Glance Metadata Definitions ("metadefs") are served from the database,
but are stored in files in the JSON format.  The files in this
directory are used to initialize the metadefs in the database.
Additionally, when metadefs are exported from the database, the files
are written to this directory.

NOTE: If you plan to export metadefs, make sure that this directory
has write permissions set for the user being used to run the
glance-api service.

Possible values:
    * String value representing a valid absolute pathname

Related options:
    * None

""")),
]

CONF = cfg.CONF
CONF.register_opts(metadata_opts)


def get_metadef_namespaces_table(meta, conn):
    with conn.begin():
        return sqlalchemy.Table('metadef_namespaces', meta, autoload_with=conn)


def get_metadef_resource_types_table(meta, conn):
    with conn.begin():
        return sqlalchemy.Table('metadef_resource_types', meta,
                                autoload_with=conn)


def get_metadef_namespace_resource_types_table(meta, conn):
    with conn.begin():
        return sqlalchemy.Table('metadef_namespace_resource_types', meta,
                                autoload_with=conn)


def get_metadef_properties_table(meta, conn):
    with conn.begin():
        return sqlalchemy.Table('metadef_properties', meta, autoload_with=conn)


def get_metadef_objects_table(meta, conn):
    with conn.begin():
        return sqlalchemy.Table('metadef_objects', meta, autoload_with=conn)


def get_metadef_tags_table(meta, conn):
    with conn.begin():
        return sqlalchemy.Table('metadef_tags', meta, autoload_with=conn)


def _get_resource_type_id(meta, conn, name):
    rt_table = get_metadef_resource_types_table(meta, conn)
    with conn.begin():
        resource_type = conn.execute(
            select(rt_table.c.id).where(
                rt_table.c.name == name
            ).select_from(rt_table)
        ).fetchone()
        if resource_type:
            return resource_type[0]
    return None


def _get_resource_type(meta, conn, resource_type_id):
    rt_table = get_metadef_resource_types_table(meta, conn)
    with conn.begin():
        return conn.execute(
            rt_table.select().where(
                rt_table.c.id == resource_type_id
            )
        ).fetchone()


def _get_namespace_resource_types(meta, conn, namespace_id):
    namespace_resource_types_table = (
        get_metadef_namespace_resource_types_table(meta, conn))
    with conn.begin():
        return conn.execute(
            namespace_resource_types_table.select().where(
                namespace_resource_types_table.c.namespace_id == namespace_id
            )
        ).fetchall()


def _get_namespace_resource_type_by_ids(meta, conn, namespace_id, rt_id):
    namespace_resource_types_table = (
        get_metadef_namespace_resource_types_table(meta, conn))
    with conn.begin():
        return conn.execute(
            namespace_resource_types_table.select().where(and_(
                namespace_resource_types_table.c.namespace_id == namespace_id,
                namespace_resource_types_table.c.resource_type_id == rt_id)
            )
        ).fetchone()


def _get_properties(meta, conn, namespace_id):
    properties_table = get_metadef_properties_table(meta, conn)
    with conn.begin():
        return conn.execute(
            properties_table.select().where(
                properties_table.c.namespace_id == namespace_id
            )
        ).fetchall()


def _get_objects(meta, conn, namespace_id):
    objects_table = get_metadef_objects_table(meta, conn)
    with conn.begin():
        return conn.execute(
            objects_table.select().where(
                objects_table.c.namespace_id == namespace_id)
        ).fetchall()


def _get_tags(meta, conn, namespace_id):
    tags_table = get_metadef_tags_table(meta, conn)
    with conn.begin():
        return conn.execute(
            tags_table.select().where(
                tags_table.c.namespace_id == namespace_id
            )
        ).fetchall()


def _get_resource_id(table, conn, namespace_id, resource_name):
    with conn.begin():
        resource = conn.execute(
            select(table.c.id).where(
                and_(
                    table.c.namespace_id == namespace_id,
                    table.c.name == resource_name,
                )
            ).select_from(table)
        ).fetchone()
        if resource:
            return resource[0]
    return None


def _clear_metadata(meta, conn):
    metadef_tables = [get_metadef_properties_table(meta, conn),
                      get_metadef_objects_table(meta, conn),
                      get_metadef_tags_table(meta, conn),
                      get_metadef_namespace_resource_types_table(meta, conn),
                      get_metadef_namespaces_table(meta, conn),
                      get_metadef_resource_types_table(meta, conn)]

    with conn.begin():
        for table in metadef_tables:
            conn.execute(table.delete())
            LOG.info(_LI("Table %s has been cleared"), table)


def _clear_namespace_metadata(meta, conn, namespace_id):
    metadef_tables = [get_metadef_properties_table(meta, conn),
                      get_metadef_objects_table(meta, conn),
                      get_metadef_tags_table(meta, conn),
                      get_metadef_namespace_resource_types_table(meta, conn)]
    namespaces_table = get_metadef_namespaces_table(meta, conn)

    with conn.begin():
        for table in metadef_tables:
            conn.execute(
                table.delete().where(table.c.namespace_id == namespace_id))

        conn.execute(
            namespaces_table.delete().where(
                namespaces_table.c.id == namespace_id))


def _populate_metadata(meta, conn, metadata_path=None, merge=False,
                       prefer_new=False, overwrite=False):
    if not metadata_path:
        metadata_path = CONF.metadata_source_path

    try:
        if isfile(metadata_path):
            json_schema_files = [metadata_path]
        else:
            json_schema_files = [f for f in os.listdir(metadata_path)
                                 if isfile(join(metadata_path, f))
                                 and f.endswith('.json')]
    except OSError as e:
        LOG.error(encodeutils.exception_to_unicode(e))
        return

    if not json_schema_files:
        LOG.error(_LE("Json schema files not found in %s. Aborting."),
                  metadata_path)
        return

    namespaces_table = get_metadef_namespaces_table(meta, conn)
    namespace_rt_table = get_metadef_namespace_resource_types_table(meta, conn)
    objects_table = get_metadef_objects_table(meta, conn)
    tags_table = get_metadef_tags_table(meta, conn)
    properties_table = get_metadef_properties_table(meta, conn)
    resource_types_table = get_metadef_resource_types_table(meta, conn)

    for json_schema_file in json_schema_files:
        try:
            file = join(metadata_path, json_schema_file)
            with open(file) as json_file:
                metadata = json.load(json_file)
        except Exception as e:
            LOG.error(_LE("Failed to parse json file %(file_path)s while "
                          "populating metadata due to: %(error_msg)s"),
                      {"file_path": file,
                       "error_msg": encodeutils.exception_to_unicode(e)})
            continue

        values = {
            'namespace': metadata.get('namespace'),
            'display_name': metadata.get('display_name'),
            'description': metadata.get('description'),
            'visibility': metadata.get('visibility'),
            'protected': metadata.get('protected'),
            'owner': metadata.get('owner', 'admin')
        }

        with conn.begin():
            db_namespace = conn.execute(
                select(
                    namespaces_table.c.id
                ).where(
                    namespaces_table.c.namespace == values['namespace']
                ).select_from(
                    namespaces_table
                )
            ).fetchone()

        if db_namespace and overwrite:
            LOG.info(_LI("Overwriting namespace %s"), values['namespace'])
            _clear_namespace_metadata(meta, conn, db_namespace[0])
            db_namespace = None

        if not db_namespace:
            values.update({'created_at': timeutils.utcnow()})
            _insert_data_to_db(conn, namespaces_table, values)

            with conn.begin():
                db_namespace = conn.execute(
                    select(
                        namespaces_table.c.id
                    ).where(
                        namespaces_table.c.namespace == values['namespace']
                    ).select_from(
                        namespaces_table
                    )
                ).fetchone()
        elif not merge:
            LOG.info(_LI("Skipping namespace %s. It already exists in the "
                         "database."), values['namespace'])
            continue
        elif prefer_new:
            values.update({'updated_at': timeutils.utcnow()})
            _update_data_in_db(conn, namespaces_table, values,
                               namespaces_table.c.id, db_namespace[0])

        namespace_id = db_namespace[0]

        for resource_type in metadata.get('resource_type_associations', []):
            rt_id = _get_resource_type_id(meta, conn, resource_type['name'])
            if not rt_id:
                val = {
                    'name': resource_type['name'],
                    'created_at': timeutils.utcnow(),
                    'protected': True
                }
                _insert_data_to_db(conn, resource_types_table, val)
                rt_id = _get_resource_type_id(
                    meta, conn, resource_type['name'])
            elif prefer_new:
                val = {'updated_at': timeutils.utcnow()}
                _update_data_in_db(conn, resource_types_table, val,
                                   resource_types_table.c.id, rt_id)

            values = {
                'namespace_id': namespace_id,
                'resource_type_id': rt_id,
                'properties_target': resource_type.get(
                    'properties_target'),
                'prefix': resource_type.get('prefix')
            }
            namespace_resource_type = _get_namespace_resource_type_by_ids(
                meta, conn, namespace_id, rt_id)
            if not namespace_resource_type:
                values.update({'created_at': timeutils.utcnow()})
                _insert_data_to_db(conn, namespace_rt_table, values)
            elif prefer_new:
                values.update({'updated_at': timeutils.utcnow()})
                _update_rt_association(conn, namespace_rt_table, values,
                                       rt_id, namespace_id)

        for name, schema in metadata.get('properties', {}).items():
            values = {
                'name': name,
                'namespace_id': namespace_id,
                'json_schema': json.dumps(schema)
            }
            property_id = _get_resource_id(
                properties_table, conn, namespace_id, name,
            )
            if not property_id:
                values.update({'created_at': timeutils.utcnow()})
                _insert_data_to_db(conn, properties_table, values)
            elif prefer_new:
                values.update({'updated_at': timeutils.utcnow()})
                _update_data_in_db(conn, properties_table, values,
                                   properties_table.c.id, property_id)

        for object in metadata.get('objects', []):
            values = {
                'name': object['name'],
                'description': object.get('description'),
                'namespace_id': namespace_id,
                'json_schema': json.dumps(
                    object.get('properties'))
            }
            object_id = _get_resource_id(objects_table, conn, namespace_id,
                                         object['name'])
            if not object_id:
                values.update({'created_at': timeutils.utcnow()})
                _insert_data_to_db(conn, objects_table, values)
            elif prefer_new:
                values.update({'updated_at': timeutils.utcnow()})
                _update_data_in_db(conn, objects_table, values,
                                   objects_table.c.id, object_id)

        for tag in metadata.get('tags', []):
            values = {
                'name': tag.get('name'),
                'namespace_id': namespace_id,
            }
            tag_id = _get_resource_id(
                tags_table, conn, namespace_id, tag['name'])
            if not tag_id:
                values.update({'created_at': timeutils.utcnow()})
                _insert_data_to_db(conn, tags_table, values)
            elif prefer_new:
                values.update({'updated_at': timeutils.utcnow()})
                _update_data_in_db(conn, tags_table, values,
                                   tags_table.c.id, tag_id)

        LOG.info(_LI("File %s loaded to database."), file)

    LOG.info(_LI("Metadata loading finished"))


def _insert_data_to_db(conn, table, values, log_exception=True):
    try:
        with conn.begin():
            conn.execute(table.insert().values(values))
    except sqlalchemy.exc.IntegrityError:
        if log_exception:
            LOG.warning(_LW("Duplicate entry for values: %s"), values)


def _update_data_in_db(conn, table, values, column, value):
    try:
        with conn.begin():
            conn.execute(
                table.update().values(values).where(column == value)
            )
    except sqlalchemy.exc.IntegrityError:
        LOG.warning(_LW("Duplicate entry for values: %s"), values)


def _update_rt_association(conn, table, values, rt_id, namespace_id):
    try:
        with conn.begin():
            conn.execute(
                table.update().values(values).where(
                    and_(
                        table.c.resource_type_id == rt_id,
                        table.c.namespace_id == namespace_id,
                    )
                )
            )
    except sqlalchemy.exc.IntegrityError:
        LOG.warning(_LW("Duplicate entry for values: %s"), values)


def _export_data_to_file(meta, conn, path):
    if not path:
        path = CONF.metadata_source_path

    namespace_table = get_metadef_namespaces_table(meta)
    with conn.begin():
        namespaces = conn.execute(namespace_table.select()).fetchall()

    pattern = re.compile(r'[\W_]+', re.UNICODE)

    for id, namespace in enumerate(namespaces, start=1):
        namespace_id = namespace['id']
        namespace_file_name = pattern.sub('', namespace['display_name'])

        values = {
            'namespace': namespace['namespace'],
            'display_name': namespace['display_name'],
            'description': namespace['description'],
            'visibility': namespace['visibility'],
            'protected': namespace['protected'],
            'resource_type_associations': [],
            'properties': {},
            'objects': [],
            'tags': []
        }

        namespace_resource_types = _get_namespace_resource_types(
            meta, conn, namespace_id)
        db_objects = _get_objects(meta, conn, namespace_id)
        db_properties = _get_properties(meta, conn, namespace_id)
        db_tags = _get_tags(meta, conn, namespace_id)

        resource_types = []
        for namespace_resource_type in namespace_resource_types:
            resource_type = _get_resource_type(
                meta, conn, namespace_resource_type['resource_type_id'])
            resource_types.append({
                'name': resource_type['name'],
                'prefix': namespace_resource_type['prefix'],
                'properties_target': namespace_resource_type[
                    'properties_target']
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

        tags = []
        for tag in db_tags:
            tags.append({
                "name": tag['name']
            })
        values.update({
            'tags': tags
        })

        try:
            file_name = ''.join([path, namespace_file_name, '.json'])
            if isfile(file_name):
                LOG.info(_LI("Overwriting: %s"), file_name)
            with open(file_name, 'w') as json_file:
                json_file.write(json.dumps(values))
        except Exception as e:
            LOG.exception(encodeutils.exception_to_unicode(e))
        LOG.info(_LI("Namespace %(namespace)s saved in %(file)s"), {
            'namespace': namespace_file_name, 'file': file_name})


def db_load_metadefs(engine, metadata_path=None, merge=False,
                     prefer_new=False, overwrite=False):
    meta = MetaData()

    if not merge and (prefer_new or overwrite):
        LOG.error(_LE("To use --prefer_new or --overwrite you need to combine "
                      "of these options with --merge option."))
        return

    if prefer_new and overwrite and merge:
        LOG.error(_LE("Please provide no more than one option from this list: "
                      "--prefer_new, --overwrite"))
        return

    with engine.connect() as conn:
        _populate_metadata(
            meta, conn, metadata_path, merge, prefer_new, overwrite)


def db_unload_metadefs(engine):
    meta = MetaData()

    with engine.connect() as conn:
        _clear_metadata(meta, conn)


def db_export_metadefs(engine, metadata_path=None):
    meta = MetaData()

    with engine.connect() as conn:
        _export_data_to_file(meta, conn, metadata_path)
