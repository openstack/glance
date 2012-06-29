# Copyright 2012 OpenStack LLC.
# All Rights Reserved.
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

import copy
import datetime
import json
import logging
import urllib

import webob.exc

from glance.common import exception
from glance.common import utils
from glance.common import wsgi
import glance.db
from glance.openstack.common import cfg
from glance.openstack.common import timeutils
import glance.schema


LOG = logging.getLogger(__name__)

CONF = cfg.CONF


class ImagesController(object):
    def __init__(self, db_api=None):
        self.db_api = db_api or glance.db.get_api()
        self.db_api.configure_db()

    def _normalize_properties(self, image):
        """Convert the properties from the stored format to a dict

        The db api returns a list of dicts that look like
        {'name': <key>, 'value': <value>}, while it expects a format
        like {<key>: <value>} in image create and update calls. This
        function takes the extra step that the db api should be
        responsible for in the image get calls.
        """
        properties = [(p['name'], p['value']) for p in image['properties']]
        image['properties'] = dict(properties)
        return image

    def _extract_tags(self, image):
        try:
            return image.pop('tags')
        except KeyError:
            pass

    def _append_tags(self, context, image):
        image['tags'] = self.db_api.image_tag_get_all(context, image['id'])
        return image

    @utils.mutating
    def create(self, req, image):
        if 'owner' not in image:
            image['owner'] = req.context.owner
        elif not req.context.is_admin:
            raise webob.exc.HTTPForbidden()

        #TODO(bcwaldon): this should eventually be settable through the API
        image['status'] = 'queued'

        tags = self._extract_tags(image)

        image = dict(self.db_api.image_create(req.context, image))

        if tags is not None:
            self.db_api.image_tag_set_all(req.context, image['id'], tags)
            image['tags'] = tags
        else:
            image['tags'] = []

        return self._normalize_properties(dict(image))

    def index(self, req, marker=None, limit=None, sort_key='created_at',
              sort_dir='desc', filters={}):
        filters['deleted'] = False
        #NOTE(bcwaldon): is_public=True gets public images and those
        # owned by the authenticated tenant
        result = {}
        filters.setdefault('is_public', True)
        if limit is None:
            limit = CONF.limit_param_default
        limit = min(CONF.api_limit_max, limit)

        try:
            images = self.db_api.image_get_all(req.context, filters=filters,
                                               marker=marker, limit=limit,
                                               sort_key=sort_key,
                                               sort_dir=sort_dir)
            if len(images) != 0 and len(images) == limit:
                result['next_marker'] = images[-1]['id']
        except exception.InvalidFilterRangeValue as e:
            raise webob.exc.HTTPBadRequest(explanation=unicode(e))
        except exception.InvalidSortKey as e:
            raise webob.exc.HTTPBadRequest(explanation=unicode(e))
        except exception.NotFound as e:
            raise webob.exc.HTTPBadRequest(explanation=unicode(e))
        images = [self._normalize_properties(dict(image)) for image in images]
        result['images'] = [self._append_tags(req.context, image)
                            for image in images]
        return result

    def show(self, req, image_id):
        try:
            image = self.db_api.image_get(req.context, image_id)
        except (exception.NotFound, exception.Forbidden):
            raise webob.exc.HTTPNotFound()
        image = self._normalize_properties(dict(image))
        return self._append_tags(req.context, image)

    @utils.mutating
    def update(self, req, image_id, image):
        tags = self._extract_tags(image)

        try:
            image = self.db_api.image_update(req.context, image_id, image)
        except (exception.NotFound, exception.Forbidden):
            raise webob.exc.HTTPNotFound()

        image = self._normalize_properties(dict(image))

        if tags is not None:
            self.db_api.image_tag_set_all(req.context, image_id, tags)
            image['tags'] = tags
        else:
            self._append_tags(req.context, image)

        return image

    @utils.mutating
    def delete(self, req, image_id):
        try:
            self.db_api.image_destroy(req.context, image_id)
        except (exception.NotFound, exception.Forbidden):
            raise webob.exc.HTTPNotFound()


class RequestDeserializer(wsgi.JSONRequestDeserializer):
    def __init__(self, schema=None):
        super(RequestDeserializer, self).__init__()
        self.schema = schema or get_schema()

    def _parse_image(self, request):
        output = super(RequestDeserializer, self).default(request)
        body = output.pop('body')
        self.schema.validate(body)

        # Create a dict of base image properties, with user- and deployer-
        # defined properties contained in a 'properties' dictionary
        image = {'properties': body}
        for key in ['id', 'name', 'visibility', 'created_at', 'updated_at',
                    'tags']:
            try:
                image[key] = image['properties'].pop(key)
            except KeyError:
                pass

        if 'visibility' in image:
            image['is_public'] = image.pop('visibility') == 'public'

        self._remove_readonly(image)
        return {'image': image}

    @staticmethod
    def _remove_readonly(image):
        for key in ['created_at', 'updated_at']:
            if key in image:
                del image[key]

    def create(self, request):
        return self._parse_image(request)

    def update(self, request):
        return self._parse_image(request)

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

    def _validate_sort_dir(self, sort_dir):
        if sort_dir not in ['asc', 'desc']:
            msg = _('Invalid sort direction: %s' % sort_dir)
            raise webob.exc.HTTPBadRequest(explanation=msg)

        return sort_dir

    def _get_filters(self, filters):
        visibility = filters.pop('visibility', None)
        if visibility:
            if visibility in ['public', 'private']:
                filters['is_public'] = visibility == 'public'
            else:
                msg = _('Invalid visibility value: %s') % visibility
                raise webob.exc.HTTPBadRequest(explanation=msg)

        return filters

    def index(self, request):
        params = request.params.copy()
        limit = params.pop('limit', None)
        marker = params.pop('marker', None)
        sort_dir = params.pop('sort_dir', 'desc')
        query_params = {
            'sort_key': params.pop('sort_key', 'created_at'),
            'sort_dir': self._validate_sort_dir(sort_dir),
            'filters': self._get_filters(params),
        }

        if marker is not None:
            query_params['marker'] = marker

        if limit is not None:
            query_params['limit'] = self._validate_limit(limit)

        return query_params


