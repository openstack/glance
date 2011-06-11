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
/images endpoint for Glance v1 API
"""

import httplib
import json
import logging
import sys

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


logger = logging.getLogger('glance.api.v1.images')

SUPPORTED_FILTERS = ['name', 'status', 'container_format', 'disk_format',
                     'size_min', 'size_max']


class Controller(object):

    """
    WSGI controller for images resource in Glance v1 API

    The images resource API is a RESTful web service for image data. The API
    is as follows::

        GET /images -- Returns a set of brief metadata about images
        GET /images/detail -- Returns a set of detailed metadata about
                              images
        HEAD /images/<ID> -- Return metadata about an image with id <ID>
        GET /images/<ID> -- Return image data for image with id <ID>
        POST /images -- Store image data and return metadata about the
                        newly-stored image
        PUT /images/<ID> -- Update image metadata and/or upload image
                            data for a previously-reserved image
        DELETE /images/<ID> -- Delete the image with id <ID>
    """

    def __init__(self, options):
        self.options = options

    def index(self, req):
        """
        Returns the following information for all public, available images:

            * id -- The opaque image identifier
            * name -- The name of the image
            * disk_format -- The disk image format
            * container_format -- The "container" format of the image
            * checksum -- MD5 checksum of the image data
            * size -- Size of image data in bytes

        :param request: The WSGI/Webob Request object
        :retval The response body is a mapping of the following form::

            {'images': [
                {'id': <ID>,
                 'name': <NAME>,
                 'disk_format': <DISK_FORMAT>,
                 'container_format': <DISK_FORMAT>,
                 'checksum': <CHECKSUM>
                 'size': <SIZE>}, ...
            ]}
        """
        params = {'filters': self._get_filters(req)}

        if 'limit' in req.str_params:
            params['limit'] = req.str_params.get('limit')

        if 'marker' in req.str_params:
            params['marker'] = req.str_params.get('marker')

        images = registry.get_images_list(self.options, **params)
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
                 'disk_format': <DISK_FORMAT>,
                 'container_format': <CONTAINER_FORMAT>,
                 'checksum': <CHECKSUM>,
                 'store': <STORE>,
                 'status': <STATUS>,
                 'created_at': <TIMESTAMP>,
                 'updated_at': <TIMESTAMP>,
                 'deleted_at': <TIMESTAMP>|<NONE>,
                 'properties': {'distro': 'Ubuntu 10.04 LTS', ...}}, ...
            ]}
        """
        params = {'filters': self._get_filters(req)}

        if 'limit' in req.str_params:
            params['limit'] = req.str_params.get('limit')

        if 'marker' in req.str_params:
            params['marker'] = req.str_params.get('marker')

        images = registry.get_images_detail(self.options, **params)
        return dict(images=images)

    def _get_filters(self, req):
        """
        Return a dictionary of query param filters from the request

        :param req: the Request object coming from the wsgi layer
        :retval a dict of key/value filters
        """
        filters = {}
        for param in req.str_params:
            if param in SUPPORTED_FILTERS or param.startswith('property-'):
                filters[param] = req.str_params.get(param)

        return filters

    def meta(self, req, id):
        """
        Returns metadata about an image in the HTTP headers of the
        response object

        :param request: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :raises HTTPNotFound if image metadata is not available to user
        """
        return {
            'image_meta': self.get_image_meta_or_404(req, id),
        }

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
                                      expected_size=image['size'],
                                      options=self.options)

            for chunk in chunks:
                yield chunk

        return {
            'image_iterator': image_iterator(),
            'image_meta': image,
        }

    def _reserve(self, req, image_meta):
        """
        Adds the image metadata to the registry and assigns
        an image identifier if one is not supplied in the request
        headers. Sets the image's status to `queued`

        :param request: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :raises HTTPConflict if image already exists
        :raises HTTPBadRequest if image metadata is not valid
        """
        if 'location' in image_meta and image_meta['location'] is not None:
            store = get_store_from_location(image_meta['location'])
            # check the store exists before we hit the registry, but we
            # don't actually care what it is at this point
            self.get_store_or_400(req, store)

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
        try:
            req.get_content_type('application/octet-stream')
        except exception.InvalidContentType:
            msg = "Content-Type must be application/octet-stream"
            logger.error(msg)
            raise HTTPBadRequest(msg)

        store_name = req.headers.get(
            'x-image-meta-store', self.options['default_store'])

        store = self.get_store_or_400(req, store_name)

        image_id = image_meta['id']
        logger.debug("Setting image %s to status 'saving'" % image_id)
        registry.update_image_metadata(self.options, image_id,
                                       {'status': 'saving'})
        try:
            logger.debug("Uploading image data for image %(image_id)s "
                         "to %(store_name)s store" % locals())
            location, size, checksum = store.add(image_meta['id'],
                                                 req.body_file,
                                                 self.options)

            # Verify any supplied checksum value matches checksum
            # returned from store when adding image
            supplied_checksum = image_meta.get('checksum')
            if supplied_checksum and supplied_checksum != checksum:
                msg = ("Supplied checksum (%(supplied_checksum)s) and "
                       "checksum generated from uploaded image "
                       "(%(checksum)s) did not match. Setting image "
                       "status to 'killed'.") % locals()
                logger.error(msg)
                self._safe_kill(req, image_id)
                raise HTTPBadRequest(msg, content_type="text/plain",
                                     request=req)

            # Update the database with the checksum returned
            # from the backend store
            logger.debug("Updating image %(image_id)s data. "
                         "Checksum set to %(checksum)s, size set "
                         "to %(size)d" % locals())
            registry.update_image_metadata(self.options, image_id,
                                           {'checksum': checksum,
                                            'size': size})

            return location

        except exception.Duplicate, e:
            msg = ("Attempt to upload duplicate image: %s") % str(e)
            logger.error(msg)
            self._safe_kill(req, image_id)
            raise HTTPConflict(msg, request=req)

        except Exception, e:
            msg = ("Error uploading image: %s") % str(e)
            logger.error(msg)
            self._safe_kill(req, image_id)
            raise HTTPBadRequest(msg, request=req)

    def _activate(self, req, image_id, location):
        """
        Sets the image status to `active` and the image's location
        attribute.

        :param request: The WSGI/Webob Request object
        :param image_meta: Mapping of metadata about image
        :param location: Location of where Glance stored this image
        """
        image_meta = {}
        image_meta['location'] = location
        image_meta['status'] = 'active'
        return registry.update_image_metadata(self.options,
                                       image_id,
                                       image_meta)

    def _kill(self, req, image_id):
        """
        Marks the image status to `killed`

        :param request: The WSGI/Webob Request object
        :param image_id: Opaque image identifier
        """
        registry.update_image_metadata(self.options,
                                       image_id,
                                       {'status': 'killed'})

    def _safe_kill(self, req, image_id):
        """
        Mark image killed without raising exceptions if it fails.

        Since _kill is meant to be called from exceptions handlers, it should
        not raise itself, rather it should just log its error.

        :param request: The WSGI/Webob Request object
        :param image_id: Opaque image identifier
        """
        try:
            self._kill(req, image_id)
        except Exception, e:
            logger.error("Unable to kill image %s: %s",
                          image_id, repr(e))

    def _upload_and_activate(self, req, image_meta):
        """
        Safely uploads the image data in the request payload
        and activates the image in the registry after a successful
        upload.

        :param request: The WSGI/Webob Request object
        :param image_meta: Mapping of metadata about image

        :retval Mapping of updated image data
        """
        image_id = image_meta['id']
        location = self._upload(req, image_meta)
        return self._activate(req, image_id, location)

    def create(self, req, image_meta, image_data):
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

        :raises HTTPBadRequest if x-image-meta-location is missing
                and the request body is not application/octet-stream
                image data.
        """
        image_meta = self._reserve(req, image_meta)
        image_id = image_meta['id']

        if image_data is not None:
            image_meta = self._upload_and_activate(req, image_meta)
        else:
            if 'location' in image_meta and image_meta['location'] is not None:
                location = image_meta['location']
                image_meta = self._activate(req, image_id, location)

        return {'image_meta': image_meta}

    def update(self, req, id, image_meta, image_data):
        """
        Updates an existing image with the registry.

        :param request: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :retval Returns the updated image information as a mapping
        """
        orig_image_meta = self.get_image_meta_or_404(req, id)
        orig_status = orig_image_meta['status']

        if image_data is not None and orig_status != 'queued':
            raise HTTPConflict("Cannot upload to an unqueued image")

        try:
            image_meta = registry.update_image_metadata(self.options, id,
                                                         image_meta, True)
            if image_data is not None:
                image_meta = self._upload_and_activate(req, image_meta)
        except exception.Invalid, e:
            msg = ("Failed to update image metadata. Got error: %(e)s"
                   % locals())
            for line in msg.split('\n'):
                logger.error(line)
            raise HTTPBadRequest(msg, request=req, content_type="text/plain")

        return {'image_meta': image_meta}

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

        # The image's location field may be None in the case
        # of a saving or queued image, therefore don't ask a backend
        # to delete the image if the backend doesn't yet store it.
        # See https://bugs.launchpad.net/glance/+bug/747799
        if image['location']:
            try:
                delete_from_backend(image['location'])
            except (UnsupportedBackend, exception.NotFound):
                msg = "Failed to delete image from store (%s). " + \
                      "Continuing with deletion from registry."
                logger.error(msg % (image['location'],))

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


class ImageDeserializer(wsgi.JSONRequestDeserializer):

    def create(self, request):
        result = {}
        result['image_meta'] = utils.get_image_meta_from_headers(request)
        data = request.body if self.has_body(request) else None
        result['image_data'] = data
        return result

    def update(self, request):
        result = {}
        result['image_meta'] = utils.get_image_meta_from_headers(request)
        data = request.body if self.has_body(request) else None
        result['image_data'] = data
        return result


class ImageSerializer(wsgi.JSONResponseSerializer):

    def _inject_location_header(self, response, image_meta):
        location = self._get_image_location(image_meta)
        response.headers.add('Location', location)

    def _inject_checksum_header(self, response, image_meta):
        response.headers.add('ETag', image_meta['checksum'])

    def _inject_image_meta_headers(self, response, image_meta):
        """
        Given a response and mapping of image metadata, injects
        the Response with a set of HTTP headers for the image
        metadata. Each main image metadata field is injected
        as a HTTP header with key 'x-image-meta-<FIELD>' except
        for the properties field, which is further broken out
        into a set of 'x-image-meta-property-<KEY>' headers

        :param response: The Webob Response object
        :param image_meta: Mapping of image metadata
        """
        headers = utils.image_meta_to_http_headers(image_meta)

        for k, v in headers.items():
            response.headers.add(k, v)

    def _get_image_location(self, image_meta):
        return "/v1/images/%s" % image_meta['id']

    def meta(self, result):
        image_meta = result['image_meta']
        response = Response()
        self._inject_image_meta_headers(response, image_meta)
        self._inject_location_header(response, image_meta)
        self._inject_checksum_header(response, image_meta)
        return response

    def show(self, result):
        image_meta = result['image_meta']

        response = Response(app_iter=result['image_iterator'])
        # Using app_iter blanks content-length, so we set it here...
        response.headers.add('Content-Length', image_meta['size'])
        response.headers.add('Content-Type', 'application/octet-stream')

        self._inject_image_meta_headers(response, image_meta)
        self._inject_location_header(response, image_meta)
        self._inject_checksum_header(response, image_meta)

        return response

    def update(self, result):
        image_meta = result['image_meta']
        response = Response()
        response.body = self.to_json(dict(image=image_meta))
        response.headers.add('Content-Type', 'application/json')
        self._inject_location_header(response, image_meta)
        self._inject_checksum_header(response, image_meta)
        return response

    def create(self, result):
        image_meta = result['image_meta']
        response = Response()
        response.status = httplib.CREATED
        response.headers.add('Content-Type', 'application/json')
        response.body = self.to_json(dict(image=image_meta))
        self._inject_location_header(response, image_meta)
        self._inject_checksum_header(response, image_meta)
        return response


def create_resource(options):
    deserializer = ImageDeserializer()
    serializer = ImageSerializer()
    return wsgi.Resource(deserializer, Controller(options), serializer)
