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
from glance.api.v2.model.metadef_namespace import Namespace
from glance.api.v2.model.metadef_property_type import PropertyType
from glance.api.v2.model.metadef_property_type import PropertyTypes
from glance.api.v2 import policy as api_policy
from glance.common import exception
from glance.common import wsgi
import glance.db
import glance.gateway
from glance.i18n import _
import glance.notifier
import glance.schema

LOG = logging.getLogger(__name__)


class NamespacePropertiesController(object):
    def __init__(self, db_api=None, policy_enforcer=None, notifier=None):
        self.db_api = db_api or glance.db.get_api()
        self.policy = policy_enforcer or policy.Enforcer()
        self.notifier = notifier or glance.notifier.Notifier()
        self.gateway = glance.gateway.Gateway(db_api=self.db_api,
                                              notifier=self.notifier,
                                              policy_enforcer=self.policy)

    def _to_dict(self, model_property_type):
        # Convert the model PropertyTypes dict to a JSON encoding
        db_property_type_dict = dict()
        db_property_type_dict['schema'] = json.tojson(
            PropertyType, model_property_type)
        db_property_type_dict['name'] = model_property_type.name
        return db_property_type_dict

    def _to_model(self, db_property_type):
        # Convert the persisted json schema to a dict of PropertyTypes
        property_type = json.fromjson(
            PropertyType, db_property_type.schema)
        property_type.name = db_property_type.name
        return property_type

    def index(self, req, namespace):
        ns_repo = self.gateway.get_metadef_namespace_repo(req.context)
        try:
            namespace_obj = ns_repo.get(namespace)
        except (exception.Forbidden, exception.NotFound):
            # NOTE (abhishekk): Returning 404 Not Found as the
            # namespace is outside of this user's project
            msg = _("Namespace %s not found") % namespace
            raise webob.exc.HTTPNotFound(explanation=msg)

        try:
            # NOTE(abhishekk): This is just a "do you have permission to
            # list properties" check. Each property is checked against
            # get_metadef_property below.
            api_policy.MetadefAPIPolicy(
                req.context,
                md_resource=namespace_obj,
                enforcer=self.policy).get_metadef_properties()

            filters = dict()
            filters['namespace'] = namespace
            prop_repo = self.gateway.get_metadef_property_repo(req.context)
            db_properties = prop_repo.list(filters=filters)
            property_list = Namespace.to_model_properties(db_properties)
            namespace_properties = PropertyTypes()
            namespace_properties.properties = property_list
        except exception.Forbidden as e:
            LOG.debug("User not permitted to retrieve metadata properties "
                      "within '%s' namespace", namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        return namespace_properties

    def show(self, req, namespace, property_name, filters=None):
        ns_repo = self.gateway.get_metadef_namespace_repo(req.context)
        try:
            namespace_obj = ns_repo.get(namespace)
        except (exception.Forbidden, exception.NotFound):
            # NOTE (abhishekk): Returning 404 Not Found as the
            # namespace is outside of this user's project
            msg = _("Namespace %s not found") % namespace
            raise webob.exc.HTTPNotFound(explanation=msg)

        try:
            # NOTE(abhishekk): Metadef properties are associated with
            # namespace, so made provision to pass namespace here
            # for visibility check
            api_pol = api_policy.MetadefAPIPolicy(
                req.context,
                md_resource=namespace_obj,
                enforcer=self.policy)
            api_pol.get_metadef_property()

            if filters and filters['resource_type']:
                # Verify that you can fetch resource type details
                api_pol.get_metadef_resource_type()

                rs_repo = self.gateway.get_metadef_resource_type_repo(
                    req.context)
                db_resource_type = rs_repo.get(filters['resource_type'],
                                               namespace)
                prefix = db_resource_type.prefix
                if prefix and property_name.startswith(prefix):
                    property_name = property_name[len(prefix):]
                else:
                    msg = (_("Property %(property_name)s does not start "
                             "with the expected resource type association "
                             "prefix of '%(prefix)s'.")
                           % {'property_name': property_name,
                              'prefix': prefix})
                    raise exception.NotFound(msg)

            prop_repo = self.gateway.get_metadef_property_repo(req.context)
            db_property = prop_repo.get(namespace, property_name)
            property = self._to_model(db_property)
        except exception.Forbidden as e:
            LOG.debug("User not permitted to show metadata property '%s' "
                      "within '%s' namespace", property_name, namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        return property

    def create(self, req, namespace, property_type):
        prop_factory = self.gateway.get_metadef_property_factory(req.context)
        prop_repo = self.gateway.get_metadef_property_repo(req.context)
        ns_repo = self.gateway.get_metadef_namespace_repo(req.context)
        try:
            namespace_obj = ns_repo.get(namespace)
        except (exception.Forbidden, exception.NotFound):
            # NOTE (abhishekk): Returning 404 Not Found as the
            # namespace is outside of this user's project
            msg = _("Namespace %s not found") % namespace
            raise webob.exc.HTTPNotFound(explanation=msg)

        try:
            # NOTE(abhishekk): Metadef property is created for Metadef
            # namespaces. Here we are just checking if user is authorized
            # to create metadef property or not.
            api_policy.MetadefAPIPolicy(
                req.context,
                md_resource=namespace_obj,
                enforcer=self.policy).add_metadef_property()

            new_property_type = prop_factory.new_namespace_property(
                namespace=namespace, **self._to_dict(property_type))
            prop_repo.add(new_property_type)
        except exception.Forbidden as e:
            LOG.debug("User not permitted to create metadata property within "
                      "'%s' namespace", namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.Invalid as e:
            msg = (_("Couldn't create metadata property: %s")
                   % encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPBadRequest(explanation=msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except exception.Duplicate as e:
            raise webob.exc.HTTPConflict(explanation=e.msg)
        return self._to_model(new_property_type)

    def update(self, req, namespace, property_name, property_type):
        prop_repo = self.gateway.get_metadef_property_repo(req.context)
        ns_repo = self.gateway.get_metadef_namespace_repo(req.context)
        try:
            namespace_obj = ns_repo.get(namespace)
        except (exception.Forbidden, exception.NotFound):
            # NOTE (abhishekk): Returning 404 Not Found as the
            # namespace is outside of this user's project
            msg = _("Namespace %s not found") % namespace
            raise webob.exc.HTTPNotFound(explanation=msg)

        try:
            # NOTE(abhishekk): Metadef property is created for Metadef
            # namespaces. Here we are just checking if user is authorized
            # to update metadef property or not.
            api_policy.MetadefAPIPolicy(
                req.context,
                md_resource=namespace_obj,
                enforcer=self.policy).modify_metadef_property()

            db_property_type = prop_repo.get(namespace, property_name)
            db_property_type._old_name = db_property_type.name
            db_property_type.name = property_type.name
            db_property_type.schema = (self._to_dict(property_type))['schema']
            updated_property_type = prop_repo.save(db_property_type)
        except exception.Invalid as e:
            msg = (_("Couldn't update metadata property: %s")
                   % encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPBadRequest(explanation=msg)
        except exception.Forbidden as e:
            LOG.debug("User not permitted to update metadata property '%s' "
                      "within '%s' namespace", property_name, namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except exception.Duplicate as e:
            raise webob.exc.HTTPConflict(explanation=e.msg)
        return self._to_model(updated_property_type)

    def delete(self, req, namespace, property_name):
        prop_repo = self.gateway.get_metadef_property_repo(req.context)
        ns_repo = self.gateway.get_metadef_namespace_repo(req.context)
        try:
            namespace_obj = ns_repo.get(namespace)
        except (exception.Forbidden, exception.NotFound):
            # NOTE (abhishekk): Returning 404 Not Found as the
            # namespace is outside of this user's project
            msg = _("Namespace %s not found") % namespace
            raise webob.exc.HTTPNotFound(explanation=msg)

        try:
            # NOTE(abhishekk): Metadef property is created for Metadef
            # namespaces. Here we are just checking if user is authorized
            # to delete metadef property or not.
            api_policy.MetadefAPIPolicy(
                req.context,
                md_resource=namespace_obj,
                enforcer=self.policy).remove_metadef_property()

            property_type = prop_repo.get(namespace, property_name)
            property_type.delete()
            prop_repo.remove(property_type)
        except exception.Forbidden as e:
            LOG.debug("User not permitted to delete metadata property '%s' "
                      "within '%s' namespace", property_name, namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)


class RequestDeserializer(wsgi.JSONRequestDeserializer):
    _disallowed_properties = ['created_at', 'updated_at']

    def __init__(self, schema=None):
        super(RequestDeserializer, self).__init__()
        self.schema = schema or get_schema()

    def _get_request_body(self, request):
        output = super(RequestDeserializer, self).default(request)
        if 'body' not in output:
            msg = _('Body expected in request.')
            raise webob.exc.HTTPBadRequest(explanation=msg)
        return output['body']

    @classmethod
    def _check_allowed(cls, image):
        for key in cls._disallowed_properties:
            if key in image:
                msg = _("Attribute '%s' is read-only.") % key
                raise webob.exc.HTTPForbidden(explanation=msg)

    def create(self, request):
        body = self._get_request_body(request)
        self._check_allowed(body)
        try:
            self.schema.validate(body)
        except exception.InvalidObject as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        property_type = json.fromjson(PropertyType, body)
        return dict(property_type=property_type)

    def update(self, request):
        body = self._get_request_body(request)
        self._check_allowed(body)
        try:
            self.schema.validate(body)
        except exception.InvalidObject as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        property_type = json.fromjson(PropertyType, body)
        return dict(property_type=property_type)

    def show(self, request):
        params = request.params.copy()
        query_params = {
            'filters': params
        }
        return query_params


class ResponseSerializer(wsgi.JSONResponseSerializer):
    def __init__(self, schema=None):
        super(ResponseSerializer, self).__init__()
        self.schema = schema

    def show(self, response, result):
        property_type_json = json.tojson(PropertyType, result)
        body = jsonutils.dumps(property_type_json, ensure_ascii=False)
        response.unicode_body = body
        response.content_type = 'application/json'

    def index(self, response, result):
        property_type_json = json.tojson(PropertyTypes, result)
        body = jsonutils.dumps(property_type_json, ensure_ascii=False)
        response.unicode_body = body
        response.content_type = 'application/json'

    def create(self, response, result):
        response.status_int = http.CREATED
        self.show(response, result)

    def update(self, response, result):
        response.status_int = http.OK
        self.show(response, result)

    def delete(self, response, result):
        response.status_int = http.NO_CONTENT


def _get_base_definitions():
    return {
        "positiveInteger": {
            "type": "integer",
            "minimum": 0
        },
        "positiveIntegerDefault0": {
            "allOf": [
                {"$ref": "#/definitions/positiveInteger"},
                {"default": 0}
            ]
        },
        "stringArray": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "uniqueItems": True
        }
    }


def _get_base_properties():
    base_def = namespaces.get_schema_definitions()
    return base_def['property']['additionalProperties']['properties']


def get_schema(require_name=True):
    definitions = _get_base_definitions()
    properties = _get_base_properties()
    mandatory_attrs = PropertyType.get_mandatory_attrs()
    if require_name:
        # name is required attribute when use as single property type
        mandatory_attrs.append('name')
    schema = glance.schema.Schema(
        'property',
        properties,
        required=mandatory_attrs,
        definitions=definitions
    )
    return schema


def get_collection_schema():
    namespace_properties_schema = get_schema()
    # Property name is a dict key and not a required attribute in
    # individual property schema inside property collections
    namespace_properties_schema.required.remove('name')
    return glance.schema.DictCollectionSchema('properties',
                                              namespace_properties_schema)


def create_resource():
    """NamespaceProperties resource factory method"""
    schema = get_schema()
    deserializer = RequestDeserializer(schema)
    serializer = ResponseSerializer(schema)
    controller = NamespacePropertiesController()
    return wsgi.Resource(controller, deserializer, serializer)
