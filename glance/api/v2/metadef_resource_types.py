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
import webob.exc
from wsme.rest import json

from glance.api import policy
from glance.api.v2.model.metadef_resource_type import ResourceType
from glance.api.v2.model.metadef_resource_type import ResourceTypeAssociation
from glance.api.v2.model.metadef_resource_type import ResourceTypeAssociations
from glance.api.v2.model.metadef_resource_type import ResourceTypes
from glance.api.v2 import policy as api_policy
from glance.common import exception
from glance.common import wsgi
import glance.db
import glance.gateway
from glance.i18n import _
import glance.notifier
import glance.schema

LOG = logging.getLogger(__name__)


class ResourceTypeController(object):
    def __init__(self, db_api=None, policy_enforcer=None, notifier=None):
        self.db_api = db_api or glance.db.get_api()
        self.policy = policy_enforcer or policy.Enforcer()
        self.notifier = notifier or glance.notifier.Notifier()
        self.gateway = glance.gateway.Gateway(db_api=self.db_api,
                                              notifier=self.notifier,
                                              policy_enforcer=self.policy)

    def index(self, req):
        try:
            filters = {'namespace': None}
            rs_type_repo = self.gateway.get_metadef_resource_type_repo(
                req.context)
            # NOTE(abhishekk): Here we are just checking if user is
            # authorized to view/list metadef resource types or not.
            # Also there is no relation between list_metadef_resource_types
            # and get_metadef_resource_type policies so can not enforce
            # get_metadef_resource_type policy on individual resource
            # type here.
            api_policy.MetadefAPIPolicy(
                req.context,
                enforcer=self.policy).list_metadef_resource_types()

            db_resource_type_list = rs_type_repo.list(filters=filters)
            resource_type_list = [ResourceType.to_wsme_model(
                resource_type) for resource_type in db_resource_type_list]
            resource_types = ResourceTypes()
            resource_types.resource_types = resource_type_list
        except exception.Forbidden as e:
            LOG.debug("User not permitted to retrieve metadata resource types "
                      "index")
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        return resource_types

    def show(self, req, namespace):
        ns_repo = self.gateway.get_metadef_namespace_repo(req.context)
        try:
            namespace_obj = ns_repo.get(namespace)
        except (exception.Forbidden, exception.NotFound):
            # NOTE (abhishekk): Returning 404 Not Found as the
            # namespace is outside of this user's project
            msg = _("Namespace %s not found") % namespace
            raise webob.exc.HTTPNotFound(explanation=msg)

        try:
            # NOTE(abhishekk): Here we are just checking if user is
            # authorized to view/list metadef resource types or not.
            # Each resource_type is checked against
            # get_metadef_resource_type below.
            api_policy.MetadefAPIPolicy(
                req.context,
                md_resource=namespace_obj,
                enforcer=self.policy).list_metadef_resource_types()

            filters = {'namespace': namespace}
            rs_type_repo = self.gateway.get_metadef_resource_type_repo(
                req.context)
            db_type_list = rs_type_repo.list(filters=filters)

            rs_type_list = [
                ResourceTypeAssociation.to_wsme_model(
                    rs_type
                ) for rs_type in db_type_list if api_policy.MetadefAPIPolicy(
                    req.context, md_resource=rs_type.namespace,
                    enforcer=self.policy
                ).check('get_metadef_resource_type')]

            resource_types = ResourceTypeAssociations()
            resource_types.resource_type_associations = rs_type_list
        except exception.Forbidden as e:
            LOG.debug("User not permitted to retrieve metadata resource types "
                      "within '%s' namespace", namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        return resource_types

    def create(self, req, resource_type, namespace):
        rs_type_factory = self.gateway.get_metadef_resource_type_factory(
            req.context)
        rs_type_repo = self.gateway.get_metadef_resource_type_repo(
            req.context)
        ns_repo = self.gateway.get_metadef_namespace_repo(
            req.context)
        try:
            namespace_obj = ns_repo.get(namespace)
        except (exception.Forbidden, exception.NotFound):
            # NOTE (abhishekk): Returning 404 Not Found as the
            # namespace is outside of this user's project
            msg = _("Namespace %s not found") % namespace
            raise webob.exc.HTTPNotFound(explanation=msg)

        try:
            # NOTE(abhishekk): Metadef resource type is created for Metadef
            # namespaces. Here we are just checking if user is authorized
            # to create metadef resource types or not.
            api_policy.MetadefAPIPolicy(
                req.context,
                md_resource=namespace_obj,
                enforcer=self.policy).add_metadef_resource_type_association()

            new_resource_type = rs_type_factory.new_resource_type(
                namespace=namespace, **resource_type.to_dict())
            rs_type_repo.add(new_resource_type)

        except exception.Forbidden as e:
            LOG.debug("User not permitted to create metadata resource type "
                      "within '%s' namespace", namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except exception.Duplicate as e:
            raise webob.exc.HTTPConflict(explanation=e.msg)
        return ResourceTypeAssociation.to_wsme_model(new_resource_type)

    def delete(self, req, namespace, resource_type):
        rs_type_repo = self.gateway.get_metadef_resource_type_repo(
            req.context)
        ns_repo = self.gateway.get_metadef_namespace_repo(
            req.context)
        try:
            namespace_obj = ns_repo.get(namespace)
        except (exception.Forbidden, exception.NotFound):
            # NOTE (abhishekk): Returning 404 Not Found as the
            # namespace is outside of this user's project
            msg = _("Namespace %s not found") % namespace
            raise webob.exc.HTTPNotFound(explanation=msg)

        try:
            # NOTE(abhishekk): Metadef resource type is created for Metadef
            # namespaces. Here we are just checking if user is authorized
            # to delete metadef resource types or not.
            api_policy.MetadefAPIPolicy(
                req.context,
                md_resource=namespace_obj,
                enforcer=self.policy
            ).remove_metadef_resource_type_association()

            filters = {}
            found = False
            filters['namespace'] = namespace
            db_resource_type_list = rs_type_repo.list(filters=filters)
            for db_resource_type in db_resource_type_list:
                if db_resource_type.name == resource_type:
                    db_resource_type.delete()
                    rs_type_repo.remove(db_resource_type)
                    found = True
            if not found:
                raise exception.NotFound()
        except exception.Forbidden as e:
            LOG.debug("User not permitted to delete metadata resource type "
                      "'%s' within '%s' namespace", resource_type, namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound:
            msg = (_("Failed to find resource type %(resourcetype)s to "
                     "delete") % {'resourcetype': resource_type})
            LOG.error(msg)
            raise webob.exc.HTTPNotFound(explanation=msg)


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
        resource_type = json.fromjson(ResourceTypeAssociation, body)
        return dict(resource_type=resource_type)


class ResponseSerializer(wsgi.JSONResponseSerializer):
    def __init__(self, schema=None):
        super(ResponseSerializer, self).__init__()
        self.schema = schema

    def show(self, response, result):
        resource_type_json = json.tojson(ResourceTypeAssociations, result)
        body = jsonutils.dumps(resource_type_json, ensure_ascii=False)
        response.unicode_body = body
        response.content_type = 'application/json'

    def index(self, response, result):
        resource_type_json = json.tojson(ResourceTypes, result)
        body = jsonutils.dumps(resource_type_json, ensure_ascii=False)
        response.unicode_body = body
        response.content_type = 'application/json'

    def create(self, response, result):
        resource_type_json = json.tojson(ResourceTypeAssociation, result)
        response.status_int = http.CREATED
        body = jsonutils.dumps(resource_type_json, ensure_ascii=False)
        response.unicode_body = body
        response.content_type = 'application/json'

    def delete(self, response, result):
        response.status_int = http.NO_CONTENT


def _get_base_properties():
    return {
        'name': {
            'type': 'string',
            'description': _('Resource type names should be aligned with Heat '
                             'resource types whenever possible: '
                             'https://docs.openstack.org/heat/latest/'
                             'template_guide/openstack.html'),
            'maxLength': 80,
        },
        'prefix': {
            'type': 'string',
            'description': _('Specifies the prefix to use for the given '
                             'resource type. Any properties in the namespace '
                             'should be prefixed with this prefix when being '
                             'applied to the specified resource type. Must '
                             'include prefix separator (e.g. a colon :).'),
            'maxLength': 80,
        },
        'properties_target': {
            'type': 'string',
            'description': _('Some resource types allow more than one key / '
                             'value pair per instance.  For example, Cinder '
                             'allows user and image metadata on volumes. Only '
                             'the image properties metadata is evaluated by '
                             'Nova (scheduling or drivers). This property '
                             'allows a namespace target to remove the '
                             'ambiguity.'),
            'maxLength': 80,
        },
        "created_at": {
            "type": "string",
            "readOnly": True,
            "description": _("Date and time of resource type association"),
            "format": "date-time"
        },
        "updated_at": {
            "type": "string",
            "readOnly": True,
            "description": _("Date and time of the last resource type "
                             "association modification"),
            "format": "date-time"
        }
    }


def get_schema():
    properties = _get_base_properties()
    mandatory_attrs = ResourceTypeAssociation.get_mandatory_attrs()
    schema = glance.schema.Schema(
        'resource_type_association',
        properties,
        required=mandatory_attrs,
    )
    return schema


def get_collection_schema():
    resource_type_schema = get_schema()
    return glance.schema.CollectionSchema('resource_type_associations',
                                          resource_type_schema)


def create_resource():
    """ResourceTypeAssociation resource factory method"""
    schema = get_schema()
    deserializer = RequestDeserializer(schema)
    serializer = ResponseSerializer(schema)
    controller = ResourceTypeController()
    return wsgi.Resource(controller, deserializer, serializer)
