# Copyright 2012 OpenStack Foundation.
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

import re

from oslo.config import cfg
import six.moves.urllib.parse as urlparse
import webob.exc

from glance.api import policy
from glance.common import exception
from glance.common import location_strategy
from glance.common import utils
from glance.common import wsgi
import glance.db
import glance.gateway
import glance.notifier
from glance.openstack.common import jsonutils as json
import glance.openstack.common.log as logging
from glance.openstack.common import timeutils
import glance.schema
import glance.store

LOG = logging.getLogger(__name__)

CONF = cfg.CONF
CONF.import_opt('disk_formats', 'glance.common.config', group='image_format')
CONF.import_opt('container_formats', 'glance.common.config',
                group='image_format')


class ImagesController(object):
    def __init__(self, db_api=None, policy_enforcer=None, notifier=None,
                 store_api=None):
        self.db_api = db_api or glance.db.get_api()
        self.policy = policy_enforcer or policy.Enforcer()
        self.notifier = notifier or glance.notifier.Notifier()
        self.store_api = store_api or glance.store
        self.gateway = glance.gateway.Gateway(self.db_api, self.store_api,
                                              self.notifier, self.policy)

    @utils.mutating
    def create(self, req, image, extra_properties, tags):
        image_factory = self.gateway.get_image_factory(req.context)
        image_repo = self.gateway.get_repo(req.context)
        try:
            image = image_factory.new_image(extra_properties=extra_properties,
                                            tags=tags, **image)
            image_repo.add(image)
        except exception.DuplicateLocation as dup:
            raise webob.exc.HTTPBadRequest(explanation=dup.msg)
        except exception.Forbidden as e:
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.InvalidParameterValue as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        except exception.LimitExceeded as e:
            LOG.info(unicode(e))
            raise webob.exc.HTTPRequestEntityTooLarge(
                explanation=e.msg, request=req, content_type='text/plain')

        return image

    def index(self, req, marker=None, limit=None, sort_key='created_at',
              sort_dir='desc', filters=None, member_status='accepted'):
        result = {}
        if filters is None:
            filters = {}
        filters['deleted'] = False

        if limit is None:
            limit = CONF.limit_param_default
        limit = min(CONF.api_limit_max, limit)

        image_repo = self.gateway.get_repo(req.context)
        try:
            images = image_repo.list(marker=marker, limit=limit,
                                     sort_key=sort_key, sort_dir=sort_dir,
                                     filters=filters,
                                     member_status=member_status)
            if len(images) != 0 and len(images) == limit:
                result['next_marker'] = images[-1].image_id
        except (exception.NotFound, exception.InvalidSortKey,
                exception.InvalidFilterRangeValue) as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        except exception.Forbidden as e:
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        result['images'] = images
        return result

    def show(self, req, image_id):
        image_repo = self.gateway.get_repo(req.context)
        try:
            return image_repo.get(image_id)
        except exception.Forbidden as e:
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)

    @utils.mutating
    def update(self, req, image_id, changes):
        image_repo = self.gateway.get_repo(req.context)
        try:
            image = image_repo.get(image_id)

            for change in changes:
                change_method_name = '_do_%s' % change['op']
                assert hasattr(self, change_method_name)
                change_method = getattr(self, change_method_name)
                change_method(req, image, change)

            if changes:
                    image_repo.save(image)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except exception.Forbidden as e:
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.InvalidParameterValue as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        except exception.StorageQuotaFull as e:
            msg = (_("Denying attempt to upload image because it exceeds the ."
                     "quota: %s") % e)
            LOG.info(msg)
            raise webob.exc.HTTPRequestEntityTooLarge(
                explanation=msg, request=req, content_type='text/plain')
        except exception.LimitExceeded as e:
            LOG.info(unicode(e))
            raise webob.exc.HTTPRequestEntityTooLarge(
                explanation=e.msg, request=req, content_type='text/plain')

        return image

    def _do_replace(self, req, image, change):
        path = change['path']
        path_root = path[0]
        value = change['value']
        if path_root == 'locations':
            self._do_replace_locations(image, value)
        else:
            if hasattr(image, path_root):
                setattr(image, path_root, value)
            elif path_root in image.extra_properties:
                image.extra_properties[path_root] = value
            else:
                msg = _("Property %s does not exist.")
                raise webob.exc.HTTPConflict(msg % path_root)

    def _do_add(self, req, image, change):
        path = change['path']
        path_root = path[0]
        value = change['value']
        if path_root == 'locations':
            self._do_add_locations(image, path[1], value)
        else:
            if (hasattr(image, path_root) or
                    path_root in image.extra_properties):
                msg = _("Property %s already present.")
                raise webob.exc.HTTPConflict(msg % path_root)
            image.extra_properties[path_root] = value

    def _do_remove(self, req, image, change):
        path = change['path']
        path_root = path[0]
        if path_root == 'locations':
            self._do_remove_locations(image, path[1])
        else:
            if hasattr(image, path_root):
                msg = _("Property %s may not be removed.")
                raise webob.exc.HTTPForbidden(msg % path_root)
            elif path_root in image.extra_properties:
                del image.extra_properties[path_root]
            else:
                msg = _("Property %s does not exist.")
                raise webob.exc.HTTPConflict(msg % path_root)

    @utils.mutating
    def delete(self, req, image_id):
        image_repo = self.gateway.get_repo(req.context)
        try:
            image = image_repo.get(image_id)
            image.delete()
            image_repo.remove(image)
        except exception.Forbidden as e:
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            msg = (_("Failed to find image %(image_id)s to delete") %
                   {'image_id': image_id})
            LOG.info(msg)
            raise webob.exc.HTTPNotFound(explanation=msg)

    def _get_locations_op_pos(self, path_pos, max_pos, allow_max):
        if path_pos is None or max_pos is None:
            return None
        pos = max_pos if allow_max else max_pos - 1
        if path_pos.isdigit():
            pos = int(path_pos)
        elif path_pos != '-':
            return None
        if (not allow_max) and (pos not in range(max_pos)):
            return None
        return pos

    def _do_replace_locations(self, image, value):
        if len(image.locations) > 0 and len(value) > 0:
            msg = _("Cannot replace locations from a non-empty "
                    "list to a non-empty list.")
            raise webob.exc.HTTPBadRequest(explanation=msg)
        if len(value) == 0:
            # NOTE(zhiyan): this actually deletes the location
            # from the backend store.
            del image.locations[:]
            if image.status == 'active':
                image.status = 'queued'
        else:   # NOTE(zhiyan): len(image.locations) == 0
            try:
                image.locations = value
                if image.status == 'queued':
                    image.status = 'active'
            except (exception.BadStoreUri, exception.DuplicateLocation) as bse:
                raise webob.exc.HTTPBadRequest(explanation=bse.msg)
            except ValueError as ve:    # update image status failed.
                raise webob.exc.HTTPBadRequest(explanation=unicode(ve))

    def _do_add_locations(self, image, path_pos, value):
        pos = self._get_locations_op_pos(path_pos,
                                         len(image.locations), True)
        if pos is None:
            msg = _("Invalid position for adding a location.")
            raise webob.exc.HTTPBadRequest(explanation=msg)
        try:
            image.locations.insert(pos, value)
            if image.status == 'queued':
                image.status = 'active'
        except (exception.BadStoreUri, exception.DuplicateLocation) as bse:
            raise webob.exc.HTTPBadRequest(explanation=bse.msg)
        except ValueError as ve:    # update image status failed.
            raise webob.exc.HTTPBadRequest(explanation=unicode(ve))

    def _do_remove_locations(self, image, path_pos):
        pos = self._get_locations_op_pos(path_pos,
                                         len(image.locations), False)
        if pos is None:
            msg = _("Invalid position for removing a location.")
            raise webob.exc.HTTPBadRequest(explanation=msg)
        try:
            # NOTE(zhiyan): this actually deletes the location
            # from the backend store.
            image.locations.pop(pos)
        except Exception as e:
            raise webob.exc.HTTPInternalServerError(explanation=unicode(e))
        if (len(image.locations) == 0) and (image.status == 'active'):
            image.status = 'queued'


