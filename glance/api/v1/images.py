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

import errno
import logging
import sys
import traceback

from webob.exc import (HTTPError,
                       HTTPNotFound,
                       HTTPConflict,
                       HTTPBadRequest,
                       HTTPForbidden,
                       HTTPRequestEntityTooLarge,
                       HTTPServiceUnavailable,
                      )

from glance.api import policy
import glance.api.v1
from glance.api.v1 import controller
from glance.api.v1 import filters
from glance.common import cfg
from glance.common import exception
from glance.common import wsgi
from glance.common import utils
import glance.store
import glance.store.filesystem
import glance.store.http
import glance.store.rbd
import glance.store.s3
import glance.store.swift
from glance.store import (get_from_backend,
                          get_size_from_backend,
                          schedule_delete_from_backend,
                          get_store_from_location,
                          get_store_from_scheme)
from glance import registry
from glance import notifier


logger = logging.getLogger(__name__)
SUPPORTED_PARAMS = glance.api.v1.SUPPORTED_PARAMS
SUPPORTED_FILTERS = glance.api.v1.SUPPORTED_FILTERS


# 1 PiB, which is a *huge* image by anyone's measure.  This is just to protect
# against client programming errors (or DoS attacks) in the image metadata.
# We have a known limit of 1 << 63 in the database -- images.size is declared
# as a BigInteger.
IMAGE_SIZE_CAP = 1 << 50


