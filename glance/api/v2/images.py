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
import urllib

import webob.exc

from glance.api import policy
import glance.api.v2 as v2
from glance.common import exception
from glance.common import utils
from glance.common import wsgi
import glance.db
import glance.notifier
from glance.openstack.common import cfg
import glance.openstack.common.log as logging
from glance.openstack.common import timeutils
import glance.schema


LOG = logging.getLogger(__name__)

CONF = cfg.CONF


class ImagesController(object):
    def __init__(self, db_api=None, policy_enforcer=None, notifier=None):
        self.db_api = db_api or glance.db.get_api()
        self.db_api.configure_db()
        self.policy = policy_enforcer or policy.Enforcer()
        self.notifier = notifier or glance.notifier.Notifier()

    def _enforce(self, req, action):
        """Authorize an action against our policies"""
        try:
            self.policy.enforce(req.context, action, {})
        except exception.Forbidden:
            raise webob.exc.HTTPForbidden()

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
            #NOTE(bcwaldon): cast to set to make the list unique, then
            # cast back to list since that's a more sane response type
            return list(set(image.pop('tags')))
        except KeyError:
            pass

    def _append_tags(self, context, image):
        image['tags'] = self.db_api.image_tag_get_all(context, image['id'])
        return image

    @utils.mutating
    def create(self, req, image):
        self._enforce(req, 'add_image')
        is_public = image.get('is_public')
        if is_public:
            self._enforce(req, 'publicize_image')
        image['owner'] = req.context.owner
        image['status'] = 'queued'

        tags = self._extract_tags(image)

        image = dict(self.db_api.image_create(req.context, image))

        if tags is not None:
            self.db_api.image_tag_set_all(req.context, image['id'], tags)
            image['tags'] = tags
        else:
            image['tags'] = []

        v2.update_image_read_acl(req, self.db_api, image)
        image = self._normalize_properties(dict(image))
        self.notifier.info('image.update', image)
        return image

    def index(self, req, marker=None, limit=None, sort_key='created_at',
              sort_dir='desc', filters={}):
        self._enforce(req, 'get_images')
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

    def _get_image(self, context, image_id):
        try:
            return self.db_api.image_get(context, image_id)
        except (exception.NotFound, exception.Forbidden):
            raise webob.exc.HTTPNotFound()

    def show(self, req, image_id):
        self._enforce(req, 'get_image')
        image = self._get_image(req.context, image_id)
        image = self._normalize_properties(dict(image))
        return self._append_tags(req.context, image)

    @utils.mutating
    def update(self, req, image_id, image):
        self._enforce(req, 'modify_image')
        is_public = image.get('is_public')
        if is_public:
            self._enforce(req, 'publicize_image')
        tags = self._extract_tags(image)

        try:
            image = self.db_api.image_update(req.context, image_id, image)
        except (exception.NotFound, exception.Forbidden):
            msg = ("Failed to find image %(image_id)s to update" % locals())
            LOG.info(msg)
            raise webob.exc.HTTPNotFound(explanation=msg)

        image = self._normalize_properties(dict(image))

        v2.update_image_read_acl(req, self.db_api, image)

        if tags is not None:
            self.db_api.image_tag_set_all(req.context, image_id, tags)
            image['tags'] = tags
        else:
            self._append_tags(req.context, image)

        self.notifier.info('image.update', image)
        return image

    @utils.mutating
    def delete(self, req, image_id):
        self._enforce(req, 'delete_image')
        image = self._get_image(req.context, image_id)

        if image['protected']:
            msg = _("Unable to delete as image %(image_id)s is protected"
                    % locals())
            raise webob.exc.HTTPForbidden(explanation=msg)

        try:
            self.db_api.image_destroy(req.context, image_id)
        except (exception.NotFound, exception.Forbidden):
            msg = ("Failed to find image %(image_id)s to delete" % locals())
            LOG.info(msg)
            raise webob.exc.HTTPNotFound()
        else:
            self.notifier.info('image.delete', image)


