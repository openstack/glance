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
import six.moves.urllib.parse as urlparse
import webob.exc
from wsme.rest import json

from glance.api import policy
from glance.api.v2.model.metadef_namespace import Namespace
from glance.api.v2.model.metadef_namespace import Namespaces
from glance.api.v2.model.metadef_object import MetadefObject
from glance.api.v2.model.metadef_property_type import PropertyType
from glance.api.v2.model.metadef_resource_type import ResourceTypeAssociation
from glance.api.v2.model.metadef_tag import MetadefTag
from glance.common import exception
from glance.common import utils
from glance.common import wsgi
from glance.common import wsme_utils
import glance.db
import glance.gateway
from glance import i18n
import glance.notifier
import glance.schema

LOG = logging.getLogger(__name__)
_ = i18n._
_LE = i18n._LE

CONF = cfg.CONF


class NamespaceController(object):
    def __init__(self, db_api=None, policy_enforcer=None, notifier=None):
        self.db_api = db_api or glance.db.get_api()
        self.policy = policy_enforcer or policy.Enforcer()
        self.notifier = notifier or glance.notifier.Notifier()
        self.gateway = glance.gateway.Gateway(db_api=self.db_api,
                                              notifier=self.notifier,
                                              policy_enforcer=self.policy)
        self.ns_schema_link = '/v2/schemas/metadefs/namespace'
        self.obj_schema_link = '/v2/schemas/metadefs/object'
        self.tag_schema_link = '/v2/schemas/metadefs/tag'

    def index(self, req, marker=None, limit=None, sort_key='created_at',
              sort_dir='desc', filters=None):
        try:
            ns_repo = self.gateway.get_metadef_namespace_repo(req.context)

            # Get namespace id
            if marker:
                namespace_obj = ns_repo.get(marker)
                marker = namespace_obj.namespace_id

            database_ns_list = ns_repo.list(
                marker=marker, limit=limit, sort_key=sort_key,
                sort_dir=sort_dir, filters=filters)
            for db_namespace in database_ns_list:
                # Get resource type associations
                filters = dict()
                filters['namespace'] = db_namespace.namespace
                rs_repo = (
                    self.gateway.get_metadef_resource_type_repo(req.context))
                repo_rs_type_list = rs_repo.list(filters=filters)
                resource_type_list = [ResourceTypeAssociation.to_wsme_model(
                    resource_type) for resource_type in repo_rs_type_list]
                if resource_type_list:
                    db_namespace.resource_type_associations = (
                        resource_type_list)

            namespace_list = [Namespace.to_wsme_model(
                db_namespace,
                get_namespace_href(db_namespace),
                self.ns_schema_link) for db_namespace in database_ns_list]
            namespaces = Namespaces()
            namespaces.namespaces = namespace_list
            if len(namespace_list) != 0 and len(namespace_list) == limit:
                namespaces.next = namespace_list[-1].namespace

        except exception.Forbidden as e:
            LOG.debug("User not permitted to retrieve metadata namespaces "
                      "index")
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except Exception as e:
            LOG.error(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPInternalServerError()
        return namespaces

    @utils.mutating
    def create(self, req, namespace):
        try:
            namespace_created = False
            # Create Namespace
            ns_factory = self.gateway.get_metadef_namespace_factory(
                req.context)
            ns_repo = self.gateway.get_metadef_namespace_repo(req.context)
            new_namespace = ns_factory.new_namespace(**namespace.to_dict())
            ns_repo.add(new_namespace)
            namespace_created = True

            # Create Resource Types
            if namespace.resource_type_associations:
                rs_factory = (self.gateway.get_metadef_resource_type_factory(
                    req.context))
                rs_repo = self.gateway.get_metadef_resource_type_repo(
                    req.context)
                for resource_type in namespace.resource_type_associations:
                    new_resource = rs_factory.new_resource_type(
                        namespace=namespace.namespace,
                        **resource_type.to_dict())
                    rs_repo.add(new_resource)

            # Create Objects
            if namespace.objects:
                object_factory = self.gateway.get_metadef_object_factory(
                    req.context)
                object_repo = self.gateway.get_metadef_object_repo(
                    req.context)
                for metadata_object in namespace.objects:
                    new_meta_object = object_factory.new_object(
                        namespace=namespace.namespace,
                        **metadata_object.to_dict())
                    object_repo.add(new_meta_object)

            # Create Tags
            if namespace.tags:
                tag_factory = self.gateway.get_metadef_tag_factory(
                    req.context)
                tag_repo = self.gateway.get_metadef_tag_repo(req.context)
                for metadata_tag in namespace.tags:
                    new_meta_tag = tag_factory.new_tag(
                        namespace=namespace.namespace,
                        **metadata_tag.to_dict())
                    tag_repo.add(new_meta_tag)

            # Create Namespace Properties
            if namespace.properties:
                prop_factory = (self.gateway.get_metadef_property_factory(
                    req.context))
                prop_repo = self.gateway.get_metadef_property_repo(
                    req.context)
                for (name, value) in namespace.properties.items():
                    new_property_type = (
                        prop_factory.new_namespace_property(
                            namespace=namespace.namespace,
                            **self._to_property_dict(name, value)
                        ))
                    prop_repo.add(new_property_type)

        except exception.Forbidden as e:
            self._cleanup_namespace(ns_repo, namespace, namespace_created)
            LOG.debug("User not permitted to create metadata namespace")
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            self._cleanup_namespace(ns_repo, namespace, namespace_created)
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except exception.Duplicate as e:
            self._cleanup_namespace(ns_repo, namespace, namespace_created)
            raise webob.exc.HTTPConflict(explanation=e.msg)
        except Exception as e:
            LOG.error(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPInternalServerError()

        # Return the user namespace as we don't expose the id to user
        new_namespace.properties = namespace.properties
        new_namespace.objects = namespace.objects
        new_namespace.resource_type_associations = (
            namespace.resource_type_associations)
        new_namespace.tags = namespace.tags
        return Namespace.to_wsme_model(new_namespace,
                                       get_namespace_href(new_namespace),
                                       self.ns_schema_link)

    def _to_property_dict(self, name, value):
        # Convert the model PropertyTypes dict to a JSON string
        db_property_type_dict = dict()
        db_property_type_dict['schema'] = json.tojson(PropertyType, value)
        db_property_type_dict['name'] = name
        return db_property_type_dict

    def _cleanup_namespace(self, namespace_repo, namespace, namespace_created):
        if namespace_created:
            try:
                namespace_obj = namespace_repo.get(namespace.namespace)
                namespace_obj.delete()
                namespace_repo.remove(namespace_obj)
                msg = ("Cleaned up namespace %(namespace)s "
                       % {'namespace': namespace.namespace})
                LOG.debug(msg)
            except exception:
                msg = (_LE("Failed to delete namespace %(namespace)s ") %
                       {'namespace': namespace.namespace})
                LOG.error(msg)

    def show(self, req, namespace, filters=None):
        try:
            # Get namespace
            ns_repo = self.gateway.get_metadef_namespace_repo(req.context)
            namespace_obj = ns_repo.get(namespace)
            namespace_detail = Namespace.to_wsme_model(
                namespace_obj,
                get_namespace_href(namespace_obj),
                self.ns_schema_link)
            ns_filters = dict()
            ns_filters['namespace'] = namespace

            # Get objects
            object_repo = self.gateway.get_metadef_object_repo(req.context)
            db_metaobject_list = object_repo.list(filters=ns_filters)
            object_list = [MetadefObject.to_wsme_model(
                db_metaobject,
                get_object_href(namespace, db_metaobject),
                self.obj_schema_link) for db_metaobject in db_metaobject_list]
            if object_list:
                namespace_detail.objects = object_list

            # Get resource type associations
            rs_repo = self.gateway.get_metadef_resource_type_repo(req.context)
            db_resource_type_list = rs_repo.list(filters=ns_filters)
            resource_type_list = [ResourceTypeAssociation.to_wsme_model(
                resource_type) for resource_type in db_resource_type_list]
            if resource_type_list:
                namespace_detail.resource_type_associations = (
                    resource_type_list)

            # Get properties
            prop_repo = self.gateway.get_metadef_property_repo(req.context)
            db_properties = prop_repo.list(filters=ns_filters)
            property_list = Namespace.to_model_properties(db_properties)
            if property_list:
                namespace_detail.properties = property_list

            if filters and filters['resource_type']:
                namespace_detail = self._prefix_property_name(
                    namespace_detail, filters['resource_type'])

            # Get tags
            tag_repo = self.gateway.get_metadef_tag_repo(req.context)
            db_metatag_list = tag_repo.list(filters=ns_filters)
            tag_list = [MetadefTag(**{'name': db_metatag.name})
                        for db_metatag in db_metatag_list]
            if tag_list:
                namespace_detail.tags = tag_list

        except exception.Forbidden as e:
            LOG.debug("User not permitted to show metadata namespace "
                      "'%s'", namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except Exception as e:
            LOG.error(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPInternalServerError()
        return namespace_detail

    def update(self, req, user_ns, namespace):
        namespace_repo = self.gateway.get_metadef_namespace_repo(req.context)
        try:
            ns_obj = namespace_repo.get(namespace)
            ns_obj._old_namespace = ns_obj.namespace
            ns_obj.namespace = wsme_utils._get_value(user_ns.namespace)
            ns_obj.display_name = wsme_utils._get_value(user_ns.display_name)
            ns_obj.description = wsme_utils._get_value(user_ns.description)
            # Following optional fields will default to same values as in
            # create namespace if not specified
            ns_obj.visibility = (
                wsme_utils._get_value(user_ns.visibility) or 'private')
            ns_obj.protected = (
                wsme_utils._get_value(user_ns.protected) or False)
            ns_obj.owner = (
                wsme_utils._get_value(user_ns.owner) or req.context.owner)
            updated_namespace = namespace_repo.save(ns_obj)
        except exception.Forbidden as e:
            LOG.debug("User not permitted to update metadata namespace "
                      "'%s'", namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except exception.Duplicate as e:
            raise webob.exc.HTTPConflict(explanation=e.msg)
        except Exception as e:
            LOG.error(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPInternalServerError()

        return Namespace.to_wsme_model(updated_namespace,
                                       get_namespace_href(updated_namespace),
                                       self.ns_schema_link)

    def delete(self, req, namespace):
        namespace_repo = self.gateway.get_metadef_namespace_repo(req.context)
        try:
            namespace_obj = namespace_repo.get(namespace)
            namespace_obj.delete()
            namespace_repo.remove(namespace_obj)
        except exception.Forbidden as e:
            LOG.debug("User not permitted to delete metadata namespace "
                      "'%s'", namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except Exception as e:
            LOG.error(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPInternalServerError()

    def delete_objects(self, req, namespace):
        ns_repo = self.gateway.get_metadef_namespace_repo(req.context)
        try:
            namespace_obj = ns_repo.get(namespace)
            namespace_obj.delete()
            ns_repo.remove_objects(namespace_obj)
        except exception.Forbidden as e:
            LOG.debug("User not permitted to delete metadata objects "
                      "within '%s' namespace", namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except Exception as e:
            LOG.error(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPInternalServerError()

    def delete_tags(self, req, namespace):
        ns_repo = self.gateway.get_metadef_namespace_repo(req.context)
        try:
            namespace_obj = ns_repo.get(namespace)
            namespace_obj.delete()
            ns_repo.remove_tags(namespace_obj)
        except exception.Forbidden as e:
            LOG.debug("User not permitted to delete metadata tags "
                      "within '%s' namespace", namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except Exception as e:
            LOG.error(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPInternalServerError()

    def delete_properties(self, req, namespace):
        ns_repo = self.gateway.get_metadef_namespace_repo(req.context)
        try:
            namespace_obj = ns_repo.get(namespace)
            namespace_obj.delete()
            ns_repo.remove_properties(namespace_obj)
        except exception.Forbidden as e:
            LOG.debug("User not permitted to delete metadata properties "
                      "within '%s' namespace", namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except Exception as e:
            LOG.error(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPInternalServerError()

    def _prefix_property_name(self, namespace_detail, user_resource_type):
        prefix = None
        if user_resource_type and namespace_detail.resource_type_associations:
            for resource_type in namespace_detail.resource_type_associations:
                if resource_type.name == user_resource_type:
                    prefix = resource_type.prefix
                    break

        if prefix:
            if namespace_detail.properties:
                new_property_dict = dict()
                for (key, value) in namespace_detail.properties.items():
                    new_property_dict[prefix + key] = value
                namespace_detail.properties = new_property_dict

            if namespace_detail.objects:
                for object in namespace_detail.objects:
                    new_object_property_dict = dict()
                    for (key, value) in object.properties.items():
                        new_object_property_dict[prefix + key] = value
                    object.properties = new_object_property_dict

                    if object.required and len(object.required) > 0:
                        required = [prefix + name for name in object.required]
                        object.required = required

        return namespace_detail


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

    @classmethod
    def _check_allowed(cls, image):
        for key in cls._disallowed_properties:
            if key in image:
                msg = _("Attribute '%s' is read-only.") % key
                raise webob.exc.HTTPForbidden(explanation=msg)

    def index(self, request):
        params = request.params.copy()
        limit = params.pop('limit', None)
        marker = params.pop('marker', None)
        sort_dir = params.pop('sort_dir', 'desc')

        if limit is None:
            limit = CONF.limit_param_default
        limit = min(CONF.api_limit_max, int(limit))

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
            if visibility not in ['public', 'private']:
                msg = _('Invalid visibility value: %s') % visibility
                raise webob.exc.HTTPBadRequest(explanation=msg)

        return filters

    def _validate_limit(self, limit):
        try:
            limit = int(limit)
        except ValueError:
            msg = _("limit param must be an integer")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        if limit < 0:
            msg = _("limit param must be positive")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        return limit

    def show(self, request):
        params = request.params.copy()
        query_params = {
            'filters': self._get_filters(params)
        }
        return query_params

    def create(self, request):
        body = self._get_request_body(request)
        self._check_allowed(body)
        try:
            self.schema.validate(body)
        except exception.InvalidObject as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        namespace = json.fromjson(Namespace, body)
        return dict(namespace=namespace)

    def update(self, request):
        body = self._get_request_body(request)
        self._check_allowed(body)
        try:
            self.schema.validate(body)
        except exception.InvalidObject as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        namespace = json.fromjson(Namespace, body)
        return dict(user_ns=namespace)


class ResponseSerializer(wsgi.JSONResponseSerializer):
    def __init__(self, schema=None):
        super(ResponseSerializer, self).__init__()
        self.schema = schema

    def create(self, response, namespace):
        ns_json = json.tojson(Namespace, namespace)
        response = self.__render(ns_json, response, 201)
        response.location = get_namespace_href(namespace)

    def show(self, response, namespace):
        ns_json = json.tojson(Namespace, namespace)
        response = self.__render(ns_json, response)

    def index(self, response, result):
        params = dict(response.request.params)
        params.pop('marker', None)
        query = urlparse.urlencode(params)
        result.first = "/v2/metadefs/namespaces"
        result.schema = "/v2/schemas/metadefs/namespaces"
        if query:
            result.first = '%s?%s' % (result.first, query)
        if result.next:
            params['marker'] = result.next
            next_query = urlparse.urlencode(params)
            result.next = '/v2/metadefs/namespaces?%s' % next_query

        ns_json = json.tojson(Namespaces, result)
        response = self.__render(ns_json, response)

    def update(self, response, namespace):
        ns_json = json.tojson(Namespace, namespace)
        response = self.__render(ns_json, response, 200)

    def delete(self, response, result):
        response.status_int = 204

    def delete_objects(self, response, result):
        response.status_int = 204

    def delete_properties(self, response, result):
        response.status_int = 204

    def __render(self, json_data, response, response_status=None):
        body = jsonutils.dumps(json_data, ensure_ascii=False)
        response.unicode_body = six.text_type(body)
        response.content_type = 'application/json'
        if response_status:
            response.status_int = response_status
        return response


def _get_base_definitions():
    return get_schema_definitions()


def get_schema_definitions():
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
            # "minItems": 1,
            "uniqueItems": True
        },
        "property": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "required": ["title", "type"],
                "properties": {
                    "name": {
                        "type": "string"
                    },
                    "title": {
                        "type": "string"
                    },
                    "description": {
                        "type": "string"
                    },
                    "operators": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        }
                    },
                    "type": {
                        "type": "string",
                        "enum": [
                            "array",
                            "boolean",
                            "integer",
                            "number",
                            "object",
                            "string",
                            None
                        ]
                    },
                    "required": {
                        "$ref": "#/definitions/stringArray"
                    },
                    "minimum": {
                        "type": "number"
                    },
                    "maximum": {
                        "type": "number"
                    },
                    "maxLength": {
                        "$ref": "#/definitions/positiveInteger"
                    },
                    "minLength": {
                        "$ref": "#/definitions/positiveIntegerDefault0"
                    },
                    "pattern": {
                        "type": "string",
                        "format": "regex"
                    },
                    "enum": {
                        "type": "array"
                    },
                    "readonly": {
                        "type": "boolean"
                    },
                    "default": {},
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": [
                                    "array",
                                    "boolean",
                                    "integer",
                                    "number",
                                    "object",
                                    "string",
                                    None
                                ]
                            },
                            "enum": {
                                "type": "array"
                            }
                        }
                    },
                    "maxItems": {
                        "$ref": "#/definitions/positiveInteger"
                    },
                    "minItems": {
                        "$ref": "#/definitions/positiveIntegerDefault0"
                    },
                    "uniqueItems": {
                        "type": "boolean",
                        "default": False
                    },
                    "additionalItems": {
                        "type": "boolean"
                    },
                }
            }
        }
    }


def _get_base_properties():
    return {
        "namespace": {
            "type": "string",
            "description": _("The unique namespace text."),
            "maxLength": 80,
        },
        "display_name": {
            "type": "string",
            "description": _("The user friendly name for the namespace. Used "
                             "by UI if available."),
            "maxLength": 80,
        },
        "description": {
            "type": "string",
            "description": _("Provides a user friendly description of the "
                             "namespace."),
            "maxLength": 500,
        },
        "visibility": {
            "type": "string",
            "description": _("Scope of namespace accessibility."),
            "enum": ["public", "private"],
        },
        "protected": {
            "type": "boolean",
            "description": _("If true, namespace will not be deletable."),
        },
        "owner": {
            "type": "string",
            "description": _("Owner of the namespace."),
            "maxLength": 255,
        },
        "created_at": {
            "type": "string",
            "description": _("Date and time of namespace creation"
                             " (READ-ONLY)"),
            "format": "date-time"
        },
        "updated_at": {
            "type": "string",
            "description": _("Date and time of the last namespace modification"
                             " (READ-ONLY)"),
            "format": "date-time"
        },
        "schema": {
            "type": "string"
        },
        "self": {
            "type": "string"
        },
        "resource_type_associations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string"
                    },
                    "prefix": {
                        "type": "string"
                    },
                    "properties_target": {
                        "type": "string"
                    }
                }
            }
        },
        "properties": {
            "$ref": "#/definitions/property"
        },
        "objects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
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
                }
            }
        },
        "tags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string"
                    }
                }
            }
        },
    }


def get_schema():
    properties = _get_base_properties()
    definitions = _get_base_definitions()
    mandatory_attrs = Namespace.get_mandatory_attrs()
    schema = glance.schema.Schema(
        'namespace',
        properties,
        required=mandatory_attrs,
        definitions=definitions
    )
    return schema


def get_collection_schema():
    namespace_schema = get_schema()
    return glance.schema.CollectionSchema('namespaces', namespace_schema)


def get_namespace_href(namespace):
    base_href = '/v2/metadefs/namespaces/%s' % namespace.namespace
    return base_href


def get_object_href(namespace_name, metadef_object):
    base_href = ('/v2/metadefs/namespaces/%s/objects/%s' %
                 (namespace_name, metadef_object.name))
    return base_href


def get_tag_href(namespace_name, metadef_tag):
    base_href = ('/v2/metadefs/namespaces/%s/tags/%s' %
                 (namespace_name, metadef_tag.name))
    return base_href


def create_resource():
    """Namespaces resource factory method"""
    schema = get_schema()
    deserializer = RequestDeserializer(schema)
    serializer = ResponseSerializer(schema)
    controller = NamespaceController()
    return wsgi.Resource(controller, deserializer, serializer)
