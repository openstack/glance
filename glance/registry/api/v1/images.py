# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack LLC.
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

import logging

from webob import exc

from glance.common import cfg
from glance.common import exception
from glance.common import utils
from glance.common import wsgi
from glance.registry.db import api as db_api


logger = logging.getLogger('glance.registry.api.v1.images')

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


class Controller(object):

    opts = [
        cfg.IntOpt('limit_param_default', default=25),
        cfg.IntOpt('api_limit_max', default=1000),
        ]

    def __init__(self, conf):
        self.conf = conf
        self.conf.register_opts(self.opts)
        db_api.configure_db(conf)

    def _get_images(self, context, **params):
        """
        Get images, wrapping in exception if necessary.
        """
        try:
            return db_api.image_get_all(context, **params)
        except exception.NotFound, e:
            msg = _("Invalid marker. Image could not be found.")
            raise exc.HTTPBadRequest(explanation=msg)

    def index(self, req):
        """
        Return a basic filtered list of public, non-deleted images

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
        return dict(images=results)

    def detail(self, req):
        """
        Return a filtered list of public, non-deleted images in detail

        :param req: the Request object coming from the wsgi layer
        :retval a mapping of the following form::

            dict(images=[image_list])

        Where image_list is a sequence of mappings containing
        all image model fields.
        """
        params = self._get_query_params(req)

        images = self._get_images(req.context, **params)
        image_dicts = [make_image_dict(i) for i in images]
        return dict(images=image_dicts)

    def _get_query_params(self, req):
        """
        Extract necessary query parameters from http request.

        :param req: the Request object coming from the wsgi layer
        :retval dictionary of filters to apply to list of images
        """
        params = {
            'filters': self._get_filters(req),
            'limit': self._get_limit(req),
            'sort_key': self._get_sort_key(req),
            'sort_dir': self._get_sort_dir(req),
            'marker': self._get_marker(req),
        }

        for key, value in params.items():
            if value is None:
                del params[key]

        return params

    def _get_filters(self, req):
        """
        Return a dictionary of query param filters from the request

        :param req: the Request object coming from the wsgi layer
        :retval a dict of key/value filters
        """
        filters = {}
        properties = {}

        if req.context.is_admin:
            # Only admin gets to look for non-public images
            filters['is_public'] = self._get_is_public(req)
        else:
            filters['is_public'] = True

        for param in req.str_params:
            if param in SUPPORTED_FILTERS:
                filters[param] = req.str_params.get(param)
            if param.startswith('property-'):
                _param = param[9:]
                properties[_param] = req.str_params.get(param)

        if 'changes-since' in filters:
            isotime = filters['changes-since']
            try:
                filters['changes-since'] = utils.parse_isotime(isotime)
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

        if len(properties) > 0:
            filters['properties'] = properties

        return filters

    def _get_limit(self, req):
        """Parse a limit query param into something usable."""
        try:
            limit = int(req.str_params.get('limit',
                                           self.conf.limit_param_default))
        except ValueError:
            raise exc.HTTPBadRequest(_("limit param must be an integer"))

        if limit < 0:
            raise exc.HTTPBadRequest(_("limit param must be positive"))

        return min(self.conf.api_limit_max, limit)

    def _get_marker(self, req):
        """Parse a marker query param into something usable."""
        marker = req.str_params.get('marker', None)

        if marker and not utils.is_uuid_like(marker):
            msg = _('Invalid marker format')
            raise exc.HTTPBadRequest(explanation=msg)

        return marker

    def _get_sort_key(self, req):
        """Parse a sort key query param from the request object."""
        sort_key = req.str_params.get('sort_key', None)
        if sort_key is not None and sort_key not in SUPPORTED_SORT_KEYS:
            _keys = ', '.join(SUPPORTED_SORT_KEYS)
            msg = _("Unsupported sort_key. Acceptable values: %s") % (_keys,)
            raise exc.HTTPBadRequest(explanation=msg)
        return sort_key

    def _get_sort_dir(self, req):
        """Parse a sort direction query param from the request object."""
        sort_dir = req.str_params.get('sort_dir', None)
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
        is_public = req.str_params.get('is_public', None)

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
        deleted = req.str_params.get('deleted')
        if deleted is None:
            return None
        return utils.bool_from_string(deleted)

    def show(self, req, id):
        """Return data about the given image id."""
        try:
            image = db_api.image_get(req.context, id)
        except exception.NotFound:
            raise exc.HTTPNotFound()
        except exception.NotAuthorized:
            # If it's private and doesn't belong to them, don't let on
            # that it exists
            msg = _("Access by %(user)s to image %(id)s "
                    "denied") % ({'user': req.context.user,
                    'id': id})
            logger.info(msg)
            raise exc.HTTPNotFound()

        return dict(image=make_image_dict(image))

    def delete(self, req, id):
        """
        Deletes an existing image with the registry.

        :param req: wsgi Request object
        :param id:  The opaque internal identifier for the image

        :retval Returns 200 if delete was successful, a fault if not.
        """
        if req.context.read_only:
            raise exc.HTTPForbidden()

        try:
            db_api.image_destroy(req.context, id)
        except exception.NotFound:
            return exc.HTTPNotFound()
        except exception.NotAuthorized:
            # If it's private and doesn't belong to them, don't let on
            # that it exists
            msg = _("Access by %(user)s to image %(id)s "
                    "denied") % ({'user': req.context.user,
                    'id': id})
            logger.info(msg)
            raise exc.HTTPNotFound()

    def create(self, req, body):
        """
        Registers a new image with the registry.

        :param req: wsgi Request object
        :param body: Dictionary of information about the image

        :retval Returns the newly-created image information as a mapping,
                which will include the newly-created image's internal id
                in the 'id' field
        """
        if req.context.read_only:
            raise exc.HTTPForbidden()

        image_data = body['image']

        # Ensure the image has a status set
        image_data.setdefault('status', 'active')

        # Set up the image owner
        if not req.context.is_admin or 'owner' not in image_data:
            image_data['owner'] = req.context.owner

        image_id = image_data.get('id')
        if image_id and not utils.is_uuid_like(image_id):
            msg = _("Invalid image id format")
            return exc.HTTPBadRequest(explanation=msg)

        try:
            image_data = db_api.image_create(req.context, image_data)
            return dict(image=make_image_dict(image_data))
        except exception.Duplicate:
            msg = (_("Image with identifier %s already exists!") % id)
            logger.error(msg)
            return exc.HTTPConflict(msg)
        except exception.Invalid, e:
            msg = (_("Failed to add image metadata. "
                     "Got error: %(e)s") % locals())
            logger.error(msg)
            return exc.HTTPBadRequest(msg)

    def update(self, req, id, body):
        """
        Updates an existing image with the registry.

        :param req: wsgi Request object
        :param body: Dictionary of information about the image
        :param id:  The opaque internal identifier for the image

        :retval Returns the updated image information as a mapping,
        """
        if req.context.read_only:
            raise exc.HTTPForbidden()

        image_data = body['image']

        # Prohibit modification of 'owner'
        if not req.context.is_admin and 'owner' in image_data:
            del image_data['owner']

        purge_props = req.headers.get("X-Glance-Registry-Purge-Props", "false")
        try:
            logger.debug(_("Updating image %(id)s with metadata: "
                           "%(image_data)r") % locals())
            if purge_props == "true":
                updated_image = db_api.image_update(req.context, id,
                                                    image_data, True)
            else:
                updated_image = db_api.image_update(req.context, id,
                                                    image_data)
            return dict(image=make_image_dict(updated_image))
        except exception.Invalid, e:
            msg = (_("Failed to update image metadata. "
                     "Got error: %(e)s") % locals())
            logger.error(msg)
            return exc.HTTPBadRequest(msg)
        except exception.NotFound:
            raise exc.HTTPNotFound(body='Image not found',
                               request=req,
                               content_type='text/plain')
        except exception.NotAuthorized:
            # If it's private and doesn't belong to them, don't let on
            # that it exists
            msg = _("Access by %(user)s to image %(id)s "
                    "denied") % ({'user': req.context.user,
                    'id': id})
            logger.info(msg)
            raise exc.HTTPNotFound(body='Image not found',
                               request=req,
                               content_type='text/plain')


def make_image_dict(image):
    """
    Create a dict representation of an image which we can use to
    serialize the image.
    """

    def _fetch_attrs(d, attrs):
        return dict([(a, d[a]) for a in attrs
                    if a in d.keys()])

    # TODO(sirp): should this be a dict, or a list of dicts?
    # A plain dict is more convenient, but list of dicts would provide
    # access to created_at, etc
    properties = dict((p['name'], p['value'])
                      for p in image['properties'] if not p['deleted'])

    image_dict = _fetch_attrs(image, db_api.IMAGE_ATTRS)

    image_dict['properties'] = properties
    return image_dict


def create_resource(conf):
    """Images resource factory method."""
    deserializer = wsgi.JSONRequestDeserializer()
    serializer = wsgi.JSONResponseSerializer()
    return wsgi.Resource(Controller(conf), deserializer, serializer)
