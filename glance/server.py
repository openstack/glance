# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 OpenStack LLC.
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
=================
Glance API Server
=================

Configuration Options
---------------------

   `default_store`: When no x-image-meta-store header is sent for a
                    `POST /images` request, this store will be used
                    for storing the image data. Default: 'file'

"""

import json
import logging

import routes
from webob import Response
from webob.exc import (HTTPNotFound,
                       HTTPConflict,
                       HTTPBadRequest)

from glance.common import exception
from glance.common import flags
from glance.common import wsgi
from glance.store import (get_from_backend,
                          delete_from_backend,
                          get_store_from_location,
                          get_backend_class,
                          UnsupportedBackend)
from glance import registry
from glance import util


FLAGS = flags.FLAGS


class Controller(wsgi.Controller):

    """
    Main WSGI application controller for Glance.

    The Glance API is a RESTful web service for image data. The API
    is as follows::

        GET /images -- Returns a set of brief metadata about images
        GET /images/detail -- Returns a set of detailed metadata about
                              images
        HEAD /images/<ID> -- Return metadata about an image with id <ID>
        GET /images/<ID> -- Return image data for image with id <ID>
        POST /images -- Store image data and return metadata about the
                        newly-stored image
        PUT /images/<ID> -- Update image metadata (not image data, since
                            image data is immutable once stored)
        DELETE /images/<ID> -- Delete the image with id <ID>
    """

    def index(self, req):
        """
        Returns the following information for all public, available images:

            * id -- The opaque image identifier
            * name -- The name of the image
            * size -- Size of image data in bytes
            * type -- One of 'kernel', 'ramdisk', 'raw', or 'machine'

        :param request: The WSGI/Webob Request object
        :retval The response body is a mapping of the following form::

            {'images': [
                {'id': <ID>,
                 'name': <NAME>,
                 'size': <SIZE>,
                 'type': <TYPE>}, ...
            ]}
        """
        images = registry.get_images_list()
        return dict(images=images)

    def detail(self, req):
        """
        Returns detailed information for all public, available images

        :param request: The WSGI/Webob Request object
        :retval The response body is a mapping of the following form::

            {'images': [
                {'id': <ID>,
                 'name': <NAME>,
                 'size': <SIZE>,
                 'type': <TYPE>,
                 'store': <STORE>,
                 'status': <STATUS>,
                 'created_at': <TIMESTAMP>,
                 'updated_at': <TIMESTAMP>,
                 'deleted_at': <TIMESTAMP>|<NONE>,
                 'properties': {'distro': 'Ubuntu 10.04 LTS', ...}}, ...
            ]}
        """
        images = registry.get_images_detail()
        return dict(images=images)

    def meta(self, req, id):
        """
        Returns metadata about an image in the HTTP headers of the
        response object

        :param request: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :raises HTTPNotFound if image metadata is not available to user
        """
        image = self.get_image_meta_or_404(req, id)

        res = Response(request=req)
        util.inject_image_meta_into_headers(res, image)

        return req.get_response(res)

    def show(self, req, id):
        """
        Returns an iterator as a Response object that
        can be used to retrieve an image's data. The
        content-type of the response is the content-type
        of the image, or application/octet-stream if none
        is known or found.

        :param request: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :raises HTTPNotFound if image is not available to user
        """
        image = self.get_image_meta_or_404(req, id)

        def image_iterator():
            chunks = get_from_backend(image['location'],
                                      expected_size=image['size'])

            for chunk in chunks:
                yield chunk

        res = Response(app_iter=image_iterator(),
                       content_type="text/plain")
        util.inject_image_meta_into_headers(res, image)
        return req.get_response(res)

    def create(self, req):
        """
        Adds a new image to Glance. The body of the request may be a
        mime-encoded image data. Metadata about the image is sent via
        HTTP Headers.

        If the metadata about the image does not include a location
        to find the image, or if the image location is not valid,
        the request body *must* be encoded as application/octet-stream
        and be the image data itself, otherwise an HTTPBadRequest is
        returned.

        Upon a successful save of the image data and metadata, a response
        containing metadata about the image is returned, including its
        opaque identifier.

        :param request: The WSGI/Webob Request object

        :raises HTTPBadRequest if no x-image-meta-location is missing
                and the request body is not application/octet-stream
                image data.
        """

        # Verify the request and headers before we generate a new id

        image_in_body = False
        image_store = None
        header_keys = [k.lower() for k in req.headers.keys()]
        if 'x-image-meta-location' not in header_keys:
            if ('content-type' not in header_keys or
                req.headers['content-type'] != 'application/octet-stream'):
                raise HTTPBadRequest("Image location was not specified in "
                                     "headers and the request body was not "
                                     "mime-encoded as application/"
                                     "octet-stream.", request=req)
            else:
                if 'x-image-meta-store' in header_keys:
                    image_store = req.headers['x-image-meta-store']
                image_status = 'pending'  # set to available when stored...
                image_in_body = True
        else:
            image_location = req.headers['x-image-meta-location']
            image_store = get_store_from_location(image_location)
            image_status = 'available'

        # If image is the request body, validate that the requested
        # or default store is capable of storing the image data...
        if not image_store:
            image_store = FLAGS.default_store
        if image_in_body:
            store = self.get_store_or_400(req, image_store)

        image_meta = util.get_image_meta_from_headers(req)

        image_meta['status'] = image_status
        image_meta['store'] = image_store
        try:
            image_meta = registry.add_image_metadata(image_meta)

            if image_in_body:
                try:
                    location = store.add(image_meta['id'], req.body_file)
                except exception.Duplicate, e:
                    logging.error("Error adding image to store: %s", str(e))
                    return HTTPConflict(str(e), request=req)
                image_meta['status'] = 'available'
                image_meta['location'] = location
                registry.update_image_metadata(image_meta['id'], image_meta)

            return dict(image=image_meta)

        except exception.Duplicate:
            msg = "An image with identifier %s already exists"\
                  % image_meta['id']
            logging.error(msg)
            return HTTPConflict(msg, request=req)
        except exception.Invalid:
            return HTTPBadRequest()

    def update(self, req, id):
        """
        Updates an existing image with the registry.

        :param request: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :retval Returns the updated image information as a mapping,

        """
        image = self.get_image_meta_or_404(req, id)

        image_data = json.loads(req.body)['image']
        updated_image = registry.update_image_metadata(id, image_data)
        return dict(image=updated_image)

    def delete(self, req, id):
        """
        Deletes the image and all its chunks from the Glance

        :param request: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :raises HttpBadRequest if image registry is invalid
        :raises HttpNotFound if image or any chunk is not available
        :raises HttpNotAuthorized if image or any chunk is not
                deleteable by the requesting user
        """
        image = self.get_image_meta_or_404(req, id)

        delete_from_backend(image['location'])

        registry.delete_image_metadata(id)

    def get_image_meta_or_404(self, request, id):
        """
        Grabs the image metadata for an image with a supplied
        identifier or raises an HTTPNotFound (404) response

        :param request: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :raises HTTPNotFound if image does not exist
        """
        try:
            return registry.get_image_metadata(id)
        except exception.NotFound:
            raise HTTPNotFound(body='Image not found',
                               request=request,
                               content_type='text/plain')

    def get_store_or_400(self, request, store_name):
        """
        Grabs the storage backend for the supplied store name
        or raises an HTTPBadRequest (400) response

        :param request: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :raises HTTPNotFound if image does not exist
        """
        try:
            return get_backend_class(store_name)
        except UnsupportedBackend:
            raise HTTPBadRequest(body='Requested store %s not available '
                                 'for storage on this Glance node'
                                 % store_name,
                                 request=request,
                                 content_type='text/plain')


class API(wsgi.Router):

    """WSGI entry point for all Glance API requests."""

    def __init__(self):
        mapper = routes.Mapper()
        mapper.resource("image", "images", controller=Controller(),
                       collection={'detail': 'GET'})
        mapper.connect("/", controller=Controller(), action="index")
        mapper.connect("/images/{id}", controller=Controller(), action="meta",
                       conditions=dict(method=["HEAD"]))
        super(API, self).__init__(mapper)
