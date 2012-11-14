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
import re
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
import glance.store


LOG = logging.getLogger(__name__)

CONF = cfg.CONF


class ImagesController(object):
    def __init__(self, db_api=None, policy_enforcer=None, notifier=None,
            store_api=None):
        self.db_api = db_api or glance.db.get_api()
        self.db_api.configure_db()
        self.policy = policy_enforcer or policy.Enforcer()
        self.notifier = notifier or glance.notifier.Notifier()
        self.store_api = store_api or glance.store
        self.store_api.create_stores()

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

        The db api will also return deleted image properties that must
        be filtered out.
        """
        properties = [(p['name'], p['value'])
                      for p in image['properties'] if not p['deleted']]
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

        v2.update_image_read_acl(req, self.store_api, self.db_api, image)
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
            image = self.db_api.image_get(context, image_id)
            if image['deleted']:
                raise exception.NotFound()
        except (exception.NotFound, exception.Forbidden):
            raise webob.exc.HTTPNotFound()
        return image

    def show(self, req, image_id):
        self._enforce(req, 'get_image')
        image = self._get_image(req.context, image_id)
        image = self._normalize_properties(dict(image))
        return self._append_tags(req.context, image)

    @utils.mutating
    def update(self, req, image_id, changes):
        self._enforce(req, 'modify_image')
        context = req.context
        try:
            image = self.db_api.image_get(context, image_id)
            if image['deleted']:
                raise exception.NotFound()
        except (exception.NotFound, exception.Forbidden):
            msg = ("Failed to find image %(image_id)s to update" % locals())
            LOG.info(msg)
            raise webob.exc.HTTPNotFound(explanation=msg)

        image = self._normalize_properties(dict(image))
        updates = self._extract_updates(req, image, changes)

        tags = None
        if len(updates) > 0:
            tags = self._extract_tags(updates)
            purge_props = 'properties' in updates
            try:
                image = self.db_api.image_update(context, image_id, updates,
                                                 purge_props)
            except (exception.NotFound, exception.Forbidden):
                raise webob.exc.HTTPNotFound()
            image = self._normalize_properties(dict(image))

        v2.update_image_read_acl(req, self.store_api, self.db_api, image)

        if tags is not None:
            self.db_api.image_tag_set_all(req.context, image_id, tags)
            image['tags'] = tags
        else:
            self._append_tags(req.context, image)

        self.notifier.info('image.update', image)
        return image

    def _extract_updates(self, req, image, changes):
        """ Determine the updates to pass to the database api.

        Given the current image, convert a list of changes to be made
        into the corresponding update dictionary that should be passed to
        db_api.image_update.

        Changes have the following parts
        op    - 'add' a new attribute, 'replace' an existing attribute, or
                'remove' an existing attribute.
        path  - A list of path parts for determining which attribute the
                the operation applies to.
        value - For 'add' and 'replace', the new value the attribute should
                assume.

        For the current use case, there are two types of valid paths. For base
        attributes (fields stored directly on the Image object) the path
        must take the form ['<attribute name>']. These attributes are always
        present so the only valid operation on them is 'replace'. For image
        properties, the path takes the form ['properties', '<property name>']
        and all operations are valid.

        Future refactoring should simplify this code by hardening the image
        abstraction such that database details such as how image properties
        are stored do not have any influence here.
        """
        updates = {}
        property_updates = image['properties']
        for change in changes:
            path = change['path']
            if len(path) == 1:
                assert change['op'] == 'replace'
                key = change['path'][0]
                if key == 'is_public' and change['value']:
                    self._enforce(req, 'publicize_image')
                updates[key] = change['value']
            else:
                assert len(path) == 2
                assert path[0] == 'properties'
                update_method_name = '_do_%s_property' % change['op']
                assert hasattr(self, update_method_name)
                update_method = getattr(self, update_method_name)
                update_method(property_updates, change)
                updates['properties'] = property_updates
        return updates

    def _do_replace_property(self, updates, change):
        """ Replace a single image property, ensuring it's present. """
        key = change['path'][1]
        if key not in updates:
            msg = _("Property %s does not exist.")
            raise webob.exc.HTTPConflict(msg % key)
        updates[key] = change['value']

    def _do_add_property(self, updates, change):
        """ Add a new image property, ensuring it does not already exist. """
        key = change['path'][1]
        if key in updates:
            msg = _("Property %s already present.")
            raise webob.exc.HTTPConflict(msg % key)
        updates[key] = change['value']

    def _do_remove_property(self, updates, change):
        """ Remove an image property, ensuring it's present. """
        key = change['path'][1]
        if key not in updates:
            msg = _("Property %s does not exist.")
            raise webob.exc.HTTPConflict(msg % key)
        del updates[key]

    @utils.mutating
    def delete(self, req, image_id):
        self._enforce(req, 'delete_image')
        image = self._get_image(req.context, image_id)

        if image['protected']:
            msg = _("Unable to delete as image %(image_id)s is protected"
                    % locals())
            raise webob.exc.HTTPForbidden(explanation=msg)

        if image['location'] and CONF.delayed_delete:
            status = 'pending_delete'
        else:
            status = 'deleted'

        try:
            self.db_api.image_update(req.context, image_id, {'status': status})
            self.db_api.image_destroy(req.context, image_id)

            if image['location']:
                if CONF.delayed_delete:
                    self.store_api.schedule_delayed_delete_from_backend(
                                    image['location'], id)
                else:
                    self.store_api.safe_delete_from_backend(image['location'],
                                                            req.context, id)
        except (exception.NotFound, exception.Forbidden):
            msg = ("Failed to find image %(image_id)s to delete" % locals())
            LOG.info(msg)
            raise webob.exc.HTTPNotFound()
        else:
            self.notifier.info('image.delete', image)


