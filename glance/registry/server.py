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

import json
import logging

import routes
from webob import exc

from glance.common import wsgi
from glance.common import exception
from glance.registry.db import api as db_api


logger = logging.getLogger('glance.registry.server')

DISPLAY_FIELDS_IN_INDEX = ['id', 'name', 'size',
                           'disk_format', 'container_format',
                           'checksum']

SUPPORTED_FILTERS = ['name', 'status', 'container_format', 'disk_format',
                     'size_min', 'size_max']

MAX_ITEM_LIMIT = 25


class Controller(object):
    """Controller for the reference implementation registry server"""

    def __init__(self, options):
        self.options = options
        db_api.configure_db(options)

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
        params = {
            'filters': self._get_filters(req),
            'limit': self._get_limit(req),
        }

        if 'marker' in req.str_params:
            params['marker'] = self._get_marker(req)

        images = db_api.image_get_all_public(None, **params)

        results = []
        for image in images:
            result = {}
            for field in DISPLAY_FIELDS_IN_INDEX:
                result[field] = image[field]
            results.append(result)
        return dict(images=results)

    def detail(self, req):
        """Return a filtered list of public, non-deleted images in detail

        :param req: the Request object coming from the wsgi layer
        :retval a mapping of the following form::

            dict(images=[image_list])

        Where image_list is a sequence of mappings containing
        all image model fields.

        """
        params = {
            'filters': self._get_filters(req),
            'limit': self._get_limit(req),
        }

        if 'marker' in req.str_params:
            params['marker'] = self._get_marker(req)

        images = db_api.image_get_all_public(None, **params)

        image_dicts = [make_image_dict(i) for i in images]
        return dict(images=image_dicts)

    def _get_filters(self, req):
        """Return a dictionary of query param filters from the request

        :param req: the Request object coming from the wsgi layer
        :retval a dict of key/value filters

        """
        filters = {}
        properties = {}

        for param in req.str_params:
            if param in SUPPORTED_FILTERS:
                filters[param] = req.str_params.get(param)
            if param.startswith('property-'):
                _param = param[9:]
                properties[_param] = req.str_params.get(param)

        if len(properties) > 0:
            filters['properties'] = properties

        return filters

    def _get_limit(self, req):
        """Parse a limit query param into something usable."""
        try:
            limit = int(req.str_params.get('limit', MAX_ITEM_LIMIT))
        except ValueError:
            raise exc.HTTPBadRequest("limit param must be an integer")

        if limit < 0:
            raise exc.HTTPBadRequest("limit param must be positive")

        return min(MAX_ITEM_LIMIT, limit)

    def _get_marker(self, req):
        """Parse a marker query param into something usable."""
        try:
            marker = int(req.str_params.get('marker', None))
        except ValueError:
            raise exc.HTTPBadRequest("marker param must be an integer")
        return marker

    def show(self, req, id):
        """Return data about the given image id."""
        try:
            image = db_api.image_get(None, id)
        except exception.NotFound:
            raise exc.HTTPNotFound()

        return dict(image=make_image_dict(image))

    def delete(self, req, id):
        """
        Deletes an existing image with the registry.

        :param req: Request body.  Ignored.
        :param id:  The opaque internal identifier for the image

        :retval Returns 200 if delete was successful, a fault if not.

        """
        context = None
        try:
            db_api.image_destroy(context, id)
        except exception.NotFound:
            return exc.HTTPNotFound()

    def create(self, req, body):
        """
        Registers a new image with the registry.

        :param req: Request body.  A JSON-ified dict of information about
                    the image.

        :retval Returns the newly-created image information as a mapping,
                which will include the newly-created image's internal id
                in the 'id' field

        """
        image_data = body['image']

        # Ensure the image has a status set
        image_data.setdefault('status', 'active')

        context = None
        try:
            image_data = db_api.image_create(context, image_data)
            return dict(image=make_image_dict(image_data))
        except exception.Duplicate:
            msg = ("Image with identifier %s already exists!" % id)
            logger.error(msg)
            return exc.HTTPConflict(msg)
        except exception.Invalid, e:
            msg = ("Failed to add image metadata. Got error: %(e)s" % locals())
            logger.error(msg)
            return exc.HTTPBadRequest(msg)

    def update(self, req, id, body):
        """Updates an existing image with the registry.

        :param req: Request body.  A JSON-ified dict of information about
                    the image.  This will replace the information in the
                    registry about this image
        :param id:  The opaque internal identifier for the image

        :retval Returns the updated image information as a mapping,

        """
        image_data = body['image']

        purge_props = req.headers.get("X-Glance-Registry-Purge-Props", "false")
        context = None
        try:
            logger.debug("Updating image %(id)s with metadata: %(image_data)r"
                         % locals())
            if purge_props == "true":
                updated_image = db_api.image_update(context, id, image_data,
                                                        True)
            else:
                updated_image = db_api.image_update(context, id, image_data)
            return dict(image=make_image_dict(updated_image))
        except exception.Invalid, e:
            msg = ("Failed to update image metadata. "
                   "Got error: %(e)s" % locals())
            logger.error(msg)
            return exc.HTTPBadRequest(msg)
        except exception.NotFound:
            raise exc.HTTPNotFound(body='Image not found',
                               request=req,
                               content_type='text/plain')


def create_resource(options):
    return wsgi.Resource(Controller(options))


class API(wsgi.Router):
    """WSGI entry point for all Registry requests."""

    def __init__(self, options):
        mapper = routes.Mapper()
        resource = create_resource(options)
        mapper.resource("image", "images", controller=resource,
                       collection={'detail': 'GET'})
        mapper.connect("/", controller=resource, action="index")
        super(API, self).__init__(mapper)


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


def app_factory(global_conf, **local_conf):
    """
    paste.deploy app factory for creating Glance reference implementation
    registry server apps
    """
    conf = global_conf.copy()
    conf.update(local_conf)
    return API(conf)
