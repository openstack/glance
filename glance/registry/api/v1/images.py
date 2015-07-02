# Copyright 2010-2011 OpenStack Foundation
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

"""
Reference implementation registry server WSGI controller
"""

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import encodeutils
from oslo_utils import strutils
from oslo_utils import timeutils
from webob import exc

from glance.common import exception
from glance.common import utils
from glance.common import wsgi
import glance.db
from glance import i18n


LOG = logging.getLogger(__name__)
_ = i18n._
_LE = i18n._LE
_LI = i18n._LI
_LW = i18n._LW

CONF = cfg.CONF

DISPLAY_FIELDS_IN_INDEX = ['id', 'name', 'size',
                           'disk_format', 'container_format',
                           'checksum']

SUPPORTED_FILTERS = ['name', 'status', 'container_format', 'disk_format',
                     'min_ram', 'min_disk', 'size_min', 'size_max',
                     'changes-since', 'protected']

SUPPORTED_SORT_KEYS = ('name', 'status', 'container_format', 'disk_format',
                       'size', 'id', 'created_at', 'updated_at')

SUPPORTED_SORT_DIRS = ('asc', 'desc')

SUPPORTED_PARAMS = ('limit', 'marker', 'sort_key', 'sort_dir')


def _normalize_image_location_for_db(image_data):
    """
    This function takes the legacy locations field and the newly added
    location_data field from the image_data values dictionary which flows
    over the wire between the registry and API servers and converts it
    into the location_data format only which is then consumable by the
    Image object.

    :param image_data: a dict of values representing information in the image
    :return: a new image data dict
    """
    if 'locations' not in image_data and 'location_data' not in image_data:
        image_data['locations'] = None
        return image_data

    locations = image_data.pop('locations', [])
    location_data = image_data.pop('location_data', [])

    location_data_dict = {}
    for l in locations:
        location_data_dict[l] = {}
    for l in location_data:
        location_data_dict[l['url']] = {'metadata': l['metadata'],
                                        'status': l['status'],
                                        # Note(zhiyan): New location has no ID.
                                        'id': l['id'] if 'id' in l else None}

    # NOTE(jbresnah) preserve original order.  tests assume original order,
    # should that be defined functionality
    ordered_keys = locations[:]
    for ld in location_data:
        if ld['url'] not in ordered_keys:
            ordered_keys.append(ld['url'])

    location_data = []
    for loc in ordered_keys:
        data = location_data_dict[loc]
        if data:
            location_data.append({'url': loc,
                                  'metadata': data['metadata'],
                                  'status': data['status'],
                                  'id': data['id']})
        else:
            location_data.append({'url': loc,
                                  'metadata': {},
                                  'status': 'active',
                                  'id': None})

    image_data['locations'] = location_data
    return image_data


