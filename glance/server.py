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
from glance.common import wsgi
from glance.store import (get_from_backend,
                          delete_from_backend,
                          get_store_from_location,
                          get_backend_class,
                          UnsupportedBackend)
from glance import registry
from glance import utils


logger = logging.getLogger('glance.server')


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

    def __init__(self, options):
        self.options = options

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
        images = registry.get_images_list(self.options)
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
        images = registry.get_images_detail(self.options)
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
        utils.inject_image_meta_into_headers(res, image)

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
        utils.inject_image_meta_into_headers(res, image)
        return req.get_response(res)

    def _reserve(self, req):
        """
        Adds the image metadata to the registry and assigns
        an image identifier if one is not supplied in the request
        headers. Sets the image's status to `queued`

        :param request: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :raises HTTPConflict if image already exists
        :raises HTTPBadRequest if image metadata is not valid
        """
        image_meta = utils.get_image_meta_from_headers(req)
        image_meta['status'] = 'queued'

        # Ensure that the size attribute is set to zero for all
        # queued instances. The size will be set to a non-zero
        # value during upload
        image_meta['size'] = image_meta.get('size', 0)

        try:
            image_meta = registry.add_image_metadata(self.options,
                                                     image_meta)
            return image_meta
        except exception.Duplicate:
            msg = "An image with identifier %s already exists"\
                  % image_meta['id']
            logger.error(msg)
            raise HTTPConflict(msg, request=req, content_type="text/plain")
        except exception.Invalid, e:
            msg = ("Failed to reserve image. Got error: %(e)s" % locals())
            for line in msg.split('\n'):
                logger.error(line)
            raise HTTPBadRequest(msg, request=req, content_type="text/plain")

    def _upload(self, req, image_meta):
        """
        Uploads the payload of the request to a backend store in
        Glance. If the `x-image-meta-store` header is set, Glance
        will attempt to use that store, if not, Glance will use the
        store set by the flag `default_store`.

        :param request: The WSGI/Webob Request object
        :param image_meta: Mapping of metadata about image

        :raises HTTPConflict if image already exists
        :retval The location where the image was stored
        """
        content_type = req.headers.get('content-type', 'notset')
        if content_type != 'application/octet-stream':
            raise HTTPBadRequest(
                "Content-Type must be application/octet-stream")

        store_name = req.headers.get(
            'x-image-meta-store', self.options['default_store'])

        store = self.get_store_or_400(req, store_name)

        image_meta['status'] = 'saving'
        image_id = image_meta['id']
        logger.debug("Updating image metadata for image %s"
                     % image_id)
        registry.update_image_metadata(self.options,
                                       image_meta['id'],
                                       image_meta)

        try:
            logger.debug("Uploading image data for image %(image_id)s "
                         "to %(store_name)s store" % locals())
            location, size = store.add(image_meta['id'],
                                       req.body_file,
                                       self.options)
            # If size returned from store is different from size
            # already stored in registry, update the registry with
            # the new size of the image
            if image_meta.get('size', 0) != size:
                image_meta['size'] = size
                logger.debug("Updating image metadata for image %s"
                             % image_id)
                registry.update_image_metadata(self.options,
                                               image_meta['id'],
                                               image_meta)
            return location
        except exception.Duplicate, e:
            logger.error("Error adding image to store: %s", str(e))
            raise HTTPConflict(str(e), request=req)

    def _activate(self, req, image_meta, location):
        """
        Sets the image status to `active` and the image's location
        attribute.

        :param request: The WSGI/Webob Request object
        :param image_meta: Mapping of metadata about image
        :param location: Location of where Glance stored this image
        """
        image_meta['location'] = location
        image_meta['status'] = 'active'
        registry.update_image_metadata(self.options,
                                       image_meta['id'],
                                       image_meta)

    def _kill(self, req, image_meta):
        """
        Marks the image status to `killed`

        :param request: The WSGI/Webob Request object
        :param image_meta: Mapping of metadata about image
        """
        image_meta['status'] = 'killed'
        registry.update_image_metadata(self.options,
                                       image_meta['id'],
                                       image_meta)

    def _safe_kill(self, req, image_meta):
        """
        Mark image killed without raising exceptions if it fails.

        Since _kill is meant to be called from exceptions handlers, it should
        not raise itself, rather it should just log its error.

        :param request: The WSGI/Webob Request object
        """
        try:
            self._kill(req, image_meta)
        except Exception, e:
            logger.error("Unable to kill image %s: %s",
                          image_meta['id'], repr(e))

    def _upload_and_activate(self, req, image_meta):
        """
        Safely uploads the image data in the request payload
        and activates the image in the registry after a successful
        upload.

        :param request: The WSGI/Webob Request object
        :param image_meta: Mapping of metadata about image
        """
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

        if utils.has_body(req):
            self._upload_and_activate(req, image_meta)
        else:
            if 'x-image-meta-location' in req.headers:
                location = req.headers['x-image-meta-location']
                self._activate(req, image_meta, location)

        # APP states we should return a Location: header with the edit
        # URI of the resource newly-created.
        res = Response(request=req, body=json.dumps(dict(image=image_meta)),
                       content_type="text/plain")
        res.headers.add('Location', "/images/%s" % image_meta['id'])

        return req.get_response(res)

    def update(self, req, id):
        """
        Updates an existing image with the registry.

        :param request: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :retval Returns the updated image information as a mapping
        """
        has_body = utils.has_body(req)

        orig_image_meta = self.get_image_meta_or_404(req, id)
        orig_status = orig_image_meta['status']

        if has_body and orig_status != 'queued':
            raise HTTPConflict("Cannot upload to an unqueued image")

        new_image_meta = utils.get_image_meta_from_headers(req)
        try:
            image_meta = registry.update_image_metadata(self.options,
                                                        id,
                                                        new_image_meta)

            if has_body:
                self._upload_and_activate(req, image_meta)

            return dict(image=image_meta)
        except exception.Invalid, e:
            msg = ("Failed to update image metadata. Got error: %(e)s"
                   % locals())
            for line in msg.split('\n'):
                logger.error(line)
            raise HTTPBadRequest(msg, request=req, content_type="text/plain")

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

        registry.delete_image_metadata(self.options, id)

    def get_image_meta_or_404(self, request, id):
        """
        Grabs the image metadata for an image with a supplied
        identifier or raises an HTTPNotFound (404) response

        :param request: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :raises HTTPNotFound if image does not exist
        """
        try:
            return registry.get_image_metadata(self.options, id)
        except exception.NotFound:
            msg = "Image with identifier %s not found" % id
            logger.debug(msg)
            raise HTTPNotFound(msg, request=request,
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
            msg = ("Requested store %s not available on this Glance server"
                   % store_name)
            logger.error(msg)
            raise HTTPBadRequest(msg, request=request,
                                 content_type='text/plain')


class API(wsgi.Router):

    """WSGI entry point for all Glance API requests."""

    def __init__(self, options):
        self.options = options
        mapper = routes.Mapper()
        controller = Controller(options)
        mapper.resource("image", "images", controller=controller,
                       collection={'detail': 'GET'})
        mapper.connect("/", controller=controller, action="index")
        mapper.connect("/images/{id}", controller=controller, action="meta",
                       conditions=dict(method=["HEAD"]))
        super(API, self).__init__(mapper)


def app_factory(global_conf, **local_conf):
    """paste.deploy app factory for creating Glance API server apps"""
    conf = global_conf.copy()
    conf.update(local_conf)
    return API(conf)
