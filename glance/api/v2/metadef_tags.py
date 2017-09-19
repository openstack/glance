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

from oslo_log import log as logging
from oslo_serialization import jsonutils
from oslo_utils import encodeutils
import six
from six.moves import http_client as http
import webob.exc
from wsme.rest import json

from glance.api import policy
from glance.api.v2.model.metadef_tag import MetadefTag
from glance.api.v2.model.metadef_tag import MetadefTags
from glance.common import exception
from glance.common import wsgi
from glance.common import wsme_utils
import glance.db
from glance.i18n import _
import glance.notifier
import glance.schema

LOG = logging.getLogger(__name__)


class TagsController(object):
    def __init__(self, db_api=None, policy_enforcer=None, notifier=None,
                 schema=None):
        self.db_api = db_api or glance.db.get_api()
        self.policy = policy_enforcer or policy.Enforcer()
        self.notifier = notifier or glance.notifier.Notifier()
        self.gateway = glance.gateway.Gateway(db_api=self.db_api,
                                              notifier=self.notifier,
                                              policy_enforcer=self.policy)
        self.schema = schema or get_schema()
        self.tag_schema_link = '/v2/schemas/metadefs/tag'

    def create(self, req, namespace, tag_name):
        tag_factory = self.gateway.get_metadef_tag_factory(req.context)
        tag_repo = self.gateway.get_metadef_tag_repo(req.context)
        tag_name_as_dict = {'name': tag_name}
        try:
            self.schema.validate(tag_name_as_dict)
        except exception.InvalidObject as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        try:
            new_meta_tag = tag_factory.new_tag(
                namespace=namespace,
                **tag_name_as_dict)
            tag_repo.add(new_meta_tag)
        except exception.Invalid as e:
            msg = (_("Couldn't create metadata tag: %s")
                   % encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPBadRequest(explanation=msg)
        except exception.Forbidden as e:
            LOG.debug("User not permitted to create metadata tag within "
                      "'%s' namespace", namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except exception.Duplicate as e:
            raise webob.exc.HTTPConflict(explanation=e.msg)
        except Exception as e:
            LOG.error(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPInternalServerError()

        return MetadefTag.to_wsme_model(new_meta_tag)

    def create_tags(self, req, metadata_tags, namespace):
        tag_factory = self.gateway.get_metadef_tag_factory(req.context)
        tag_repo = self.gateway.get_metadef_tag_repo(req.context)
        try:
            tag_list = []
            for metadata_tag in metadata_tags.tags:
                tag_list.append(tag_factory.new_tag(
                    namespace=namespace, **metadata_tag.to_dict()))
            tag_repo.add_tags(tag_list)
            tag_list_out = [MetadefTag(**{'name': db_metatag.name})
                            for db_metatag in tag_list]
            metadef_tags = MetadefTags()
            metadef_tags.tags = tag_list_out
        except exception.Forbidden as e:
            LOG.debug("User not permitted to create metadata tags within "
                      "'%s' namespace", namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except exception.Duplicate as e:
            raise webob.exc.HTTPConflict(explanation=e.msg)
        except Exception as e:
            LOG.error(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPInternalServerError()

        return metadef_tags

    def index(self, req, namespace, marker=None, limit=None,
              sort_key='created_at', sort_dir='desc', filters=None):
        try:
            filters = filters or dict()
            filters['namespace'] = namespace

            tag_repo = self.gateway.get_metadef_tag_repo(req.context)
            if marker:
                metadef_tag = tag_repo.get(namespace, marker)
                marker = metadef_tag.tag_id

            db_metatag_list = tag_repo.list(
                marker=marker, limit=limit, sort_key=sort_key,
                sort_dir=sort_dir, filters=filters)

            tag_list = [MetadefTag(**{'name': db_metatag.name})
                        for db_metatag in db_metatag_list]

            metadef_tags = MetadefTags()
            metadef_tags.tags = tag_list
        except exception.Forbidden as e:
            LOG.debug("User not permitted to retrieve metadata tags "
                      "within '%s' namespace", namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except Exception as e:
            LOG.error(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPInternalServerError()

        return metadef_tags

    def show(self, req, namespace, tag_name):
        meta_tag_repo = self.gateway.get_metadef_tag_repo(req.context)
        try:
            metadef_tag = meta_tag_repo.get(namespace, tag_name)
            return MetadefTag.to_wsme_model(metadef_tag)
        except exception.Forbidden as e:
            LOG.debug("User not permitted to show metadata tag '%s' "
                      "within '%s' namespace", tag_name, namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except Exception as e:
            LOG.error(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPInternalServerError()

    def update(self, req, metadata_tag, namespace, tag_name):
        meta_repo = self.gateway.get_metadef_tag_repo(req.context)
        try:
            metadef_tag = meta_repo.get(namespace, tag_name)
            metadef_tag._old_name = metadef_tag.name
            metadef_tag.name = wsme_utils._get_value(
                metadata_tag.name)
            updated_metadata_tag = meta_repo.save(metadef_tag)
        except exception.Invalid as e:
            msg = (_("Couldn't update metadata tag: %s")
                   % encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPBadRequest(explanation=msg)
        except exception.Forbidden as e:
            LOG.debug("User not permitted to update metadata tag '%s' "
                      "within '%s' namespace", tag_name, namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except exception.Duplicate as e:
            raise webob.exc.HTTPConflict(explanation=e.msg)
        except Exception as e:
            LOG.error(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPInternalServerError()

        return MetadefTag.to_wsme_model(updated_metadata_tag)

    def delete(self, req, namespace, tag_name):
        meta_repo = self.gateway.get_metadef_tag_repo(req.context)
        try:
            metadef_tag = meta_repo.get(namespace, tag_name)
            metadef_tag.delete()
            meta_repo.remove(metadef_tag)
        except exception.Forbidden as e:
            LOG.debug("User not permitted to delete metadata tag '%s' "
                      "within '%s' namespace", tag_name, namespace)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except Exception as e:
            LOG.error(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPInternalServerError()


def _get_base_definitions():
    return None


def _get_base_properties():
    return {
        "name": {
            "type": "string",
            "maxLength": 80
        },
        "created_at": {
            "type": "string",
            "readOnly": True,
            "description": _("Date and time of tag creation"),
            "format": "date-time"
        },
        "updated_at": {
            "type": "string",
            "readOnly": True,
            "description": _("Date and time of the last tag modification"),
            "format": "date-time"
        }
    }


def _get_base_properties_for_list():
    return {
        "tags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string"
                    }
                },
                'required': ['name'],
                "additionalProperties": False
            }
        },
    }


def get_schema():
    definitions = _get_base_definitions()
    properties = _get_base_properties()
    mandatory_attrs = MetadefTag.get_mandatory_attrs()
    schema = glance.schema.Schema(
        'tag',
        properties,
        required=mandatory_attrs,
        definitions=definitions,
    )
    return schema


def get_schema_for_list():
    definitions = _get_base_definitions()
    properties = _get_base_properties_for_list()
    schema = glance.schema.Schema(
        'tags',
        properties,
        required=None,
        definitions=definitions,
    )
    return schema


def get_collection_schema():
    tag_schema = get_schema()
    return glance.schema.CollectionSchema('tags', tag_schema)


class RequestDeserializer(wsgi.JSONRequestDeserializer):
    _disallowed_properties = ['created_at', 'updated_at']

    def __init__(self, schema=None):
        super(RequestDeserializer, self).__init__()
        self.schema = schema or get_schema()
        self.schema_for_list = get_schema_for_list()

    def _get_request_body(self, request):
        output = super(RequestDeserializer, self).default(request)
        if 'body' not in output:
            msg = _('Body expected in request.')
            raise webob.exc.HTTPBadRequest(explanation=msg)
        return output['body']

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

        if limit < 0:
            msg = _("limit param must be positive")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        return limit

    def update(self, request):
        body = self._get_request_body(request)
        self._check_allowed(body)
        try:
            self.schema.validate(body)
        except exception.InvalidObject as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        metadata_tag = json.fromjson(MetadefTag, body)
        return dict(metadata_tag=metadata_tag)

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

        if marker:
            query_params['marker'] = marker

        if limit:
            query_params['limit'] = self._validate_limit(limit)

        return query_params

    def create_tags(self, request):
        body = self._get_request_body(request)
        self._check_allowed(body)
        try:
            self.schema_for_list.validate(body)
        except exception.InvalidObject as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        metadata_tags = json.fromjson(MetadefTags, body)
        return dict(metadata_tags=metadata_tags)

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

    def create(self, response, metadata_tag):
        response.status_int = http.CREATED
        self.show(response, metadata_tag)

    def create_tags(self, response, result):
        response.status_int = http.CREATED
        metadata_tags_json = json.tojson(MetadefTags, result)
        body = jsonutils.dumps(metadata_tags_json, ensure_ascii=False)
        response.unicode_body = six.text_type(body)
        response.content_type = 'application/json'

    def show(self, response, metadata_tag):
        metadata_tag_json = json.tojson(MetadefTag, metadata_tag)
        body = jsonutils.dumps(metadata_tag_json, ensure_ascii=False)
        response.unicode_body = six.text_type(body)
        response.content_type = 'application/json'

    def update(self, response, metadata_tag):
        response.status_int = http.OK
        self.show(response, metadata_tag)

    def index(self, response, result):
        metadata_tags_json = json.tojson(MetadefTags, result)
        body = jsonutils.dumps(metadata_tags_json, ensure_ascii=False)
        response.unicode_body = six.text_type(body)
        response.content_type = 'application/json'

    def delete(self, response, result):
        response.status_int = http.NO_CONTENT


def get_tag_href(namespace_name, metadef_tag):
    base_href = ('/v2/metadefs/namespaces/%s/tags/%s' %
                 (namespace_name, metadef_tag.name))
    return base_href


def create_resource():
    """Metadef tags resource factory method"""
    schema = get_schema()
    deserializer = RequestDeserializer(schema)
    serializer = ResponseSerializer(schema)
    controller = TagsController()
    return wsgi.Resource(controller, deserializer, serializer)