class RequestDeserializer(wsgi.JSONRequestDeserializer):

    _disallowed_properties = ['direct_url', 'self', 'file', 'schema']
    _readonly_properties = ['created_at', 'updated_at', 'status', 'checksum',
                            'size', 'virtual_size', 'direct_url', 'self',
                            'file', 'schema']
    _reserved_properties = ['owner', 'is_public', 'location', 'deleted',
                            'deleted_at']
    _base_properties = ['checksum', 'created_at', 'container_format',
                        'disk_format', 'id', 'min_disk', 'min_ram', 'name',
                        'size', 'virtual_size', 'status', 'tags',
                        'updated_at', 'visibility', 'protected']
    _path_depth_limits = {'locations': {'add': 2, 'remove': 2, 'replace': 1}}

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
                raise webob.exc.HTTPForbidden(explanation=unicode(msg))

    def create(self, request):
        body = self._get_request_body(request)
        self._check_allowed(body)
        try:
            self.schema.validate(body)
        except exception.InvalidObject as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        image = {}
        properties = body
        tags = properties.pop('tags', None)
        for key in self._base_properties:
            try:
                image[key] = properties.pop(key)
            except KeyError:
                pass
        return dict(image=image, extra_properties=properties, tags=tags)

    def _get_change_operation_d10(self, raw_change):
        try:
            return raw_change['op']
        except KeyError:
            msg = _("Unable to find '%s' in JSON Schema change") % 'op'
            raise webob.exc.HTTPBadRequest(explanation=msg)

    def _get_change_operation_d4(self, raw_change):
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

    def _get_change_path_d10(self, raw_change):
        try:
            return raw_change['path']
        except KeyError:
            msg = _("Unable to find '%s' in JSON Schema change") % 'path'
            raise webob.exc.HTTPBadRequest(explanation=msg)

    def _get_change_path_d4(self, raw_change, op):
        return raw_change[op]

    def _decode_json_pointer(self, pointer):
        """Parse a json pointer.

        Json Pointers are defined in
        http://tools.ietf.org/html/draft-pbryan-zyp-json-pointer .
        The pointers use '/' for separation between object attributes, such
        that '/A/B' would evaluate to C in {"A": {"B": "C"}}. A '/' character
        in an attribute name is encoded as "~1" and a '~' character is encoded
        as "~0".
        """
        self._validate_json_pointer(pointer)
        ret = []
        for part in pointer.lstrip('/').split('/'):
            ret.append(part.replace('~1', '/').replace('~0', '~').strip())
        return ret

    def _validate_json_pointer(self, pointer):
        """Validate a json pointer.

        We only accept a limited form of json pointers.
        """
        if not pointer.startswith('/'):
            msg = _('Pointer `%s` does not start with "/".') % pointer
            raise webob.exc.HTTPBadRequest(explanation=msg)
        if re.search('/\s*?/', pointer[1:]):
            msg = _('Pointer `%s` contains adjacent "/".') % pointer
            raise webob.exc.HTTPBadRequest(explanation=msg)
        if len(pointer) > 1 and pointer.endswith('/'):
            msg = _('Pointer `%s` end with "/".') % pointer
            raise webob.exc.HTTPBadRequest(explanation=msg)
        if pointer[1:].strip() == '/':
            msg = _('Pointer `%s` does not contains valid token.') % pointer
            raise webob.exc.HTTPBadRequest(explanation=msg)
        if re.search('~[^01]', pointer) or pointer.endswith('~'):
            msg = _('Pointer `%s` contains "~" not part of'
                    ' a recognized escape sequence.') % pointer
            raise webob.exc.HTTPBadRequest(explanation=msg)

    def _get_change_value(self, raw_change, op):
        if 'value' not in raw_change:
            msg = _('Operation "%s" requires a member named "value".')
            raise webob.exc.HTTPBadRequest(explanation=msg % op)
        return raw_change['value']

    def _validate_change(self, change):
        path_root = change['path'][0]
        if path_root in self._readonly_properties:
            msg = _("Attribute '%s' is read-only.") % path_root
            raise webob.exc.HTTPForbidden(explanation=unicode(msg))
        if path_root in self._reserved_properties:
            msg = _("Attribute '%s' is reserved.") % path_root
            raise webob.exc.HTTPForbidden(explanation=unicode(msg))

        if change['op'] == 'delete':
            return

        partial_image = None
        if len(change['path']) == 1:
            partial_image = {path_root: change['value']}
        elif ((path_root in _get_base_properties().keys()) and
              (_get_base_properties()[path_root].get('type', '') == 'array')):
            # NOTE(zhiyan): cient can use PATCH API to adding element to
            # the image's existing set property directly.
            # Such as: 1. using '/locations/N' path to adding a location
            #             to the image's 'locations' list at N position.
            #             (implemented)
            #          2. using '/tags/-' path to appending a tag to the
            #             image's 'tags' list at last. (Not implemented)
            partial_image = {path_root: [change['value']]}

        if partial_image:
            try:
                self.schema.validate(partial_image)
            except exception.InvalidObject as e:
                raise webob.exc.HTTPBadRequest(explanation=e.msg)

    def _validate_path(self, op, path):
        path_root = path[0]
        limits = self._path_depth_limits.get(path_root, {})
        if len(path) != limits.get(op, 1):
            msg = _("Invalid JSON pointer for this resource: "
                    "'/%s'") % '/'.join(path)
            raise webob.exc.HTTPBadRequest(explanation=unicode(msg))

    def _parse_json_schema_change(self, raw_change, draft_version):
        if draft_version == 10:
            op = self._get_change_operation_d10(raw_change)
            path = self._get_change_path_d10(raw_change)
        elif draft_version == 4:
            op = self._get_change_operation_d4(raw_change)
            path = self._get_change_path_d4(raw_change, op)
        else:
            msg = _('Unrecognized JSON Schema draft version')
            raise webob.exc.HTTPBadRequest(explanation=msg)

        path_list = self._decode_json_pointer(path)
        return op, path_list

    def update(self, request):
        changes = []
        content_types = {
            'application/openstack-images-v2.0-json-patch': 4,
            'application/openstack-images-v2.1-json-patch': 10,
        }
        if request.content_type not in content_types:
            headers = {'Accept-Patch':
                       ', '.join(sorted(content_types.keys()))}
            raise webob.exc.HTTPUnsupportedMediaType(headers=headers)

        json_schema_version = content_types[request.content_type]

        body = self._get_request_body(request)

        if not isinstance(body, list):
            msg = _('Request body must be a JSON array of operation objects.')
            raise webob.exc.HTTPBadRequest(explanation=msg)

        for raw_change in body:
            if not isinstance(raw_change, dict):
                msg = _('Operations must be JSON objects.')
                raise webob.exc.HTTPBadRequest(explanation=msg)

            (op, path) = self._parse_json_schema_change(raw_change,
                                                        json_schema_version)

            # NOTE(zhiyan): the 'path' is a list.
            self._validate_path(op, path)
            change = {'op': op, 'path': path}

            if not op == 'remove':
                change['value'] = self._get_change_value(raw_change, op)
                self._validate_change(change)

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
            msg = _('Invalid sort direction: %s') % sort_dir
            raise webob.exc.HTTPBadRequest(explanation=msg)

        return sort_dir

    def _validate_member_status(self, member_status):
        if member_status not in ['pending', 'accepted', 'rejected', 'all']:
            msg = _('Invalid status: %s') % member_status
            raise webob.exc.HTTPBadRequest(explanation=msg)

        return member_status

    def _get_filters(self, filters):
        visibility = filters.get('visibility')
        if visibility:
            if visibility not in ['public', 'private', 'shared']:
                msg = _('Invalid visibility value: %s') % visibility
                raise webob.exc.HTTPBadRequest(explanation=msg)

        return filters

    def index(self, request):
        params = request.params.copy()
        limit = params.pop('limit', None)
        marker = params.pop('marker', None)
        sort_dir = params.pop('sort_dir', 'desc')
        member_status = params.pop('member_status', 'accepted')

        # NOTE (flwang) To avoid using comma or any predefined chars to split
        # multiple tags, now we allow user specify multiple 'tag' parameters
        # in URL, such as v2/images?tag=x86&tag=64bit.
        tags = []
        while 'tag' in params:
            tags.append(params.pop('tag').strip())

        query_params = {
            'sort_key': params.pop('sort_key', 'created_at'),
            'sort_dir': self._validate_sort_dir(sort_dir),
            'filters': self._get_filters(params),
            'member_status': self._validate_member_status(member_status),
        }

        if marker is not None:
            query_params['marker'] = marker

        if limit is not None:
            query_params['limit'] = self._validate_limit(limit)

        if tags:
            query_params['filters']['tags'] = tags

        return query_params


