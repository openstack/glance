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
import traceback

import webob
from webob.exc import (HTTPNotFound,
                       HTTPConflict,
                       HTTPBadRequest,
                       HTTPForbidden,
                       HTTPNoContent,
                       HTTPUnauthorized)

from glance import api
from glance import image_cache
from glance.common import exception
from glance.common import notifier
from glance.common import wsgi
import glance.store
import glance.store.filesystem
import glance.store.http
import glance.store.s3
import glance.store.swift
from glance.store import (get_from_backend,
                          schedule_delete_from_backend,
                          get_store_from_location,
                          get_store_from_scheme,
                          UnsupportedBackend)
from glance import registry
from glance import utils


logger = logging.getLogger('glance.api.v1.images')

SUPPORTED_FILTERS = ['name', 'status', 'container_format', 'disk_format',
                     'size_min', 'size_max', 'is_public']

SUPPORTED_PARAMS = ('limit', 'marker', 'sort_key', 'sort_dir')


class Controller(api.BaseController):
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
        glance.store.create_stores(options)
        self.notifier = notifier.Notifier(options)

    def index(self, req):
        """
        Returns the following information for all public, available images:

            * id -- The opaque image identifier
            * name -- The name of the image
            * disk_format -- The disk image format
            * container_format -- The "container" format of the image
            * checksum -- MD5 checksum of the image data
            * size -- Size of image data in bytes

        :param req: The WSGI/Webob Request object
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
        params = self._get_query_params(req)
        try:
            images = registry.get_images_list(self.options, req.context,
                                              **params)
        except exception.Invalid, e:
            raise HTTPBadRequest(explanation="%s" % e)

        return dict(images=images)

    def detail(self, req):
        """
        Returns detailed information for all public, available images

        :param req: The WSGI/Webob Request object
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
        params = self._get_query_params(req)
        try:
            images = registry.get_images_detail(self.options, req.context,
                                                **params)
            # Strip out the Location attribute. Temporary fix for
            # LP Bug #755916. This information is still coming back
            # from the registry, since the API server still needs access
            # to it, however we do not return this potential security
            # information to the API end user...
            for image in images:
                del image['location']
        except exception.Invalid, e:
            raise HTTPBadRequest(explanation="%s" % e)
        return dict(images=images)

    def _get_query_params(self, req):
        """
        Extracts necessary query params from request.

        :param req: the WSGI Request object
        :retval dict of parameters that can be used by registry client
        """
        params = {'filters': self._get_filters(req)}
        for PARAM in SUPPORTED_PARAMS:
            if PARAM in req.str_params:
                params[PARAM] = req.str_params.get(PARAM)
        return params

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

        :param req: The WSGI/Webob Request object
        :param id: The opaque image identifier
        :retval similar to 'show' method but without image_data

        :raises HTTPNotFound if image metadata is not available to user
        """
        return {
            'image_meta': self.get_image_meta_or_404(req, id),
        }

    def show(self, req, id):
        """
        Returns an iterator that can be used to retrieve an image's
        data along with the image metadata.

        :param req: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :raises HTTPNotFound if image is not available to user
        """
        image = self.get_active_image_meta_or_404(req, id)

        def get_from_store(image_meta):
            """Called if caching disabled"""
            try:
                location = image_meta['location']
                image_data, image_size = get_from_backend(location)
                image_meta["size"] = image_size or image_meta["size"]
            except exception.NotFound, e:
                raise HTTPNotFound(explanation="%s" % e)
            return image_data

        def get_from_cache(image, cache):
            """Called if cache hit"""
            with cache.open(image, "rb") as cache_file:
                chunks = utils.chunkiter(cache_file)
                for chunk in chunks:
                    yield chunk

        def get_from_store_tee_into_cache(image, cache):
            """Called if cache miss"""
            with cache.open(image, "wb") as cache_file:
                chunks = get_from_store(image)
                for chunk in chunks:
                    cache_file.write(chunk)
                    yield chunk

        cache = image_cache.ImageCache(self.options)
        if cache.enabled:
            if cache.hit(id):
                # hit
                logger.debug(_("image '%s' is a cache HIT"), id)
                image_iterator = get_from_cache(image, cache)
            else:
                # miss
                logger.debug(_("image '%s' is a cache MISS"), id)

                # Make sure we're not already prefetching or caching the image
                # that just generated the miss
                if cache.is_image_currently_prefetching(id):
                    logger.debug(_("image '%s' is already being prefetched,"
                                 " not tee'ing into the cache"), id)
                    image_iterator = get_from_store(image)
                elif cache.is_image_currently_being_written(id):
                    logger.debug(_("image '%s' is already being cached,"
                                 " not tee'ing into the cache"), id)
                    image_iterator = get_from_store(image)
                else:
                    # NOTE(sirp): If we're about to download and cache an
                    # image which is currently in the prefetch queue, just
                    # delete the queue items since we're caching it anyway
                    if cache.is_image_queued_for_prefetch(id):
                        cache.delete_queued_prefetch_image(id)

                    logger.debug(_("tee'ing image '%s' into cache"), id)
                    image_iterator = get_from_store_tee_into_cache(
                        image, cache)
        else:
            # disabled
            logger.debug(_("image cache DISABLED, retrieving image '%s'"
                         " from store"), id)
            image_iterator = get_from_store(image)

        return {
            'image_iterator': image_iterator,
            'image_meta': image,
        }

    def _reserve(self, req, image_meta):
        """
        Adds the image metadata to the registry and assigns
        an image identifier if one is not supplied in the request
        headers. Sets the image's status to `queued`.

        :param req: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :raises HTTPConflict if image already exists
        :raises HTTPBadRequest if image metadata is not valid
        """
        location = image_meta.get('location')
        if location:
            store = get_store_from_location(location)
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
                                                     req.context,
                                                     image_meta)
            return image_meta
        except exception.Duplicate:
            msg = (_("An image with identifier %s already exists")
                  % image_meta['id'])
            logger.error(msg)
            raise HTTPConflict(msg, request=req, content_type="text/plain")
        except exception.Invalid, e:
            msg = (_("Failed to reserve image. Got error: %(e)s") % locals())
            for line in msg.split('\n'):
                logger.error(line)
            raise HTTPBadRequest(msg, request=req, content_type="text/plain")
        except exception.NotAuthorized:
            msg = _("Not authorized to reserve image.")
            logger.error(msg)
            raise HTTPForbidden(msg, request=req,
                                content_type="text/plain")

    def _upload(self, req, image_meta):
        """
        Uploads the payload of the request to a backend store in
        Glance. If the `x-image-meta-store` header is set, Glance
        will attempt to use that store, if not, Glance will use the
        store set by the flag `default_store`.

        :param req: The WSGI/Webob Request object
        :param image_meta: Mapping of metadata about image

        :raises HTTPConflict if image already exists
        :retval The location where the image was stored
        """
        try:
            req.get_content_type('application/octet-stream')
        except exception.InvalidContentType:
            self._safe_kill(req, image_meta['id'])
            msg = _("Content-Type must be application/octet-stream")
            logger.error(msg)
            raise HTTPBadRequest(explanation=msg)

        store_name = req.headers.get('x-image-meta-store',
                                     self.options['default_store'])

        store = self.get_store_or_400(req, store_name)

        image_id = image_meta['id']
        logger.debug(_("Setting image %s to status 'saving'"), image_id)
        registry.update_image_metadata(self.options, req.context, image_id,
                                       {'status': 'saving'})
        try:
            logger.debug(_("Uploading image data for image %(image_id)s "
                         "to %(store_name)s store"), locals())
            if req.content_length:
                image_size = int(req.content_length)
            elif 'x-image-meta-size' in req.headers:
                image_size = int(req.headers['x-image-meta-size'])
            else:
                logger.debug(_("Got request with no content-length and no "
                               "x-image-meta-size header"))
                image_size = 0
            location, size, checksum = store.add(image_meta['id'],
                                                 req.body_file,
                                                 image_size)

            # Verify any supplied checksum value matches checksum
            # returned from store when adding image
            supplied_checksum = image_meta.get('checksum')
            if supplied_checksum and supplied_checksum != checksum:
                msg = _("Supplied checksum (%(supplied_checksum)s) and "
                       "checksum generated from uploaded image "
                       "(%(checksum)s) did not match. Setting image "
                       "status to 'killed'.") % locals()
                logger.error(msg)
                self._safe_kill(req, image_id)
                raise HTTPBadRequest(msg, content_type="text/plain",
                                     request=req)

            # Update the database with the checksum returned
            # from the backend store
            logger.debug(_("Updating image %(image_id)s data. "
                         "Checksum set to %(checksum)s, size set "
                         "to %(size)d"), locals())
            registry.update_image_metadata(self.options, req.context,
                                           image_id,
                                           {'checksum': checksum,
                                            'size': size})
            self.notifier.info('image.upload', image_meta)

            return location

        except exception.Duplicate, e:
            msg = _("Attempt to upload duplicate image: %s") % e
            logger.error(msg)
            self._safe_kill(req, image_id)
            self.notifier.error('image.upload', msg)
            raise HTTPConflict(msg, request=req)

        except exception.NotAuthorized, e:
            msg = _("Unauthorized upload attempt: %s") % e
            logger.error(msg)
            self._safe_kill(req, image_id)
            self.notifier.error('image.upload', msg)
            raise HTTPForbidden(msg, request=req,
                                content_type='text/plain')

        except Exception, e:
            tb_info = traceback.format_exc()
            logger.error(tb_info)

            self._safe_kill(req, image_id)

            msg = _("Error uploading image: (%(class_name)s): "
                    "%(exc)s") % ({'class_name': e.__class__.__name__,
                    'exc': str(e)})

            self.notifier.error('image.upload', msg)
            raise HTTPBadRequest(msg, request=req)

    def _activate(self, req, image_id, location):
        """
        Sets the image status to `active` and the image's location
        attribute.

        :param req: The WSGI/Webob Request object
        :param image_id: Opaque image identifier
        :param location: Location of where Glance stored this image
        """
        image_meta = {}
        image_meta['location'] = location
        image_meta['status'] = 'active'
        return registry.update_image_metadata(self.options,
                                       req.context,
                                       image_id,
                                       image_meta)

    def _kill(self, req, image_id):
        """
        Marks the image status to `killed`.

        :param req: The WSGI/Webob Request object
        :param image_id: Opaque image identifier
        """
        registry.update_image_metadata(self.options,
                                       req.context,
                                       image_id,
                                       {'status': 'killed'})

    def _safe_kill(self, req, image_id):
        """
        Mark image killed without raising exceptions if it fails.

        Since _kill is meant to be called from exceptions handlers, it should
        not raise itself, rather it should just log its error.

        :param req: The WSGI/Webob Request object
        :param image_id: Opaque image identifier
        """
        try:
            self._kill(req, image_id)
        except Exception, e:
            logger.error(_("Unable to kill image %(id)s: "
                           "%(exc)s") % ({'id': image_id,
                           'exc': repr(e)}))

    def _upload_and_activate(self, req, image_meta):
        """
        Safely uploads the image data in the request payload
        and activates the image in the registry after a successful
        upload.

        :param req: The WSGI/Webob Request object
        :param image_meta: Mapping of metadata about image

        :retval Mapping of updated image data
        """
        image_id = image_meta['id']
        # This is necessary because of a bug in Webob 1.0.2 - 1.0.7
        # See: https://bitbucket.org/ianb/webob/
        # issue/12/fix-for-issue-6-broke-chunked-transfer
        req.is_body_readable = True
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

        :param req: The WSGI/Webob Request object
        :param image_meta: Mapping of metadata about image
        :param image_data: Actual image data that is to be stored

        :raises HTTPBadRequest if x-image-meta-location is missing
                and the request body is not application/octet-stream
                image data.
        """
        if req.context.read_only:
            msg = _("Read-only access")
            logger.debug(msg)
            raise HTTPForbidden(msg, request=req,
                                content_type="text/plain")

        image_meta = self._reserve(req, image_meta)
        image_id = image_meta['id']

        if image_data is not None:
            image_meta = self._upload_and_activate(req, image_meta)
        else:
            location = image_meta.get('location')
            if location:
                image_meta = self._activate(req, image_id, location)

        return {'image_meta': image_meta}

    def update(self, req, id, image_meta, image_data):
        """
        Updates an existing image with the registry.

        :param request: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :retval Returns the updated image information as a mapping
        """
        if req.context.read_only:
            msg = _("Read-only access")
            logger.debug(msg)
            raise HTTPForbidden(msg, request=req,
                                content_type="text/plain")

        orig_image_meta = self.get_image_meta_or_404(req, id)
        orig_status = orig_image_meta['status']

        if image_data is not None and orig_status != 'queued':
            raise HTTPConflict(_("Cannot upload to an unqueued image"))

        try:
            image_meta = registry.update_image_metadata(self.options,
                                                        req.context, id,
                                                        image_meta, True)
            if image_data is not None:
                image_meta = self._upload_and_activate(req, image_meta)
        except exception.Invalid, e:
            msg = (_("Failed to update image metadata. Got error: %(e)s")
                   % locals())
            for line in msg.split('\n'):
                logger.error(line)
            self.notifier.error('image.update', msg)
            raise HTTPBadRequest(msg, request=req, content_type="text/plain")
        except exception.NotFound, e:
            msg = ("Failed to find image to update: %(e)s" % locals())
            for line in msg.split('\n'):
                logger.info(line)
            self.notifier.info('image.update', msg)
            raise HTTPNotFound(msg, request=req, content_type="text/plain")
        else:
            self.notifier.info('image.update', image_meta)

        return {'image_meta': image_meta}

    def delete(self, req, id):
        """
        Deletes the image and all its chunks from the Glance

        :param req: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :raises HttpBadRequest if image registry is invalid
        :raises HttpNotFound if image or any chunk is not available
        :raises HttpNotAuthorized if image or any chunk is not
                deleteable by the requesting user
        """
        if req.context.read_only:
            msg = _("Read-only access")
            logger.debug(msg)
            raise HTTPForbidden(msg, request=req,
                                content_type="text/plain")

        image = self.get_image_meta_or_404(req, id)

        # The image's location field may be None in the case
        # of a saving or queued image, therefore don't ask a backend
        # to delete the image if the backend doesn't yet store it.
        # See https://bugs.launchpad.net/glance/+bug/747799
        try:
            if image['location']:
                schedule_delete_from_backend(image['location'], self.options,
                                             req.context, id)
            registry.delete_image_metadata(self.options, req.context, id)
        except exception.NotFound, e:
            msg = ("Failed to find image to delete: %(e)s" % locals())
            for line in msg.split('\n'):
                logger.info(line)
            self.notifier.info('image.delete', msg)
            raise HTTPNotFound(msg, request=req, content_type="text/plain")
        else:
            self.notifier.info('image.delete', id)

    def members(self, req, image_id):
        """
        Return a list of dictionaries indicating the members of the
        image, i.e., those tenants the image is shared with.

        :param req: the Request object coming from the wsgi layer
        :param image_id: The opaque image identifier
        :retval The response body is a mapping of the following form::

            {'members': [
                {'member_id': <MEMBER>,
                 'can_share': <SHARE_PERMISSION>, ...}, ...
            ]}
        """
        try:
            members = registry.get_image_members(self.options, req.context,
                                                 image_id)
        except exception.NotFound:
            msg = _("Image with identifier %s not found") % image_id
            logger.debug(msg)
            raise HTTPNotFound(msg, request=req, content_type='text/plain')
        except exception.NotAuthorized:
            msg = _("Unauthorized image access")
            logger.debug(msg)
            raise HTTPForbidden(msg, request=req, content_type='text/plain')
        return dict(members=members)

    def shared_images(self, req, member):
        """
        Retrieves list of image memberships for the given member.

        :param req: the Request object coming from the wsgi layer
        :param member: the opaque member identifier
        :retval The response body is a mapping of the following form::

            {'shared_images': [
                {'image_id': <IMAGE>,
                 'can_share': <SHARE_PERMISSION>, ...}, ...
            ]}
        """
        try:
            members = registry.get_member_images(self.options, req.context,
                                                 member)
        except exception.NotFound, e:
            msg = "%s" % e
            logger.debug(msg)
            raise HTTPNotFound(msg, request=req, content_type='text/plain')
        except exception.NotAuthorized, e:
            msg = "%s" % e
            logger.debug(msg)
            raise HTTPForbidden(msg, request=req, content_type='text/plain')
        return dict(shared_images=members)

    def get_store_or_400(self, request, store_name):
        """
        Grabs the storage backend for the supplied store name
        or raises an HTTPBadRequest (400) response

        :param request: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :raises HTTPNotFound if image does not exist
        """
        try:
            return get_store_from_scheme(store_name)
        except exception.UnknownScheme:
            msg = (_("Requested store %s not available on this Glance server")
                   % store_name)
            logger.error(msg)
            raise HTTPBadRequest(msg, request=request,
                                 content_type='text/plain')

    def replace_members(self, req, image_id, body):
        """
        Replaces the members of the image with those specified in the
        body.  The body is a dict with the following format::

            {"memberships": [
                {"member_id": <MEMBER_ID>,
                 ["can_share": [True|False]]}, ...
            ]}
        """
        if req.context.read_only:
            raise HTTPForbidden()
        elif req.context.owner is None:
            raise HTTPUnauthorized(_("No authenticated user"))

        try:
            registry.replace_members(self.options, req.context,
                                     image_id, body)
        except exception.NotFound, e:
            msg = "%s" % e
            logger.debug(msg)
            raise HTTPNotFound(msg, request=req, content_type='text/plain')
        except exception.NotAuthorized, e:
            msg = "%s" % e
            logger.debug(msg)
            raise HTTPNotFound(msg, request=req, content_type='text/plain')

        return HTTPNoContent()

    def add_member(self, req, image_id, member, body=None):
        """
        Adds a membership to the image, or updates an existing one.
        If a body is present, it is a dict with the following format::

            {"member": {
                "can_share": [True|False]
            }}

        If "can_share" is provided, the member's ability to share is
        set accordingly.  If it is not provided, existing memberships
        remain unchanged and new memberships default to False.
        """
        if req.context.read_only:
            raise HTTPForbidden()
        elif req.context.owner is None:
            raise HTTPUnauthorized(_("No authenticated user"))

        # Figure out can_share
        can_share = None
        if body and 'member' in body and 'can_share' in body['member']:
            can_share = bool(body['member']['can_share'])
        try:
            registry.add_member(self.options, req.context, image_id, member,
                                can_share)
        except exception.NotFound, e:
            msg = "%s" % e
            logger.debug(msg)
            raise HTTPNotFound(msg, request=req, content_type='text/plain')
        except exception.NotAuthorized, e:
            msg = "%s" % e
            logger.debug(msg)
            raise HTTPNotFound(msg, request=req, content_type='text/plain')

        return HTTPNoContent()

    def delete_member(self, req, image_id, member):
        """
        Removes a membership from the image.
        """
        if req.context.read_only:
            raise HTTPForbidden()
        elif req.context.owner is None:
            raise HTTPUnauthorized(_("No authenticated user"))

        try:
            registry.delete_member(self.options, req.context,
                                   image_id, member)
        except exception.NotFound, e:
            msg = "%s" % e
            logger.debug(msg)
            raise HTTPNotFound(msg, request=req, content_type='text/plain')
        except exception.NotAuthorized, e:
            msg = "%s" % e
            logger.debug(msg)
            raise HTTPNotFound(msg, request=req, content_type='text/plain')

        return HTTPNoContent()


