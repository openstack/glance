# Copyright (c) 2014 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from oslo_config import cfg
from oslo_log import log as logging
from oslo_serialization import jsonutils
from oslo_utils import encodeutils
import six
import webob.exc
from wsme.rest import json

from glance.api import policy
from glance.api.v2 import metadef_namespaces as namespaces
from glance.api.v2.model.metadef_object import MetadefObject
from glance.api.v2.model.metadef_object import MetadefObjects
from glance.common import exception
from glance.common import wsgi
from glance.common import wsme_utils
import glance.db
from glance import i18n
import glance.notifier
import glance.schema

LOG = logging.getLogger(__name__)
_ = i18n._

CONF = cfg.CONF


class MetadefObjectsController(object):
    def __init__(self, db_api=None, policy_enforcer=None, notifier=None):
        self.db_api = db_api or glance.db.get_api()
        self.policy = policy_enforcer or policy.Enforcer()
        self.notifier = notifier or glance.notifier.Notifier()
        self.gateway = glance.gateway.Gateway(db_api=self.db_api,
                                              notifier=self.notifier,
                                              policy_enforcer=self.policy)
        self.obj_schema_link = '/v2/schemas/metadefs/object'

    def create(self, req, metadata_object, namespace):
        object_factory = self.gateway.get_metadef_object_factory(req.context)
        object_repo = self.gateway.get_metadef_object_repo(req.context)
        try:
            new_meta_object = object_factory.new_object(
                namespace=namespace,
                **metadata_object.to_dict())
            object_repo.add(new_meta_object)

        except exception.Forbidden as e:
            LOG.debug("User not permitted to create metadata object within "
                      "'%s' namespace", namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except exception.Duplicate as e:
            raise webob.exc.HTTPConflict(explanation=e.msg)
        except Exception as e:
            LOG.error(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPInternalServerError()
        return MetadefObject.to_wsme_model(
            new_meta_object,
            get_object_href(namespace, new_meta_object),
            self.obj_schema_link)

    def index(self, req, namespace, marker=None, limit=None,
              sort_key='created_at', sort_dir='desc', filters=None):
        try:
            filters = filters or dict()
            filters['namespace'] = namespace
            object_repo = self.gateway.get_metadef_object_repo(req.context)
            db_metaobject_list = object_repo.list(
                marker=marker, limit=limit, sort_key=sort_key,
                sort_dir=sort_dir, filters=filters)
            object_list = [MetadefObject.to_wsme_model(
                db_metaobject,
                get_object_href(namespace, db_metaobject),
                self.obj_schema_link) for db_metaobject in db_metaobject_list]
            metadef_objects = MetadefObjects()
            metadef_objects.objects = object_list
        except exception.Forbidden as e:
            LOG.debug("User not permitted to retrieve metadata objects within "
                      "'%s' namespace", namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except Exception as e:
            LOG.error(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPInternalServerError()
        return metadef_objects

    def show(self, req, namespace, object_name):
        meta_object_repo = self.gateway.get_metadef_object_repo(
            req.context)
        try:
            metadef_object = meta_object_repo.get(namespace, object_name)
            return MetadefObject.to_wsme_model(
                metadef_object,
                get_object_href(namespace, metadef_object),
                self.obj_schema_link)
        except exception.Forbidden as e:
            LOG.debug("User not permitted to show metadata object '%s' "
                      "within '%s' namespace", namespace, object_name)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except Exception as e:
            LOG.error(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPInternalServerError()

    def update(self, req, metadata_object, namespace, object_name):
        meta_repo = self.gateway.get_metadef_object_repo(req.context)
        try:
            metadef_object = meta_repo.get(namespace, object_name)
            metadef_object._old_name = metadef_object.name
            metadef_object.name = wsme_utils._get_value(
                metadata_object.name)
            metadef_object.description = wsme_utils._get_value(
                metadata_object.description)
            metadef_object.required = wsme_utils._get_value(
                metadata_object.required)
            metadef_object.properties = wsme_utils._get_value(
                metadata_object.properties)
            updated_metadata_obj = meta_repo.save(metadef_object)
        except exception.Forbidden as e:
            LOG.debug("User not permitted to update metadata object '%s' "
                      "within '%s' namespace ", object_name, namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except exception.Duplicate as e:
            raise webob.exc.HTTPConflict(explanation=e.msg)
        except Exception as e:
            LOG.error(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPInternalServerError()
        return MetadefObject.to_wsme_model(
            updated_metadata_obj,
            get_object_href(namespace, updated_metadata_obj),
            self.obj_schema_link)

    def delete(self, req, namespace, object_name):
        meta_repo = self.gateway.get_metadef_object_repo(req.context)
        try:
            metadef_object = meta_repo.get(namespace, object_name)
            metadef_object.delete()
            meta_repo.remove(metadef_object)
        except exception.Forbidden as e:
            LOG.debug("User not permitted to delete metadata object '%s' "
                      "within '%s' namespace", object_name, namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except Exception as e:
            LOG.error(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPInternalServerError()


def _get_base_definitions():
    return namespaces.get_schema_definitions()


def _get_base_properties():
    return {
        "name": {
            "type": "string"
        },
        "description": {
            "type": "string"
        },
        "required": {
            "$ref": "#/definitions/stringArray"
        },
        "properties": {
            "$ref": "#/definitions/property"
        },
        "schema": {
            "type": "string"
        },
        "self": {
            "type": "string"
        },
        "created_at": {
            "type": "string",
            "description": _("Date and time of object creation"
                             " (READ-ONLY)"),
            "format": "date-time"
        },
        "updated_at": {
            "type": "string",
            "description": _("Date and time of the last object modification"
                             " (READ-ONLY)"),
            "format": "date-time"
        }
    }


def get_schema():
    definitions = _get_base_definitions()
    properties = _get_base_properties()
    mandatory_attrs = MetadefObject.get_mandatory_attrs()
    schema = glance.schema.Schema(
        'object',
        properties,
        required=mandatory_attrs,
        definitions=definitions,
    )
    return schema


def get_collection_schema():
    object_schema = get_schema()
    return glance.schema.CollectionSchema('objects', object_schema)


class RequestDeserializer(wsgi.JSONRequestDeserializer):
    _disallowed_properties = ['self', 'schema', 'created_at', 'updated_at']

    def __init__(self, schema=None):
        super(RequestDeserializer, self).__init__()
        self.schema = schema or get_schema()

    def _get_request_body(self, request):
        output = super(RequestDeserializer, self).default(request)
        if 'body' not in output:
            msg = _('Body expected in request.')
            raise webob.exc.HTTPBadRequest(explanation=msg)
        return output['body']

    def create(self, request):
        body = self._get_request_body(request)
        self._check_allowed(body)
        try:
            self.schema.validate(body)
        except exception.InvalidObject as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        metadata_object = json.fromjson(MetadefObject, body)
        return dict(metadata_object=metadata_object)

    def update(self, request):
        body = self._get_request_body(request)
        self._check_allowed(body)
        try:
            self.schema.validate(body)
        except exception.InvalidObject as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        metadata_object = json.fromjson(MetadefObject, body)
        return dict(metadata_object=metadata_object)

    def index(self, request):
        params = request.params.copy()
        limit = params.pop('limit', None)
        marker = params.pop('marker', None)
        sort_dir = params.pop('sort_dir', 'desc')

        query_params = {
            'sort_key': params.pop('sort_key', 'created_at'),
            'sort_dir': self._validate_sort_dir(sort_dir),
            'filters': self._get_filters(params)
        }

        if marker is not None:
            query_params['marker'] = marker

        if limit is not None:
            query_params['limit'] = self._validate_limit(limit)

        return query_params

    def _validate_sort_dir(self, sort_dir):
        if sort_dir not in ['asc', 'desc']:
            msg = _('Invalid sort direction: %s') % sort_dir
            raise webob.exc.HTTPBadRequest(explanation=msg)

        return sort_dir

    def _get_filters(self, filters):
        visibility = filters.get('visibility')
        if visibility:
            if visibility not in ['public', 'private', 'shared']:
                msg = _('Invalid visibility value: %s') % visibility
                raise webob.exc.HTTPBadRequest(explanation=msg)

        return filters

    @classmethod
    def _check_allowed(cls, image):
        for key in cls._disallowed_properties:
            if key in image:
                msg = _("Attribute '%s' is read-only.") % key
                raise webob.exc.HTTPForbidden(explanation=msg)


class ResponseSerializer(wsgi.JSONResponseSerializer):
    def __init__(self, schema=None):
        super(ResponseSerializer, self).__init__()
        self.schema = schema or get_schema()

    def create(self, response, metadata_object):
        response.status_int = 201
        self.show(response, metadata_object)

    def show(self, response, metadata_object):
        metadata_object_json = json.tojson(MetadefObject, metadata_object)
        body = jsonutils.dumps(metadata_object_json, ensure_ascii=False)
        response.unicode_body = six.text_type(body)
        response.content_type = 'application/json'

    def update(self, response, metadata_object):
        response.status_int = 200
        self.show(response, metadata_object)

    def index(self, response, result):
        result.schema = "v2/schemas/metadefs/objects"
        metadata_objects_json = json.tojson(MetadefObjects, result)
        body = jsonutils.dumps(metadata_objects_json, ensure_ascii=False)
        response.unicode_body = six.text_type(body)
        response.content_type = 'application/json'

    def delete(self, response, result):
        response.status_int = 204


def get_object_href(namespace_name, metadef_object):
    base_href = ('/v2/metadefs/namespaces/%s/objects/%s' %
                 (namespace_name, metadef_object.name))
    return base_href


def create_resource():
    """Metadef objects resource factory method"""
    schema = get_schema()
    deserializer = RequestDeserializer(schema)
    serializer = ResponseSerializer(schema)
    controller = MetadefObjectsController()
    return wsgi.Resource(controller, deserializer, serializer)