class Controller(controller.BaseController):
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

    default_store_opt = cfg.StrOpt('default_store', default='file')

    def __init__(self, conf):
        self.conf = conf
        self.conf.register_opt(self.default_store_opt)
        glance.store.create_stores(conf)
        self.verify_store_or_exit(self.conf.default_store)
        self.notifier = notifier.Notifier(conf)
        registry.configure_registry_client(conf)
        self.policy = policy.Enforcer(conf)

    def _enforce(self, req, action):
        """Authorize an action against our policies"""
        try:
            self.policy.enforce(req.context, action, {})
        except exception.Forbidden:
            raise HTTPForbidden()

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
        self._enforce(req, 'get_images')
        params = self._get_query_params(req)
        try:
            images = registry.get_images_list(req.context, **params)
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
                 'min_disk': <MIN_DISK>,
                 'min_ram': <MIN_RAM>,
                 'store': <STORE>,
                 'status': <STATUS>,
                 'created_at': <TIMESTAMP>,
                 'updated_at': <TIMESTAMP>,
                 'deleted_at': <TIMESTAMP>|<NONE>,
                 'properties': {'distro': 'Ubuntu 10.04 LTS', ...}}, ...
            ]}
        """
        self._enforce(req, 'get_images')
        params = self._get_query_params(req)
        try:
            images = registry.get_images_detail(req.context, **params)
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
            if PARAM in req.params:
                params[PARAM] = req.params.get(PARAM)
        return params

    def _get_filters(self, req):
        """
        Return a dictionary of query param filters from the request

        :param req: the Request object coming from the wsgi layer
        :retval a dict of key/value filters
        """
        query_filters = {}
        for param in req.params:
            if param in SUPPORTED_FILTERS or param.startswith('property-'):
                query_filters[param] = req.params.get(param)
                if not filters.validate(param, query_filters[param]):
                    raise HTTPBadRequest('Bad value passed to filter %s '
                                         'got %s' % (param,
                                                     query_filters[param]))
        return query_filters

    def meta(self, req, id):
        """
        Returns metadata about an image in the HTTP headers of the
        response object

        :param req: The WSGI/Webob Request object
        :param id: The opaque image identifier
        :retval similar to 'show' method but without image_data

        :raises HTTPNotFound if image metadata is not available to user
        """
        self._enforce(req, 'get_image')
        image_meta = self.get_image_meta_or_404(req, id)
        del image_meta['location']
        return {
            'image_meta': image_meta
        }

    @staticmethod
    def _validate_source(source, req):
        """
        External sources (as specified via the location or copy-from headers)
        are supported only over non-local store types, i.e. S3, Swift, HTTP.
        Note the absence of file:// for security reasons, see LP bug #942118.
        If the above constraint is violated, we reject with 400 "Bad Request".
        """
        if source:
            for scheme in ['s3', 'swift', 'http']:
                if source.lower().startswith(scheme):
                    return source
            msg = _("External sourcing not supported for store %s") % source
            logger.error(msg)
            raise HTTPBadRequest(msg, request=req, content_type="text/plain")

    @staticmethod
    def _copy_from(req):
        return req.headers.get('x-glance-api-copy-from')

    @staticmethod
    def _external_source(image_meta, req):
        source = image_meta.get('location', Controller._copy_from(req))
        return Controller._validate_source(source, req)

    @staticmethod
    def _get_from_store(where):
        try:
            image_data, image_size = get_from_backend(where)
        except exception.NotFound, e:
            raise HTTPNotFound(explanation="%s" % e)
        image_size = int(image_size) if image_size else None
        return image_data, image_size

    def show(self, req, id):
        """
        Returns an iterator that can be used to retrieve an image's
        data along with the image metadata.

        :param req: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :raises HTTPNotFound if image is not available to user
        """
        self._enforce(req, 'get_image')
        image_meta = self.get_active_image_meta_or_404(req, id)

        if image_meta.get('size') == 0:
            image_iterator = iter([])
        else:
            image_iterator, size = self._get_from_store(image_meta['location'])
            image_meta['size'] = size or image_meta['size']

        del image_meta['location']
        return {
            'image_iterator': image_iterator,
            'image_meta': image_meta,
        }

    def _reserve(self, req, image_meta):
        """
        Adds the image metadata to the registry and assigns
        an image identifier if one is not supplied in the request
        headers. Sets the image's status to `queued`.

        :param req: The WSGI/Webob Request object
        :param id: The opaque image identifier
        :param image_meta: The image metadata

        :raises HTTPConflict if image already exists
        :raises HTTPBadRequest if image metadata is not valid
        """
        location = self._external_source(image_meta, req)

        image_meta['status'] = ('active' if image_meta.get('size') == 0
                                else 'queued')

        if location:
            store = get_store_from_location(location)
            # check the store exists before we hit the registry, but we
            # don't actually care what it is at this point
            self.get_store_or_400(req, store)

            # retrieve the image size from remote store (if not provided)
            image_meta['size'] = self._get_size(image_meta, location)
        else:
            # Ensure that the size attribute is set to zero for directly
            # uploadable images (if not provided). The size will be set
            # to a non-zero value during upload
            image_meta['size'] = image_meta.get('size', 0)

        try:
            image_meta = registry.add_image_metadata(req.context, image_meta)
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
        except exception.Forbidden:
            msg = _("Forbidden to reserve image.")
            logger.error(msg)
            raise HTTPForbidden(msg, request=req, content_type="text/plain")

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

        copy_from = self._copy_from(req)
        if copy_from:
            image_data, image_size = self._get_from_store(copy_from)
            image_meta['size'] = image_size or image_meta['size']
        else:
            try:
                req.get_content_type('application/octet-stream')
            except exception.InvalidContentType:
                self._safe_kill(req, image_meta['id'])
                msg = _("Content-Type must be application/octet-stream")
                logger.error(msg)
                raise HTTPBadRequest(explanation=msg)

            image_data = req.body_file

            if req.content_length:
                image_size = int(req.content_length)
            elif 'x-image-meta-size' in req.headers:
                image_size = int(req.headers['x-image-meta-size'])
            else:
                logger.debug(_("Got request with no content-length and no "
                               "x-image-meta-size header"))
                image_size = 0

        store_name = req.headers.get('x-image-meta-store',
                                     self.conf.default_store)

        store = self.get_store_or_400(req, store_name)

        image_id = image_meta['id']
        logger.debug(_("Setting image %s to status 'saving'"), image_id)
        registry.update_image_metadata(req.context, image_id,
                                       {'status': 'saving'})
        try:
            logger.debug(_("Uploading image data for image %(image_id)s "
                         "to %(store_name)s store"), locals())

            if image_size > IMAGE_SIZE_CAP:
                max_image_size = IMAGE_SIZE_CAP
                msg = _("Denying attempt to upload image larger than "
                        "%(max_image_size)d. Supplied image size was "
                        "%(image_size)d") % locals()
                logger.warn(msg)
                raise HTTPBadRequest(msg, request=req)

            location, size, checksum = store.add(image_meta['id'],
                                                 image_data,
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
            update_data = {'checksum': checksum,
                           'size': size}
            image_meta = registry.update_image_metadata(req.context,
                                                        image_id,
                                                        update_data)
            self.notifier.info('image.upload', image_meta)

            return location

        except exception.Duplicate, e:
            msg = _("Attempt to upload duplicate image: %s") % e
            logger.error(msg)
            self._safe_kill(req, image_id)
            self.notifier.error('image.upload', msg)
            raise HTTPConflict(msg, request=req)

        except exception.Forbidden, e:
            msg = _("Forbidden upload attempt: %s") % e
            logger.error(msg)
            self._safe_kill(req, image_id)
            self.notifier.error('image.upload', msg)
            raise HTTPForbidden(msg, request=req, content_type="text/plain")

        except exception.StorageFull, e:
            msg = _("Image storage media is full: %s") % e
            logger.error(msg)
            self._safe_kill(req, image_id)
            self.notifier.error('image.upload', msg)
            raise HTTPRequestEntityTooLarge(msg, request=req,
                                            content_type='text/plain')

        except exception.StorageWriteDenied, e:
            msg = _("Insufficient permissions on image storage media: %s") % e
            logger.error(msg)
            self._safe_kill(req, image_id)
            self.notifier.error('image.upload', msg)
            raise HTTPServiceUnavailable(msg, request=req,
                                         content_type='text/plain')

        except HTTPError, e:
            self._safe_kill(req, image_id)
            self.notifier.error('image.upload', e.explanation)
            raise

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

        try:
            return registry.update_image_metadata(req.context,
                                                  image_id,
                                                  image_meta)
        except exception.Invalid, e:
            msg = (_("Failed to activate image. Got error: %(e)s")
                   % locals())
            for line in msg.split('\n'):
                logger.error(line)
            self.notifier.error('image.update', msg)
            raise HTTPBadRequest(msg, request=req, content_type="text/plain")

    def _kill(self, req, image_id):
        """
        Marks the image status to `killed`.

        :param req: The WSGI/Webob Request object
        :param image_id: Opaque image identifier
        """
        registry.update_image_metadata(req.context, image_id,
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

    def _get_size(self, image_meta, location):
        # retrieve the image size from remote store (if not provided)
        return image_meta.get('size', 0) or get_size_from_backend(location)

    def _handle_source(self, req, image_id, image_meta, image_data):
        if image_data or self._copy_from(req):
            image_meta = self._upload_and_activate(req, image_meta)
        else:
            location = image_meta.get('location')
            if location:
                image_meta = self._activate(req, image_id, location)
        return image_meta

    def create(self, req, image_meta, image_data):
        """
        Adds a new image to Glance. Four scenarios exist when creating an
        image:

        1. If the image data is available directly for upload, create can be
           passed the image data as the request body and the metadata as the
           request headers. The image will initially be 'queued', during
           upload it will be in the 'saving' status, and then 'killed' or
           'active' depending on whether the upload completed successfully.

        2. If the image data exists somewhere else, you can upload indirectly
           from the external source using the x-glance-api-copy-from header.
           Once the image is uploaded, the external store is not subsequently
           consulted, i.e. the image content is served out from the configured
           glance image store.  State transitions are as for option #1.

        3. If the image data exists somewhere else, you can reference the
           source using the x-image-meta-location header. The image content
           will be served out from the external store, i.e. is never uploaded
           to the configured glance image store.

        4. If the image data is not available yet, but you'd like reserve a
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
        self._enforce(req, 'add_image')
        if image_meta.get('is_public'):
            self._enforce(req, 'publicize_image')
        if req.context.read_only:
            msg = _("Read-only access")
            logger.debug(msg)
            raise HTTPForbidden(msg, request=req,
                                content_type="text/plain")

        image_meta = self._reserve(req, image_meta)
        id = image_meta['id']

        image_meta = self._handle_source(req, id, image_meta, image_data)

        # Prevent client from learning the location, as it
        # could contain security credentials
        image_meta.pop('location', None)

        return {'image_meta': image_meta}

    def update(self, req, id, image_meta, image_data):
        """
        Updates an existing image with the registry.

        :param request: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :retval Returns the updated image information as a mapping
        """
        self._enforce(req, 'modify_image')
        if image_meta.get('is_public'):
            self._enforce(req, 'publicize_image')
        if req.context.read_only:
            msg = _("Read-only access")
            logger.debug(msg)
            raise HTTPForbidden(msg, request=req,
                                content_type="text/plain")

        orig_image_meta = self.get_image_meta_or_404(req, id)
        orig_status = orig_image_meta['status']

        # The default behaviour for a PUT /images/<IMAGE_ID> is to
        # override any properties that were previously set. This, however,
        # leads to a number of issues for the common use case where a caller
        # registers an image with some properties and then almost immediately
        # uploads an image file along with some more properties. Here, we
        # check for a special header value to be false in order to force
        # properties NOT to be purged. However we also disable purging of
        # properties if an image file is being uploaded...
        purge_props = req.headers.get('x-glance-registry-purge-props', True)
        purge_props = (utils.bool_from_string(purge_props) and
                       image_data is None)

        if image_data is not None and orig_status != 'queued':
            raise HTTPConflict(_("Cannot upload to an unqueued image"))

        # Only allow the Location|Copy-From fields to be modified if the
        # image is in queued status, which indicates that the user called
        # POST /images but originally supply neither a Location|Copy-From
        # field NOR image data
        location = self._external_source(image_meta, req)
        reactivating = orig_status != 'queued' and location
        activating = orig_status == 'queued' and (location or image_data)

        if reactivating:
            msg = _("Attempted to update Location field for an image "
                    "not in queued status.")
            raise HTTPBadRequest(msg, request=req, content_type="text/plain")

        try:
            if location:
                image_meta['size'] = self._get_size(image_meta, location)

            image_meta = registry.update_image_metadata(req.context,
                                                        id,
                                                        image_meta,
                                                        purge_props)

            if activating:
                image_meta = self._handle_source(req, id, image_meta,
                                                 image_data)
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
        except exception.Forbidden, e:
            msg = ("Forbidden to update image: %(e)s" % locals())
            for line in msg.split('\n'):
                logger.info(line)
            self.notifier.info('image.update', msg)
            raise HTTPForbidden(msg, request=req, content_type="text/plain")
        else:
            self.notifier.info('image.update', image_meta)

        # Prevent client from learning the location, as it
        # could contain security credentials
        image_meta.pop('location', None)

        return {'image_meta': image_meta}

    def delete(self, req, id):
        """
        Deletes the image and all its chunks from the Glance

        :param req: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :raises HttpBadRequest if image registry is invalid
        :raises HttpNotFound if image or any chunk is not available
        :raises HttpUnauthorized if image or any chunk is not
                deleteable by the requesting user
        """
        self._enforce(req, 'delete_image')
        if req.context.read_only:
            msg = _("Read-only access")
            logger.debug(msg)
            raise HTTPForbidden(msg, request=req,
                                content_type="text/plain")

        image = self.get_image_meta_or_404(req, id)

        if not (req.context.is_admin
                or image['owner'] == None
                or image['owner'] == req.context.owner):
            msg = _("Unable to delete image you do not own")
            logger.debug(msg)
            raise HTTPForbidden(msg, request=req,
                                content_type="text/plain")

        if image['protected']:
            msg = _("Image is protected")
            logger.debug(msg)
            raise HTTPForbidden(msg, request=req,
                                content_type="text/plain")

        # The image's location field may be None in the case
        # of a saving or queued image, therefore don't ask a backend
        # to delete the image if the backend doesn't yet store it.
        # See https://bugs.launchpad.net/glance/+bug/747799
        try:
            if image['location']:
                schedule_delete_from_backend(image['location'], self.conf,
                                             req.context, id)
            registry.delete_image_metadata(req.context, id)
        except exception.NotFound, e:
            msg = ("Failed to find image to delete: %(e)s" % locals())
            for line in msg.split('\n'):
                logger.info(line)
            self.notifier.info('image.delete', msg)
            raise HTTPNotFound(msg, request=req, content_type="text/plain")
        except exception.Forbidden, e:
            msg = ("Forbidden to delete image: %(e)s" % locals())
            for line in msg.split('\n'):
                logger.info(line)
            self.notifier.info('image.delete', msg)
            raise HTTPForbidden(msg, request=req, content_type="text/plain")
        else:
            self.notifier.info('image.delete', id)

    def get_store_or_400(self, request, store_name):
        """
        Grabs the storage backend for the supplied store name
        or raises an HTTPBadRequest (400) response

        :param request: The WSGI/Webob Request object
        :param store_name: The backend store name

        :raises HTTPNotFound if store does not exist
        """
        try:
            return get_store_from_scheme(store_name)
        except exception.UnknownScheme:
            msg = (_("Requested store %s not available on this Glance server")
                   % store_name)
            logger.error(msg)
            raise HTTPBadRequest(msg, request=request,
                                 content_type='text/plain')

    def verify_store_or_exit(self, store_name):
        """
        Verifies availability of the storage backend for the
        given store name or exits

        :param store_name: The backend store name
        """
        try:
            get_store_from_scheme(store_name)
        except exception.UnknownScheme:
            msg = (_("Default store %s not available on this Glance server\n")
                   % store_name)
            logger.error(msg)
            # message on stderr will only be visible if started directly via
            # bin/glance-api, as opposed to being daemonized by glance-control
            sys.stderr.write(msg)
            sys.exit(255)