class ResponseSerializer(wsgi.JSONResponseSerializer):
    def __init__(self, schema=None):
        super(ResponseSerializer, self).__init__()
        self.schema = schema or get_schema()

    def _get_image_href(self, image, subcollection=''):
        base_href = '/v2/images/%s' % image.image_id
        if subcollection:
            base_href = '%s/%s' % (base_href, subcollection)
        return base_href

    def _format_image(self, image):
        image_view = dict()
        try:
            image_view = dict(image.extra_properties)
            attributes = ['name', 'disk_format', 'container_format',
                          'visibility', 'size', 'virtual_size', 'status',
                          'checksum', 'protected', 'min_ram', 'min_disk',
                          'owner']
            for key in attributes:
                image_view[key] = getattr(image, key)
            image_view['id'] = image.image_id
            image_view['created_at'] = timeutils.isotime(image.created_at)
            image_view['updated_at'] = timeutils.isotime(image.updated_at)

            if CONF.show_multiple_locations:
                if image.locations:
                    image_view['locations'] = list(image.locations)
                else:
                    # NOTE (flwang): We will still show "locations": [] if
                    # image.locations is None to indicate it's allowed to show
                    # locations but it's just non-existent.
                    image_view['locations'] = []

            if CONF.show_image_direct_url and image.locations:
                # Choose best location configured strategy
                best_location = (
                    location_strategy.choose_best_location(image.locations))
                image_view['direct_url'] = best_location['url']

            image_view['tags'] = list(image.tags)
            image_view['self'] = self._get_image_href(image)
            image_view['file'] = self._get_image_href(image, 'file')
            image_view['schema'] = '/v2/schemas/image'
            image_view = self.schema.filter(image_view)  # domain
        except exception.Forbidden as e:
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        return image_view

    def create(self, response, image):
        response.status_int = 201
        self.show(response, image)
        response.location = self._get_image_href(image)

    def show(self, response, image):
        image_view = self._format_image(image)
        body = json.dumps(image_view, ensure_ascii=False)
        response.unicode_body = unicode(body)
        response.content_type = 'application/json'

    def update(self, response, image):
        image_view = self._format_image(image)
        body = json.dumps(image_view, ensure_ascii=False)
        response.unicode_body = unicode(body)
        response.content_type = 'application/json'

    def index(self, response, result):
        params = dict(response.request.params)
        params.pop('marker', None)
        query = urlparse.urlencode(params)
        body = {
            'images': [self._format_image(i) for i in result['images']],
            'first': '/v2/images',
            'schema': '/v2/schemas/images',
        }
        if query:
            body['first'] = '%s?%s' % (body['first'], query)
        if 'next_marker' in result:
            params['marker'] = result['next_marker']
            next_query = urlparse.urlencode(params)
            body['next'] = '/v2/images?%s' % next_query
        response.unicode_body = unicode(json.dumps(body, ensure_ascii=False))
        response.content_type = 'application/json'

    def delete(self, response, result):
        response.status_int = 204


