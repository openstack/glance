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


class Controller(wsgi.Controller):
    """Controller for the reference implementation registry server"""

    def __init__(self, options):
        self.options = options
        db_api.configure_db(options)

    def index(self, req):
        """Return basic information for all public, non-deleted images

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
        images = db_api.image_get_all_public(None)
        results = []
        for image in images:
            result = {}
            for field in DISPLAY_FIELDS_IN_INDEX:
                result[field] = image[field]
            results.append(result)
        return dict(images=results)

    def detail(self, req):
        """Return detailed information for all public, non-deleted images

        :param req: the Request object coming from the wsgi layer
        :retval a mapping of the following form::

            dict(images=[image_list])

        Where image_list is a sequence of mappings containing
        all image model fields.

        """
        images = db_api.image_get_all_public(None)
        image_dicts = [make_image_dict(i) for i in images]
        return dict(images=image_dicts)

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

    def create(self, req):
        """
        Registers a new image with the registry.

        :param req: Request body.  A JSON-ified dict of information about
                    the image.

        :retval Returns the newly-created image information as a mapping,
                which will include the newly-created image's internal id
                in the 'id' field

        """
        image_data = json.loads(req.body)['image']

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

    def update(self, req, id):
        """Updates an existing image with the registry.

        :param req: Request body.  A JSON-ified dict of information about
                    the image.  This will replace the information in the
                    registry about this image
        :param id:  The opaque internal identifier for the image

        :retval Returns the updated image information as a mapping,

        """
        image_data = json.loads(req.body)['image']

        context = None
        try:
            logger.debug("Updating image %(id)s with metadata: %(image_data)r"
                         % locals())
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


class API(wsgi.Router):
    """WSGI entry point for all Registry requests."""

    def __init__(self, options):
        mapper = routes.Mapper()
        controller = Controller(options)
        mapper.resource("image", "images", controller=controller,
                       collection={'detail': 'GET'})
        mapper.connect("/", controller=controller, action="index")
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