class RequestDeserializer(wsgi.JSONRequestDeserializer):

    _readonly_properties = ['created_at', 'updated_at', 'status', 'checksum',
            'size', 'direct_url', 'self', 'file', 'schema']
    _reserved_properties = ['owner', 'is_public', 'location',
            'deleted', 'deleted_at']
    _base_properties = ['checksum', 'created_at', 'container_format',
            'disk_format', 'id', 'min_disk', 'min_ram', 'name', 'size',
            'status', 'tags', 'updated_at', 'visibility', 'protected']

    def __init__(self, schema=None):
        super(RequestDeserializer, self).__init__()
        self.schema = schema or get_schema()

    def _parse_image(self, request):
        body = self._get_request_body(request)
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
        for key in self._base_properties:
            try:
                image[key] = image['properties'].pop(key)
            except KeyError:
                pass

        if 'visibility' in image:
            image['is_public'] = image.pop('visibility') == 'public'

        return {'image': image}

    def _get_request_body(self, request):
        output = super(RequestDeserializer, self).default(request)
        if not 'body' in output:
            msg = _('Body expected in request.')
            raise webob.exc.HTTPBadRequest(explanation=msg)
        return output['body']

    @classmethod
    def _check_readonly(cls, image):
        for key in cls._readonly_properties:
            if key in image:
                msg = "Attribute \'%s\' is read-only." % key
                raise webob.exc.HTTPForbidden(explanation=unicode(msg))

    @classmethod
    def _check_reserved(cls, image):
        for key in cls._reserved_properties:
            if key in image:
                msg = "Attribute \'%s\' is reserved." % key
                raise webob.exc.HTTPForbidden(explanation=unicode(msg))

    def create(self, request):
        return self._parse_image(request)

    def _get_change_operation(self, raw_change):
        op = None
        for key in ['replace', 'add', 'remove']:
            if key in raw_change:
                if op is not None:
                    msg = _('Operation objects must contain only one member'
                            ' named "add", "remove", or "replace".')
                    raise webob.exc.HTTPBadRequest(explanation=msg)
                op = key
        if op is None:
            msg = _('Operation objects must contain exactly one member'
                    ' named "add", "remove", or "replace".')
            raise webob.exc.HTTPBadRequest(explanation=msg)
        return op

    def _get_change_path(self, raw_change, op):
        key = self._decode_json_pointer(raw_change[op])
        if key in self._readonly_properties:
            msg = "Attribute \'%s\' is read-only." % key
            raise webob.exc.HTTPForbidden(explanation=unicode(msg))
        if key in self._reserved_properties:
            msg = "Attribute \'%s\' is reserved." % key
            raise webob.exc.HTTPForbidden(explanation=unicode(msg))

        # For image properties, we need to put "properties" at the beginning
        if key not in self._base_properties:
            return ['properties', key]
        return [key]

    def _decode_json_pointer(self, pointer):
        """ Parse a json pointer.

        Json Pointers are defined in
        http://tools.ietf.org/html/draft-pbryan-zyp-json-pointer .
        The pointers use '/' for separation between object attributes, such
        that '/A/B' would evaluate to C in {"A": {"B": "C"}}. A '/' character
        in an attribute name is encoded as "~1" and a '~' character is encoded
        as "~0".
        """
        self._validate_json_pointer(pointer)
        return pointer.lstrip('/').replace('~1', '/').replace('~0', '~')

    def _validate_json_pointer(self, pointer):
        """ Validate a json pointer.

        We only accept a limited form of json pointers. Specifically, we do
        not allow multiple levels of indirection, so there can only be one '/'
        in the pointer, located at the start of the string.
        """
        if not pointer.startswith('/'):
            msg = _('Pointer `%s` does not start with "/".' % pointer)
            raise webob.exc.HTTPBadRequest(explanation=msg)
        if '/' in pointer[1:]:
            msg = _('Pointer `%s` contains more than one "/".' % pointer)
            raise webob.exc.HTTPBadRequest(explanation=msg)
        if re.match('~[^01]', pointer):
            msg = _('Pointer `%s` contains "~" not part of'
                    ' a recognized escape sequence.' % pointer)
            raise webob.exc.HTTPBadRequest(explanation=msg)

    def _get_change_value(self, raw_change, op):
        if 'value' not in raw_change:
            msg = _('Operation "%s" requires a member named "value".')
            raise webob.exc.HTTPBadRequest(explanation=msg % op)
        return raw_change['value']

    def _validate_change(self, change):
        if change['op'] == 'delete':
            return
        partial_image = {change['path'][-1]: change['value']}
        try:
            self.schema.validate(partial_image)
        except exception.InvalidObject as e:
            raise webob.exc.HTTPBadRequest(explanation=unicode(e))

    def update(self, request):
        changes = []
        valid_content_types = [
            'application/openstack-images-v2.0-json-patch'
        ]
        if request.content_type not in valid_content_types:
            headers = {'Accept-Patch': ','.join(valid_content_types)}
            raise webob.exc.HTTPUnsupportedMediaType(headers=headers)
        body = self._get_request_body(request)
        if not isinstance(body, list):
            msg = _('Request body must be a JSON array of operation objects.')
            raise webob.exc.HTTPBadRequest(explanation=msg)
        for raw_change in body:
            if not isinstance(raw_change, dict):
                msg = _('Operations must be JSON objects.')
                raise webob.exc.HTTPBadRequest(explanation=msg)
            op = self._get_change_operation(raw_change)
            path = self._get_change_path(raw_change, op)
            change = {'op': op, 'path': path}
            if not op == 'remove':
                change['value'] = self._get_change_value(raw_change, op)
                self._validate_change(change)
                if change['path'] == ['visibility']:
                    change['path'] = ['is_public']
                    change['value'] = change['value'] == 'public'
            changes.append(change)
        return {'changes': changes}

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
        body = json.dumps(self._format_image(image), ensure_ascii=False)
        response.unicode_body = unicode(body)
        response.content_type = 'application/json'
        response.location = self._get_image_href(image)

    def show(self, response, image):
        body = json.dumps(self._format_image(image), ensure_ascii=False)
        response.unicode_body = unicode(body)
        response.content_type = 'application/json'

    def update(self, response, image):
        body = json.dumps(self._format_image(image), ensure_ascii=False)
        response.unicode_body = unicode(body)
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
        response.unicode_body = unicode(json.dumps(body, ensure_ascii=False))
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