class RequestDeserializer(wsgi.JSONRequestDeserializer):
    def __init__(self, schema=None):
        super(RequestDeserializer, self).__init__()
        self.schema = schema or get_schema()

    def _parse_image(self, request):
        output = super(RequestDeserializer, self).default(request)
        if not 'body' in output:
            msg = _('Body expected in request.')
            raise webob.exc.HTTPBadRequest(explanation=msg)
        body = output.pop('body')
        try:
            self.schema.validate(body)
        except exception.InvalidObject as e:
            raise webob.exc.HTTPBadRequest(explanation=unicode(e))

        # Ensure all specified properties are allowed
        self._check_readonly(body)
        self._check_reserved(body)

        # Create a dict of base image properties, with user- and deployer-
        # defined properties contained in a 'properties' dictionary
        image = {'properties': body}
        for key in ['checksum', 'created_at', 'container_format',
                'disk_format', 'id', 'min_disk', 'min_ram', 'name', 'size',
                'status', 'tags', 'updated_at', 'visibility', 'protected']:
            try:
                image[key] = image['properties'].pop(key)
            except KeyError:
                pass

        if 'visibility' in image:
            image['is_public'] = image.pop('visibility') == 'public'

        return {'image': image}

    @staticmethod
    def _check_readonly(image):
        for key in ['created_at', 'updated_at', 'status', 'checksum', 'size',
                'direct_url', 'self', 'file', 'schema']:
            if key in image:
                msg = "Attribute \'%s\' is read-only." % key
                raise webob.exc.HTTPForbidden(explanation=unicode(msg))

    @staticmethod
    def _check_reserved(image):
        for key in ['owner', 'is_public', 'location', 'deleted', 'deleted_at']:
            if key in image:
                msg = "Attribute \'%s\' is reserved." % key
                raise webob.exc.HTTPForbidden(explanation=unicode(msg))

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
        #NOTE(bcwaldon): merge the contained properties dict with the
        # top-level image object
        image_view = image['properties']
        attributes = ['id', 'name', 'disk_format', 'container_format',
                      'size', 'status', 'checksum', 'tags', 'protected',
                      'created_at', 'updated_at', 'min_ram', 'min_disk']
        for key in attributes:
            image_view[key] = image[key]

        location = image['location']
        if CONF.show_image_direct_url and location is not None:
            image_view['direct_url'] = location

        visibility = 'public' if image['is_public'] else 'private'
        image_view['visibility'] = visibility

        image_view['self'] = self._get_image_href(image)
        image_view['file'] = self._get_image_href(image, 'file')
        image_view['schema'] = '/v2/schemas/image'

        self._serialize_datetimes(image_view)
        image_view = self.schema.filter(image_view)

        return image_view

    @staticmethod
    def _serialize_datetimes(image):
        for (key, value) in image.iteritems():
            if isinstance(value, datetime.datetime):
                image[key] = timeutils.isotime(value)

    def create(self, response, image):
        response.status_int = 201
        response.body = json.dumps(self._format_image(image))
        response.content_type = 'application/json'
        response.location = self._get_image_href(image)

    def show(self, response, image):
        response.body = json.dumps(self._format_image(image))
        response.content_type = 'application/json'

    def update(self, response, image):
        response.body = json.dumps(self._format_image(image))
        response.content_type = 'application/json'

    def index(self, response, result):
        params = dict(response.request.params)
        params.pop('marker', None)
        query = urllib.urlencode(params)
        body = {
               'images': [self._format_image(i) for i in result['images']],
               'first': '/v2/images',
               'schema': '/v2/schemas/images',
        }
        if query:
            body['first'] = '%s?%s' % (body['first'], query)
        if 'next_marker' in result:
            params['marker'] = result['next_marker']
            next_query = urllib.urlencode(params)
            body['next'] = '/v2/images?%s' % next_query
        response.body = json.dumps(body)
        response.content_type = 'application/json'

    def delete(self, response, result):
        response.status_int = 204


_BASE_PROPERTIES = {
    'id': {
        'type': 'string',
        'description': 'An identifier for the image',
        'pattern': ('^([0-9a-fA-F]){8}-([0-9a-fA-F]){4}-([0-9a-fA-F]){4}'
                    '-([0-9a-fA-F]){4}-([0-9a-fA-F]){12}$'),
    },
    'name': {
        'type': 'string',
        'description': 'Descriptive name for the image',
        'maxLength': 255,
    },
    'status': {
      'type': 'string',
      'description': 'Status of the image',
      'enum': ['queued', 'saving', 'active', 'killed',
               'deleted', 'pending_delete'],
    },
    'visibility': {
        'type': 'string',
        'description': 'Scope of image accessibility',
        'enum': ['public', 'private'],
    },
    'protected': {
        'type': 'boolean',
        'description': 'If true, image will not be deletable.',
    },
    'checksum': {
        'type': 'string',
        'description': 'md5 hash of image contents.',
        'type': 'string',
        'maxLength': 32,
    },
    'size': {
        'type': 'integer',
        'description': 'Size of image file in bytes',
    },
    'container_format': {
        'type': 'string',
        'description': '',
        'type': 'string',
        'enum': ['bare', 'ovf', 'ami', 'aki', 'ari'],
    },
    'disk_format': {
        'type': 'string',
        'description': '',
        'type': 'string',
        'enum': ['raw', 'vhd', 'vmdk', 'vdi', 'iso', 'qcow2',
                 'aki', 'ari', 'ami'],
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
    'direct_url': {
        'type': 'string',
        'description': 'URL to access the image file kept in external store',
    },
    'min_ram': {
        'type': 'integer',
        'description': 'Amount of ram (in MB) required to boot image.',
    },
    'min_disk': {
        'type': 'integer',
        'description': 'Amount of disk space (in GB) required to boot image.',
    },
    'self': {'type': 'string'},
    'file': {'type': 'string'},
    'schema': {'type': 'string'},
}

_BASE_LINKS = [
    {'rel': 'self', 'href': '{self}'},
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


def get_collection_schema(custom_properties=None):
    image_schema = get_schema(custom_properties)
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