class ResponseSerializer(wsgi.JSONResponseSerializer):
    def __init__(self, schema=None):
        super(ResponseSerializer, self).__init__()
        self.schema = schema or get_schema()

    def _get_image_href(self, image, subcollection=''):
        base_href = '/v2/images/%s' % image['id']
        if subcollection:
            base_href = '%s/%s' % (base_href, subcollection)
        return base_href

    def _get_image_links(self, image):
        return [
            {'rel': 'self', 'href': self._get_image_href(image)},
            {'rel': 'file', 'href': self._get_image_href(image, 'file')},
            {'rel': 'describedby', 'href': '/v2/schemas/image'},
        ]

    def _format_image(self, image):
        _image = image['properties']
        for key in ['id', 'name', 'created_at', 'updated_at', 'tags']:
            _image[key] = image[key]
        _image['visibility'] = 'public' if image['is_public'] else 'private'
        _image = self.schema.filter(_image)
        _image['self'] = self._get_image_href(image)
        _image['file'] = self._get_image_href(image, 'file')
        _image['access'] = self._get_image_href(image, 'access')
        _image['schema'] = '/v2/schemas/image'
        self._serialize_datetimes(_image)
        return _image

    @staticmethod
    def _serialize_datetimes(image):
        for (key, value) in image.iteritems():
            if isinstance(value, datetime.datetime):
                image[key] = timeutils.isotime(value)

    def create(self, response, image):
        response.body = json.dumps({'image': self._format_image(image)})
        response.location = self._get_image_href(image)

    def show(self, response, image):
        response.body = json.dumps({'image': self._format_image(image)})

    def update(self, response, image):
        response.body = json.dumps({'image': self._format_image(image)})

    def index(self, response, result):
        params = dict(response.request.params)
        params.pop('marker', None)
        query = urllib.urlencode(params)
        body = {
               'images': [self._format_image(i) for i in result['images']],
               'first': '/v2/images',
        }
        if query:
            body['first'] = '%s?%s' % (body['first'], query)
        if 'next_marker' in result:
            params['marker'] = result['next_marker']
            next_query = urllib.urlencode(params)
            body['next'] = '/v2/images?%s' % next_query
        response.body = json.dumps(body)

    def delete(self, response, result):
        response.status_int = 204


_BASE_PROPERTIES = {
    'id': {
        'type': 'string',
        'description': 'An identifier for the image',
        'maxLength': 36,
    },
    'name': {
        'type': 'string',
        'description': 'Descriptive name for the image',
        'maxLength': 255,
    },
    'visibility': {
        'type': 'string',
        'description': 'Scope of image accessibility',
        'enum': ['public', 'private'],
    },
    'created_at': {
        'type': 'string',
        'description': 'Date and time of image registration',
        #TODO(bcwaldon): our jsonschema library doesn't seem to like the
        # format attribute, figure out why!
        #'format': 'date-time',
    },
    'updated_at': {
        'type': 'string',
        'description': 'Date and time of the last image modification',
        #'format': 'date-time',
    },
    'tags': {
        'type': 'array',
        'description': 'List of strings related to the image',
        'items': {
            'type': 'string',
            'maxLength': 255,
        },
    },
    'self': {'type': 'string'},
    'access': {'type': 'string'},
    'file': {'type': 'string'},
    'schema': {'type': 'string'},
}

_BASE_LINKS = [
    {'rel': 'self', 'href': '{self}'},
    {'rel': 'related', 'href': '{access}'},
    {'rel': 'enclosure', 'href': '{file}'},
    {'rel': 'describedby', 'href': '{schema}'},
]


def get_schema(custom_properties=None):
    properties = copy.deepcopy(_BASE_PROPERTIES)
    links = copy.deepcopy(_BASE_LINKS)
    if CONF.allow_additional_image_properties:
        schema = glance.schema.PermissiveSchema('image', properties, links)
    else:
        schema = glance.schema.Schema('image', properties)
    schema.merge_properties(custom_properties or {})
    return schema


def get_collection_schema():
    image_schema = get_schema()
    return glance.schema.CollectionSchema('images', image_schema)


def load_custom_properties():
    """Find the schema properties files and load them into a dict."""
    filename = 'schema-image.json'
    match = CONF.find_file(filename)
    if match:
        schema_file = open(match)
        schema_data = schema_file.read()
        return json.loads(schema_data)
    else:
        msg = _('Could not find schema properties file %s. Continuing '
                'without custom properties')
        LOG.warn(msg % filename)
        return {}


def create_resource(custom_properties=None):
    """Images resource factory method"""
    schema = get_schema(custom_properties)
    deserializer = RequestDeserializer(schema)
    serializer = ResponseSerializer(schema)
    controller = ImagesController()
    return wsgi.Resource(controller, deserializer, serializer)