class ImageDeserializer(wsgi.JSONRequestDeserializer):
    """Handles deserialization of specific controller method requests."""

    def _deserialize(self, request):
        result = {}
        result['image_meta'] = utils.get_image_meta_from_headers(request)
        data = request.body_file if self.has_body(request) else None
        result['image_data'] = data
        return result

    def create(self, request):
        return self._deserialize(request)

    def update(self, request):
        return self._deserialize(request)


class ImageSerializer(wsgi.JSONResponseSerializer):
    """Handles serialization of specific controller method responses."""

    def _inject_location_header(self, response, image_meta):
        location = self._get_image_location(image_meta)
        response.headers['Location'] = location

    def _inject_checksum_header(self, response, image_meta):
        response.headers['ETag'] = image_meta['checksum']

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
            response.headers[k] = v

    def _get_image_location(self, image_meta):
        """Build a relative url to reach the image defined by image_meta."""
        return "/v1/images/%s" % image_meta['id']

    def meta(self, response, result):
        image_meta = result['image_meta']
        self._inject_image_meta_headers(response, image_meta)
        self._inject_location_header(response, image_meta)
        self._inject_checksum_header(response, image_meta)
        return response

    def show(self, response, result):
        image_meta = result['image_meta']

        response.app_iter = result['image_iterator']
        # Using app_iter blanks content-length, so we set it here...
        response.headers['Content-Length'] = image_meta['size']
        response.headers['Content-Type'] = 'application/octet-stream'

        self._inject_image_meta_headers(response, image_meta)
        self._inject_location_header(response, image_meta)
        self._inject_checksum_header(response, image_meta)

        return response

    def update(self, response, result):
        image_meta = result['image_meta']
        response.body = self.to_json(dict(image=image_meta))
        response.headers['Content-Type'] = 'application/json'
        self._inject_location_header(response, image_meta)
        self._inject_checksum_header(response, image_meta)
        return response

    def create(self, response, result):
        image_meta = result['image_meta']
        response.status = httplib.CREATED
        response.headers['Content-Type'] = 'application/json'
        response.body = self.to_json(dict(image=image_meta))
        self._inject_location_header(response, image_meta)
        self._inject_checksum_header(response, image_meta)
        return response


def create_resource(options):
    """Images resource factory method"""
    deserializer = ImageDeserializer()
    serializer = ImageSerializer()
    return wsgi.Resource(Controller(options), deserializer, serializer)