def _get_base_properties():
    return {
        'id': {
            'type': 'string',
            'description': _('An identifier for the image'),
            'pattern': ('^([0-9a-fA-F]){8}-([0-9a-fA-F]){4}-([0-9a-fA-F]){4}'
                        '-([0-9a-fA-F]){4}-([0-9a-fA-F]){12}$'),
        },
        'name': {
            'type': 'string',
            'description': _('Descriptive name for the image'),
            'maxLength': 255,
        },
        'status': {
            'type': 'string',
            'description': _('Status of the image (READ-ONLY)'),
            'enum': ['queued', 'saving', 'active', 'killed',
                     'deleted', 'pending_delete'],
        },
        'visibility': {
            'type': 'string',
            'description': _('Scope of image accessibility'),
            'enum': ['public', 'private'],
        },
        'protected': {
            'type': 'boolean',
            'description': _('If true, image will not be deletable.'),
        },
        'checksum': {
            'type': 'string',
            'description': _('md5 hash of image contents. (READ-ONLY)'),
            'maxLength': 32,
        },
        'owner': {
            'type': 'string',
            'description': _('Owner of the image'),
            'maxLength': 255,
        },
        'size': {
            'type': 'integer',
            'description': _('Size of image file in bytes (READ-ONLY)'),
        },
        'virtual_size': {
            'type': 'integer',
            'description': _('Virtual size of image in bytes (READ-ONLY)'),
        },
        'container_format': {
            'type': 'string',
            'description': _('Format of the container'),
            'enum': CONF.image_format.container_formats,
        },
        'disk_format': {
            'type': 'string',
            'description': _('Format of the disk'),
            'enum': CONF.image_format.disk_formats,
        },
        'created_at': {
            'type': 'string',
            'description': _('Date and time of image registration'
                             ' (READ-ONLY)'),
            #TODO(bcwaldon): our jsonschema library doesn't seem to like the
            # format attribute, figure out why!
            #'format': 'date-time',
        },
        'updated_at': {
            'type': 'string',
            'description': _('Date and time of the last image modification'
                             ' (READ-ONLY)'),
            #'format': 'date-time',
        },
        'tags': {
            'type': 'array',
            'description': _('List of strings related to the image'),
            'items': {
                'type': 'string',
                'maxLength': 255,
            },
        },
        'direct_url': {
            'type': 'string',
            'description': _('URL to access the image file kept in external '
                             'store (READ-ONLY)'),
        },
        'min_ram': {
            'type': 'integer',
            'description': _('Amount of ram (in MB) required to boot image.'),
        },
        'min_disk': {
            'type': 'integer',
            'description': _('Amount of disk space (in GB) required to boot '
                             'image.'),
        },
        'self': {
            'type': 'string',
            'description': '(READ-ONLY)'
        },
        'file': {
            'type': 'string',
            'description': '(READ-ONLY)'
        },
        'schema': {
            'type': 'string',
            'description': '(READ-ONLY)'
        },
        'locations': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'url': {
                        'type': 'string',
                        'maxLength': 255,
                    },
                    'metadata': {
                        'type': 'object',
                    },
                },
                'required': ['url', 'metadata'],
            },
            'description': _('A set of URLs to access the image file kept in '
                             'external store'),
        },
    }


def _get_base_links():
    return [
        {'rel': 'self', 'href': '{self}'},
        {'rel': 'enclosure', 'href': '{file}'},
        {'rel': 'describedby', 'href': '{schema}'},
    ]


def get_schema(custom_properties=None):
    properties = _get_base_properties()
    links = _get_base_links()
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
