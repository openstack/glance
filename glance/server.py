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

    def _reserve(self, req):
        image_meta = util.get_image_meta_from_headers(req)
        image_meta['status'] = 'queued'

        try:
            image_meta = registry.add_image_metadata(image_meta)
            return image_meta
        except exception.Duplicate:
            msg = "An image with identifier %s already exists"\
                  % image_meta['id']
            logging.error(msg)
            raise HTTPConflict(msg, request=req)
        except exception.Invalid:
            raise HTTPBadRequest()

    def _upload(self, req, image_meta):
        content_type = req.headers.get('content-type', 'notset')
        if content_type != 'application/octet-stream':
            raise HTTPBadRequest(
                "Content-Type must be application/octet-stream")

        image_store = req.headers.get(
            'x-image-meta-store', FLAGS.default_store)

        store = self.get_store_or_400(req, image_store)

        image_meta['status'] = 'saving'
        registry.update_image_metadata(image_meta['id'], image_meta)

        try:
            location = store.add(image_meta['id'], req.body_file)
            return location
        except exception.Duplicate, e:
            logging.error("Error adding image to store: %s", str(e))
            raise HTTPConflict(str(e), request=req)

    def _activate(self, req, image_meta, location):
        image_meta['location'] = location
        image_meta['status'] = 'active'
        registry.update_image_metadata(image_meta['id'], image_meta)

    def _kill(self, req, image_meta):
        image_meta['status'] = 'killed'
        registry.update_image_metadata(image_meta['id'], image_meta)

    def _safe_kill(self, req, image_meta):
        """Mark image killed without raising exceptions if it fails.

        Since _kill is meant to be called from exceptions handlers, it should
        not raise itself, rather it should just log its error.
        """
        try:
            self._kill(req, image_meta)
        except Exception, e:
            logging.error("Unable to kill image %s: %s",
                          image_meta['id'], repr(e))

    def _upload_and_activate(self, req, image_meta):
        try:
            location = self._upload(req, image_meta)
            self._activate(req, image_meta, location)
        except Exception, e:
            # NOTE(sirp): _safe_kill uses httplib which, in turn, uses
            # Eventlet's GreenSocket. Eventlet subsequently clears exceptions
            # by calling `sys.exc_clear()`. This is why we have to `raise e`
            # instead of `raise`
            self._safe_kill(req, image_meta)
            raise e

    def create(self, req):
        """
        Adds a new image to Glance. Three scenarios exist when creating an
        image:

        1. If the image data is available for upload, create can be passed the
           image data as the request body and the metadata as the request
           headers. The image will initially be 'queued', during upload it
           will be in the 'saving' status, and then 'killed' or 'active'
           depending on whether the upload completed successfully.

        2. If the image data exists somewhere else, you can pass in the source
           using the x-image-meta-location header

        3. If the image data is not available yet, but you'd like reserve a
           spot for it, you can omit the data and a record will be created in
           the 'queued' state. This exists primarily to maintain backwards
           compatibility with OpenStack/Rackspace API semantics.

        The request body *must* be encoded as application/octet-stream,
        otherwise an HTTPBadRequest is returned.

        Upon a successful save of the image data and metadata, a response
        containing metadata about the image is returned, including its
        opaque identifier.

        :param request: The WSGI/Webob Request object

        :raises HTTPBadRequest if no x-image-meta-location is missing
                and the request body is not application/octet-stream
                image data.
        """
        image_meta = self._reserve(req)

        if req.body:
            self._upload_and_activate(req, image_meta)
        else:
            if 'x-image-meta-location' in req.headers:
                location = req.headers['x-image-meta-location']
                self._activate(req, image_meta, location)

        return dict(image=image_meta)

    def update(self, req, id):
        """
        Updates an existing image with the registry.

        :param request: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :retval Returns the updated image information as a mapping

        """
        orig_image_meta = self.get_image_meta_or_404(req, id)
        new_image_meta = util.get_image_meta_from_headers(req)

        if req.body and (orig_image_meta['status'] != 'queued'):
            raise HTTPConflict("Cannot upload to an unqueued image")

        image_meta = registry.update_image_metadata(id, new_image_meta)

        if req.body:
            self._upload_and_activate(req, image_meta)

        return dict(image=image_meta)

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