class ImageDeserializer(wsgi.JSONRequestDeserializer):
    """Handles deserialization of specific controller method requests."""

    def _deserialize(self, request):
        result = {}
        try:
            result['image_meta'] = utils.get_image_meta_from_headers(request)
        except exception.Invalid:
            image_size_str = request.headers['x-image-meta-size']
            msg = _("Incoming image size of %s was not convertible to "
                    "an integer.") % image_size_str
            raise HTTPBadRequest(msg, request=request)

        image_meta = result['image_meta']
        if 'size' in image_meta:
            incoming_image_size = image_meta['size']
            if incoming_image_size > IMAGE_SIZE_CAP:
                max_image_size = IMAGE_SIZE_CAP
                msg = _("Denying attempt to upload image larger than "
                        "%(max_image_size)d. Supplied image size was "
                        "%(incoming_image_size)d") % locals()
                logger.warn(msg)
                raise HTTPBadRequest(msg, request=request)

        data = request.body_file if self.has_body(request) else None
        result['image_data'] = data
        return result

    def create(self, request):
        return self._deserialize(request)

    def update(self, request):
        return self._deserialize(request)


class ImageSerializer(wsgi.JSONResponseSerializer):
    """Handles serialization of specific controller method responses."""

    def __init__(self, conf):
        self.conf = conf
        self.notifier = notifier.Notifier(conf)

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

    def image_send_notification(self, bytes_written, expected_size,
                                image_meta, request):
        """Send an image.send message to the notifier."""
        try:
            context = request.context
            payload = {
                'bytes_sent': bytes_written,
                'image_id': image_meta['id'],
                'owner_id': image_meta['owner'],
                'receiver_tenant_id': context.tenant,
                'receiver_user_id': context.user,
                'destination_ip': request.remote_addr,
            }
            if bytes_written != expected_size:
                self.notifier.error('image.send', payload)
            else:
                self.notifier.info('image.send', payload)
        except Exception, err:
            msg = _("An error occurred during image.send"
                    " notification: %(err)s") % locals()
            logger.error(msg)

    def show(self, response, result):
        image_meta = result['image_meta']
        image_id = image_meta['id']

        # We use a secondary iterator here to wrap the
        # iterator coming back from the store driver in
        # order to check for disconnections from the backend
        # storage connections and log an error if the size of
        # the transferred image is not the same as the expected
        # size of the image file. See LP Bug #882585.
        def checked_iter(image_id, expected_size, image_iter):
            bytes_written = 0

            def notify_image_sent_hook(env):
                self.image_send_notification(bytes_written, expected_size,
                                             image_meta, response.request)

            # Add hook to process after response is fully sent
            if 'eventlet.posthooks' in response.request.environ:
                response.request.environ['eventlet.posthooks'].append(
                    (notify_image_sent_hook, (), {}))

            try:
                for chunk in image_iter:
                    yield chunk
                    bytes_written += len(chunk)
            except Exception, err:
                msg = _("An error occurred reading from backend storage "
                        "for image %(image_id): %(err)s") % locals()
                logger.error(msg)
                raise

            if expected_size != bytes_written:
                msg = _("Backend storage for image %(image_id)s "
                        "disconnected after writing only %(bytes_written)d "
                        "bytes") % locals()
                logger.error(msg)
                raise IOError(errno.EPIPE, _("Corrupt image download for "
                                             "image %(image_id)s") % locals())

        image_iter = result['image_iterator']
        # image_meta['size'] is a str
        expected_size = int(image_meta['size'])
        response.app_iter = checked_iter(image_id, expected_size, image_iter)
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
        response.status = 201
        response.headers['Content-Type'] = 'application/json'
        response.body = self.to_json(dict(image=image_meta))
        self._inject_location_header(response, image_meta)
        self._inject_checksum_header(response, image_meta)
        return response


def create_resource(conf):
    """Images resource factory method"""
    deserializer = ImageDeserializer()
    serializer = ImageSerializer(conf)
    return wsgi.Resource(Controller(conf), deserializer, serializer)
