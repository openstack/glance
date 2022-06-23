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

import http.client as http

from oslo_log import log as logging
from oslo_serialization import jsonutils
from oslo_utils import encodeutils
import webob.exc
from wsme.rest import json

from glance.api import policy
from glance.api.v2 import metadef_namespaces as namespaces
import glance.api.v2.metadef_properties as properties
from glance.api.v2.model.metadef_object import MetadefObject
from glance.api.v2.model.metadef_object import MetadefObjects
from glance.api.v2 import policy as api_policy
from glance.common import exception
from glance.common import wsgi
from glance.common import wsme_utils
import glance.db
from glance.i18n import _
import glance.notifier
import glance.schema

LOG = logging.getLogger(__name__)


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
            ns_repo = self.gateway.get_metadef_namespace_repo(req.context)
            try:
                # NOTE(abhishekk): Verifying that namespace is visible
                # to user
                namespace_obj = ns_repo.get(namespace)
            except exception.Forbidden:
                # NOTE (abhishekk): Returning 404 Not Found as the
                # namespace is outside of this user's project
                msg = _("Namespace %s not found") % namespace
                raise exception.NotFound(msg)

            # NOTE(abhishekk): Metadef object is created for Metadef namespaces
            # Here we are just checking if user is authorized to create metadef
            # object or not.
            api_policy.MetadefAPIPolicy(
                req.context,
                md_resource=namespace_obj,
                enforcer=self.policy).add_metadef_object()

            new_meta_object = object_factory.new_object(
                namespace=namespace,
                **metadata_object.to_dict())
            object_repo.add(new_meta_object)

        except exception.Forbidden as e:
            LOG.debug("User not permitted to create metadata object within "
                      "'%s' namespace", namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.Invalid as e:
            msg = (_("Couldn't create metadata object: %s")
                   % encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPBadRequest(explanation=msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except exception.Duplicate as e:
            raise webob.exc.HTTPConflict(explanation=e.msg)
        return MetadefObject.to_wsme_model(
            new_meta_object,
            get_object_href(namespace, new_meta_object),
            self.obj_schema_link)

    def index(self, req, namespace, marker=None, limit=None,
              sort_key='created_at', sort_dir='desc', filters=None):
        try:
            ns_repo = self.gateway.get_metadef_namespace_repo(req.context)
            try:
                namespace_obj = ns_repo.get(namespace)
            except exception.Forbidden:
                # NOTE (abhishekk): Returning 404 Not Found as the
                # namespace is outside of this user's project
                msg = _("Namespace %s not found") % namespace
                raise exception.NotFound(msg)

            # NOTE(abhishekk): This is just a "do you have permission to
            # list objects" check. Each object is checked against
            # get_metadef_object below.
            api_policy.MetadefAPIPolicy(
                req.context,
                md_resource=namespace_obj,
                enforcer=self.policy).get_metadef_objects()

            filters = filters or dict()
            filters['namespace'] = namespace
            object_repo = self.gateway.get_metadef_object_repo(req.context)

            db_metaobject_list = object_repo.list(
                marker=marker, limit=limit, sort_key=sort_key,
                sort_dir=sort_dir, filters=filters)

            object_list = [
                MetadefObject.to_wsme_model(
                    obj, get_object_href(namespace, obj),
                    self.obj_schema_link
                ) for obj in db_metaobject_list if api_policy.MetadefAPIPolicy(
                    req.context, md_resource=obj.namespace,
                    enforcer=self.policy
                ).check('get_metadef_object')]

            metadef_objects = MetadefObjects()
            metadef_objects.objects = object_list
        except exception.Forbidden as e:
            LOG.debug("User not permitted to retrieve metadata objects within "
                      "'%s' namespace", namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        return metadef_objects

    def show(self, req, namespace, object_name):
        meta_object_repo = self.gateway.get_metadef_object_repo(req.context)
        try:
            ns_repo = self.gateway.get_metadef_namespace_repo(req.context)
            try:
                namespace_obj = ns_repo.get(namespace)
            except exception.Forbidden:
                # NOTE (abhishekk): Returning 404 Not Found as the
                # namespace is outside of this user's project
                msg = _("Namespace %s not found") % namespace
                raise exception.NotFound(msg)

            # NOTE(abhishekk): Metadef objects are associated with
            # namespace, so made provision to pass namespace here
            # for visibility check
            api_policy.MetadefAPIPolicy(
                req.context,
                md_resource=namespace_obj,
                enforcer=self.policy).get_metadef_object()

            metadef_object = meta_object_repo.get(namespace,
                                                  object_name)
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

    def update(self, req, metadata_object, namespace, object_name):
        meta_repo = self.gateway.get_metadef_object_repo(req.context)
        try:
            ns_repo = self.gateway.get_metadef_namespace_repo(req.context)
            try:
                # NOTE(abhishekk): Verifying that namespace is visible
                # to user
                namespace_obj = ns_repo.get(namespace)
            except exception.Forbidden:
                # NOTE (abhishekk): Returning 404 Not Found as the
                # namespace is outside of this user's project
                msg = _("Namespace %s not found") % namespace
                raise exception.NotFound(msg)

            # NOTE(abhishekk): Metadef object is created for Metadef namespaces
            # Here we are just checking if user is authorized to modify metadef
            # object or not.
            api_policy.MetadefAPIPolicy(
                req.context,
                md_resource=namespace_obj,
                enforcer=self.policy).modify_metadef_object()

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
        except exception.Invalid as e:
            msg = (_("Couldn't update metadata object: %s")
                   % encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPBadRequest(explanation=msg)
        except exception.Forbidden as e:
            LOG.debug("User not permitted to update metadata object '%s' "
                      "within '%s' namespace ", object_name, namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except exception.Duplicate as e:
            raise webob.exc.HTTPConflict(explanation=e.msg)
        return MetadefObject.to_wsme_model(
            updated_metadata_obj,
            get_object_href(namespace, updated_metadata_obj),
            self.obj_schema_link)

    def delete(self, req, namespace, object_name):
        meta_repo = self.gateway.get_metadef_object_repo(req.context)
        try:
            ns_repo = self.gateway.get_metadef_namespace_repo(req.context)
            try:
                # NOTE(abhishekk): Verifying that namespace is visible
                # to user
                namespace_obj = ns_repo.get(namespace)
            except exception.Forbidden:
                # NOTE (abhishekk): Returning 404 Not Found as the
                # namespace is outside of this user's project
                msg = _("Namespace %s not found") % namespace
                raise exception.NotFound(msg)

            # NOTE(abhishekk): Metadef object is created for Metadef namespaces
            # Here we are just checking if user is authorized to delete metadef
            # object or not.
            api_policy.MetadefAPIPolicy(
                req.context,
                md_resource=namespace_obj,
                enforcer=self.policy).delete_metadef_object()

            metadef_object = meta_repo.get(namespace, object_name)
            metadef_object.delete()
            meta_repo.remove(metadef_object)
        except exception.Forbidden as e:
            LOG.debug("User not permitted to delete metadata object '%s' "
                      "within '%s' namespace", object_name, namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)


def _get_base_definitions():
    return namespaces.get_schema_definitions()


def _get_base_properties():
    return {
        "name": {
            "type": "string",
            "maxLength": 80
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
            'readOnly': True,
            "type": "string"
        },
        "self": {
            'readOnly': True,
            "type": "string"
        },
        "created_at": {
            "type": "string",
            "readOnly": True,
            "description": _("Date and time of object creation"),
            "format": "date-time"
        },
        "updated_at": {
            "type": "string",
            "readOnly": True,
            "description": _("Date and time of the last object modification"),
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
            if 'properties' in body:
                for propertyname in body['properties']:
                    schema = properties.get_schema(require_name=False)
                    schema.validate(body['properties'][propertyname])
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

    def _validate_limit(self, limit):
        try:
            limit = int(limit)
        except ValueError:
            msg = _("limit param must be an integer")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        if limit <= 0:
            msg = _("limit param must be positive")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        return limit

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
        response.status_int = http.CREATED
        self.show(response, metadata_object)

    def show(self, response, metadata_object):
        metadata_object_json = json.tojson(MetadefObject, metadata_object)
        body = jsonutils.dumps(metadata_object_json, ensure_ascii=False)
        response.unicode_body = body
        response.content_type = 'application/json'

    def update(self, response, metadata_object):
        response.status_int = http.OK
        self.show(response, metadata_object)

    def index(self, response, result):
        result.schema = "v2/schemas/metadefs/objects"
        metadata_objects_json = json.tojson(MetadefObjects, result)
        body = jsonutils.dumps(metadata_objects_json, ensure_ascii=False)
        response.unicode_body = body
        response.content_type = 'application/json'

    def delete(self, response, result):
        response.status_int = http.NO_CONTENT


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