class Controller(object):

    def __init__(self):
        self.db_api = glance.db.get_api()

    def _get_images(self, context, filters, **params):
        """Get images, wrapping in exception if necessary."""
        # NOTE(markwash): for backwards compatibility, is_public=True for
        # admins actually means "treat me as if I'm not an admin and show me
        # all my images"
        if context.is_admin and params.get('is_public') is True:
            params['admin_as_user'] = True
            del params['is_public']
        try:
            return self.db_api.image_get_all(context, filters=filters,
                                             **params)
        except exception.ImageNotFound:
            LOG.warn(_LW("Invalid marker. Image %(id)s could not be "
                         "found.") % {'id': params.get('marker')})
            msg = _("Invalid marker. Image could not be found.")
            raise exc.HTTPBadRequest(explanation=msg)
        except exception.Forbidden:
            LOG.warn(_LW("Access denied to image %(id)s but returning "
                         "'not found'") % {'id': params.get('marker')})
            msg = _("Invalid marker. Image could not be found.")
            raise exc.HTTPBadRequest(explanation=msg)
        except Exception:
            LOG.exception(_LE("Unable to get images"))
            raise

    def index(self, req):
        """Return a basic filtered list of public, non-deleted images

        :param req: the Request object coming from the wsgi layer
        :retval a mapping of the following form::

            dict(images=[image_list])

        Where image_list is a sequence of mappings::

            {
            'id': <ID>,
            'name': <NAME>,
            'size': <SIZE>,
            'disk_format': <DISK_FORMAT>,
            'container_format': <CONTAINER_FORMAT>,
            'checksum': <CHECKSUM>
            }
        """
        params = self._get_query_params(req)
        images = self._get_images(req.context, **params)

        results = []
        for image in images:
            result = {}
            for field in DISPLAY_FIELDS_IN_INDEX:
                result[field] = image[field]
            results.append(result)

        LOG.debug("Returning image list")
        return dict(images=results)

    def detail(self, req):
        """Return a filtered list of public, non-deleted images in detail

        :param req: the Request object coming from the wsgi layer
        :retval a mapping of the following form::

            dict(images=[image_list])

        Where image_list is a sequence of mappings containing
        all image model fields.
        """
        params = self._get_query_params(req)

        images = self._get_images(req.context, **params)
        image_dicts = [make_image_dict(i) for i in images]
        LOG.debug("Returning detailed image list")
        return dict(images=image_dicts)

    def _get_query_params(self, req):
        """Extract necessary query parameters from http request.

        :param req: the Request object coming from the wsgi layer
        :retval dictionary of filters to apply to list of images
        """
        params = {
            'filters': self._get_filters(req),
            'limit': self._get_limit(req),
            'sort_key': [self._get_sort_key(req)],
            'sort_dir': [self._get_sort_dir(req)],
            'marker': self._get_marker(req),
        }

        if req.context.is_admin:
            # Only admin gets to look for non-public images
            params['is_public'] = self._get_is_public(req)

        for key, value in params.items():
            if value is None:
                del params[key]

        # Fix for LP Bug #1132294
        # Ensure all shared images are returned in v1
        params['member_status'] = 'all'
        return params

    def _get_filters(self, req):
        """Return a dictionary of query param filters from the request

        :param req: the Request object coming from the wsgi layer
        :retval a dict of key/value filters
        """
        filters = {}
        properties = {}

        for param in req.params:
            if param in SUPPORTED_FILTERS:
                filters[param] = req.params.get(param)
            if param.startswith('property-'):
                _param = param[9:]
                properties[_param] = req.params.get(param)

        if 'changes-since' in filters:
            isotime = filters['changes-since']
            try:
                filters['changes-since'] = timeutils.parse_isotime(isotime)
            except ValueError:
                raise exc.HTTPBadRequest(_("Unrecognized changes-since value"))

        if 'protected' in filters:
            value = self._get_bool(filters['protected'])
            if value is None:
                raise exc.HTTPBadRequest(_("protected must be True, or "
                                           "False"))

            filters['protected'] = value

        # only allow admins to filter on 'deleted'
        if req.context.is_admin:
            deleted_filter = self._parse_deleted_filter(req)
            if deleted_filter is not None:
                filters['deleted'] = deleted_filter
            elif 'changes-since' not in filters:
                filters['deleted'] = False
        elif 'changes-since' not in filters:
            filters['deleted'] = False

        if properties:
            filters['properties'] = properties

        return filters

    def _get_limit(self, req):
        """Parse a limit query param into something usable."""
        try:
            limit = int(req.params.get('limit', CONF.limit_param_default))
        except ValueError:
            raise exc.HTTPBadRequest(_("limit param must be an integer"))

        if limit < 0:
            raise exc.HTTPBadRequest(_("limit param must be positive"))

        return min(CONF.api_limit_max, limit)

    def _get_marker(self, req):
        """Parse a marker query param into something usable."""
        marker = req.params.get('marker', None)

        if marker and not utils.is_uuid_like(marker):
            msg = _('Invalid marker format')
            raise exc.HTTPBadRequest(explanation=msg)

        return marker

    def _get_sort_key(self, req):
        """Parse a sort key query param from the request object."""
        sort_key = req.params.get('sort_key', 'created_at')
        if sort_key is not None and sort_key not in SUPPORTED_SORT_KEYS:
            _keys = ', '.join(SUPPORTED_SORT_KEYS)
            msg = _("Unsupported sort_key. Acceptable values: %s") % (_keys,)
            raise exc.HTTPBadRequest(explanation=msg)
        return sort_key

    def _get_sort_dir(self, req):
        """Parse a sort direction query param from the request object."""
        sort_dir = req.params.get('sort_dir', 'desc')
        if sort_dir is not None and sort_dir not in SUPPORTED_SORT_DIRS:
            _keys = ', '.join(SUPPORTED_SORT_DIRS)
            msg = _("Unsupported sort_dir. Acceptable values: %s") % (_keys,)
            raise exc.HTTPBadRequest(explanation=msg)
        return sort_dir

    def _get_bool(self, value):
        value = value.lower()
        if value == 'true' or value == '1':
            return True
        elif value == 'false' or value == '0':
            return False

        return None

    def _get_is_public(self, req):
        """Parse is_public into something usable."""
        is_public = req.params.get('is_public', None)

        if is_public is None:
            # NOTE(vish): This preserves the default value of showing only
            #             public images.
            return True
        elif is_public.lower() == 'none':
            return None

        value = self._get_bool(is_public)
        if value is None:
            raise exc.HTTPBadRequest(_("is_public must be None, True, or "
                                       "False"))

        return value

    def _parse_deleted_filter(self, req):
        """Parse deleted into something usable."""
        deleted = req.params.get('deleted')
        if deleted is None:
            return None
        return strutils.bool_from_string(deleted)

    def show(self, req, id):
        """Return data about the given image id."""
        try:
            image = self.db_api.image_get(req.context, id)
            msg = "Successfully retrieved image %(id)s" % {'id': id}
            LOG.debug(msg)
        except exception.ImageNotFound:
            msg = _LI("Image %(id)s not found") % {'id': id}
            LOG.info(msg)
            raise exc.HTTPNotFound()
        except exception.Forbidden:
            # If it's private and doesn't belong to them, don't let on
            # that it exists
            msg = _LI("Access denied to image %(id)s but returning"
                      " 'not found'") % {'id': id}
            LOG.info(msg)
            raise exc.HTTPNotFound()
        except Exception:
            LOG.exception(_LE("Unable to show image %s") % id)
            raise

        return dict(image=make_image_dict(image))

    @utils.mutating
    def delete(self, req, id):
        """Deletes an existing image with the registry.

        :param req: wsgi Request object
        :param id:  The opaque internal identifier for the image

        :retval Returns 200 if delete was successful, a fault if not. On
        success, the body contains the deleted image information as a mapping.
        """
        try:
            deleted_image = self.db_api.image_destroy(req.context, id)
            msg = _LI("Successfully deleted image %(id)s") % {'id': id}
            LOG.info(msg)
            return dict(image=make_image_dict(deleted_image))
        except exception.ForbiddenPublicImage:
            msg = _LI("Delete denied for public image %(id)s") % {'id': id}
            LOG.info(msg)
            raise exc.HTTPForbidden()
        except exception.Forbidden:
            # If it's private and doesn't belong to them, don't let on
            # that it exists
            msg = _LI("Access denied to image %(id)s but returning"
                      " 'not found'") % {'id': id}
            LOG.info(msg)
            return exc.HTTPNotFound()
        except exception.ImageNotFound:
            msg = _LI("Image %(id)s not found") % {'id': id}
            LOG.info(msg)
            return exc.HTTPNotFound()
        except Exception:
            LOG.exception(_LE("Unable to delete image %s") % id)
            raise

    @utils.mutating
    def create(self, req, body):
        """Registers a new image with the registry.

        :param req: wsgi Request object
        :param body: Dictionary of information about the image

        :retval Returns the newly-created image information as a mapping,
                which will include the newly-created image's internal id
                in the 'id' field
        """
        image_data = body['image']

        # Ensure the image has a status set
        image_data.setdefault('status', 'active')

        # Set up the image owner
        if not req.context.is_admin or 'owner' not in image_data:
            image_data['owner'] = req.context.owner

        image_id = image_data.get('id')
        if image_id and not utils.is_uuid_like(image_id):
            msg = _LI("Rejecting image creation request for invalid image "
                      "id '%(bad_id)s'") % {'bad_id': image_id}
            LOG.info(msg)
            msg = _("Invalid image id format")
            return exc.HTTPBadRequest(explanation=msg)

        if 'location' in image_data:
            image_data['locations'] = [image_data.pop('location')]

        try:
            image_data = _normalize_image_location_for_db(image_data)
            image_data = self.db_api.image_create(req.context, image_data)
            image_data = dict(image=make_image_dict(image_data))
            msg = (_LI("Successfully created image %(id)s") %
                   image_data['image'])
            LOG.info(msg)
            return image_data
        except exception.Duplicate:
            msg = _("Image with identifier %s already exists!") % image_id
            LOG.warn(msg)
            return exc.HTTPConflict(msg)
        except exception.Invalid as e:
            msg = (_("Failed to add image metadata. "
                     "Got error: %s") % encodeutils.exception_to_unicode(e))
            LOG.error(msg)
            return exc.HTTPBadRequest(msg)
        except Exception:
            LOG.exception(_LE("Unable to create image %s"), image_id)
            raise

    @utils.mutating
    def update(self, req, id, body):
        """Updates an existing image with the registry.

        :param req: wsgi Request object
        :param body: Dictionary of information about the image
        :param id:  The opaque internal identifier for the image

        :retval Returns the updated image information as a mapping,
        """
        image_data = body['image']
        from_state = body.get('from_state', None)

        # Prohibit modification of 'owner'
        if not req.context.is_admin and 'owner' in image_data:
            del image_data['owner']

        if 'location' in image_data:
            image_data['locations'] = [image_data.pop('location')]

        purge_props = req.headers.get("X-Glance-Registry-Purge-Props", "false")
        try:
            LOG.debug("Updating image %(id)s with metadata: %(image_data)r",
                      {'id': id,
                       'image_data': {k: v for k, v in image_data.items()
                                      if k != 'locations'}})
            image_data = _normalize_image_location_for_db(image_data)
            if purge_props == "true":
                purge_props = True
            else:
                purge_props = False

            updated_image = self.db_api.image_update(req.context, id,
                                                     image_data,
                                                     purge_props=purge_props,
                                                     from_state=from_state)

            msg = _LI("Updating metadata for image %(id)s") % {'id': id}
            LOG.info(msg)
            return dict(image=make_image_dict(updated_image))
        except exception.Invalid as e:
            msg = (_("Failed to update image metadata. "
                     "Got error: %s") % encodeutils.exception_to_unicode(e))
            LOG.error(msg)
            return exc.HTTPBadRequest(msg)
        except exception.ImageNotFound:
            msg = _LI("Image %(id)s not found") % {'id': id}
            LOG.info(msg)
            raise exc.HTTPNotFound(body='Image not found',
                                   request=req,
                                   content_type='text/plain')
        except exception.ForbiddenPublicImage:
            msg = _LI("Update denied for public image %(id)s") % {'id': id}
            LOG.info(msg)
            raise exc.HTTPForbidden()
        except exception.Forbidden:
            # If it's private and doesn't belong to them, don't let on
            # that it exists
            msg = _LI("Access denied to image %(id)s but returning"
                      " 'not found'") % {'id': id}
            LOG.info(msg)
            raise exc.HTTPNotFound(body='Image not found',
                                   request=req,
                                   content_type='text/plain')
        except exception.Conflict as e:
            LOG.info(encodeutils.exception_to_unicode(e))
            raise exc.HTTPConflict(body='Image operation conflicts',
                                   request=req,
                                   content_type='text/plain')
        except Exception:
            LOG.exception(_LE("Unable to update image %s") % id)
            raise


def _limit_locations(image):
    locations = image.pop('locations', [])
    image['location_data'] = locations
    image['location'] = None
    for loc in locations:
        if loc['status'] == 'active':
            image['location'] = loc['url']
            break


def make_image_dict(image):
    """Create a dict representation of an image which we can use to
    serialize the image.
    """

    def _fetch_attrs(d, attrs):
        return {a: d[a] for a in attrs if a in d.keys()}

    # TODO(sirp): should this be a dict, or a list of dicts?
    # A plain dict is more convenient, but list of dicts would provide
    # access to created_at, etc
    properties = {p['name']: p['value'] for p in image['properties']
                  if not p['deleted']}

    image_dict = _fetch_attrs(image, glance.db.IMAGE_ATTRS)
    image_dict['properties'] = properties
    _limit_locations(image_dict)

    return image_dict


def create_resource():
    """Images resource factory method."""
    deserializer = wsgi.JSONRequestDeserializer()
    serializer = wsgi.JSONResponseSerializer()
    return wsgi.Resource(Controller(), deserializer, serializer)
