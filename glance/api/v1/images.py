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

import sys
import traceback

import eventlet
from webob.exc import (HTTPError,
                       HTTPNotFound,
                       HTTPConflict,
                       HTTPBadRequest,
                       HTTPForbidden,
                       HTTPRequestEntityTooLarge,
                       HTTPServiceUnavailable,
                      )

from glance.api import common
from glance.api import policy
import glance.api.v1
from glance import context
from glance.api.v1 import controller
from glance.api.v1 import filters
from glance.common import exception
from glance.common import utils
from glance.common import wsgi
from glance import notifier
from glance.openstack.common import cfg
import glance.openstack.common.log as logging
from glance import registry
from glance.store import (create_stores,
                          get_from_backend,
                          get_size_from_backend,
                          safe_delete_from_backend,
                          schedule_delayed_delete_from_backend,
                          get_store_from_location,
                          get_store_from_scheme)


LOG = logging.getLogger(__name__)
SUPPORTED_PARAMS = glance.api.v1.SUPPORTED_PARAMS
SUPPORTED_FILTERS = glance.api.v1.SUPPORTED_FILTERS
CONTAINER_FORMATS = ['ami', 'ari', 'aki', 'bare', 'ovf']
DISK_FORMATS = ['ami', 'ari', 'aki', 'vhd', 'vmdk', 'raw', 'qcow2', 'vdi',
               'iso']


# Defined at module level due to _is_opt_registered
# identity check (not equality).
default_store_opt = cfg.StrOpt('default_store', default='file')

CONF = cfg.CONF
CONF.register_opt(default_store_opt)


def validate_image_meta(req, values):

    name = values.get('name')
    disk_format = values.get('disk_format')
    container_format = values.get('container_format')

    if 'disk_format' in values:
        if not disk_format in DISK_FORMATS:
            msg = "Invalid disk format '%s' for image." % disk_format
            raise HTTPBadRequest(explanation=msg, request=req)

    if 'container_format' in values:
        if not container_format in CONTAINER_FORMATS:
            msg = "Invalid container format '%s' for image." % container_format
            raise HTTPBadRequest(explanation=msg, request=req)

    if name and len(name) > 255:
        msg = _('Image name too long: %d') % len(name)
        raise HTTPBadRequest(explanation=msg, request=req)

    amazon_formats = ('aki', 'ari', 'ami')

    if disk_format in amazon_formats or container_format in amazon_formats:
        if disk_format is None:
            values['disk_format'] = container_format
        elif container_format is None:
            values['container_format'] = disk_format
        elif container_format != disk_format:
            msg = ("Invalid mix of disk and container formats. "
                   "When setting a disk or container format to "
                   "one of 'aki', 'ari', or 'ami', the container "
                   "and disk formats must match.")
            raise HTTPBadRequest(explanation=msg, request=req)

    return values


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

    def __init__(self):
        create_stores()
        self.verify_scheme_or_exit(CONF.default_store)
        self.notifier = notifier.Notifier()
        registry.configure_registry_client()
        self.policy = policy.Enforcer()
        self.pool = eventlet.GreenPool(size=1024)

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
            LOG.error(msg)
            raise HTTPBadRequest(explanation=msg,
                                 request=req,
                                 content_type="text/plain")

    @staticmethod
    def _copy_from(req):
        return req.headers.get('x-glance-api-copy-from')

    @staticmethod
    def _external_source(image_meta, req):
        source = image_meta.get('location', Controller._copy_from(req))
        return Controller._validate_source(source, req)

    @staticmethod
    def _get_from_store(context, where):
        try:
            image_data, image_size = get_from_backend(context, where)
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
        self._enforce(req, 'download_image')
        image_meta = self.get_active_image_meta_or_404(req, id)

        if image_meta.get('size') == 0:
            image_iterator = iter([])
        else:
            image_iterator, size = self._get_from_store(req.context,
                                                        image_meta['location'])
            image_iterator = utils.cooperative_iter(image_iterator)
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
            image_meta['size'] = self._get_size(req.context, image_meta,
                                                location)
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
            LOG.error(msg)
            raise HTTPConflict(explanation=msg,
                               request=req,
                               content_type="text/plain")
        except exception.Invalid, e:
            msg = (_("Failed to reserve image. Got error: %(e)s") % locals())
            for line in msg.split('\n'):
                LOG.error(line)
            raise HTTPBadRequest(explanation=msg,
                                 request=req,
                                 content_type="text/plain")
        except exception.Forbidden:
            msg = _("Forbidden to reserve image.")
            LOG.error(msg)
            raise HTTPForbidden(explanation=msg,
                                request=req,
                                content_type="text/plain")

    def _upload(self, req, image_meta):
        """
        Uploads the payload of the request to a backend store in
        Glance. If the `x-image-meta-store` header is set, Glance
        will attempt to use that scheme; if not, Glance will use the
        scheme set by the flag `default_store` to find the backing store.

        :param req: The WSGI/Webob Request object
        :param image_meta: Mapping of metadata about image

        :raises HTTPConflict if image already exists
        :retval The location where the image was stored
        """

        copy_from = self._copy_from(req)
        if copy_from:
            try:
                image_data, image_size = self._get_from_store(req.context,
                                                              copy_from)
            except Exception as e:
                self._safe_kill(req, image_meta['id'])
                msg = _("Copy from external source failed: %s") % e
                LOG.error(msg)
                return
            image_meta['size'] = image_size or image_meta['size']
        else:
            try:
                req.get_content_type('application/octet-stream')
            except exception.InvalidContentType:
                self._safe_kill(req, image_meta['id'])
                msg = _("Content-Type must be application/octet-stream")
                LOG.error(msg)
                raise HTTPBadRequest(explanation=msg)

            image_data = req.body_file

        scheme = req.headers.get('x-image-meta-store', CONF.default_store)

        store = self.get_store_or_400(req, scheme)

        image_id = image_meta['id']
        LOG.debug(_("Setting image %s to status 'saving'"), image_id)
        registry.update_image_metadata(req.context, image_id,
                                       {'status': 'saving'})

        LOG.debug(_("Uploading image data for image %(image_id)s "
                    "to %(scheme)s store"), locals())

        try:
            location, size, checksum = store.add(
                image_meta['id'],
                utils.CooperativeReader(image_data),
                image_meta['size'])

            # Verify any supplied checksum value matches checksum
            # returned from store when adding image
            supplied_checksum = image_meta.get('checksum')
            if supplied_checksum and supplied_checksum != checksum:
                msg = _("Supplied checksum (%(supplied_checksum)s) and "
                       "checksum generated from uploaded image "
                       "(%(checksum)s) did not match. Setting image "
                       "status to 'killed'.") % locals()
                LOG.error(msg)
                self._safe_kill(req, image_id)
                raise HTTPBadRequest(explanation=msg,
                                     content_type="text/plain",
                                     request=req)

            # Update the database with the checksum returned
            # from the backend store
            LOG.debug(_("Updating image %(image_id)s data. "
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
            LOG.error(msg)
            self._safe_kill(req, image_id)
            self.notifier.error('image.upload', msg)
            raise HTTPConflict(explanation=msg, request=req)

        except exception.Forbidden, e:
            msg = _("Forbidden upload attempt: %s") % e
            LOG.error(msg)
            self._safe_kill(req, image_id)
            self.notifier.error('image.upload', msg)
            raise HTTPForbidden(explanation=msg,
                                request=req,
                                content_type="text/plain")

        except exception.StorageFull, e:
            msg = _("Image storage media is full: %s") % e
            LOG.error(msg)
            self._safe_kill(req, image_id)
            self.notifier.error('image.upload', msg)
            raise HTTPRequestEntityTooLarge(explanation=msg, request=req,
                                            content_type='text/plain')

        except exception.StorageWriteDenied, e:
            msg = _("Insufficient permissions on image storage media: %s") % e
            LOG.error(msg)
            self._safe_kill(req, image_id)
            self.notifier.error('image.upload', msg)
            raise HTTPServiceUnavailable(explanation=msg, request=req,
                                         content_type='text/plain')

        except exception.ImageSizeLimitExceeded, e:
            msg = _("Denying attempt to upload image larger than %d bytes.")
            self._safe_kill(req, image_id)
            raise HTTPBadRequest(explanation=msg % CONF.image_size_cap,
                                 request=req, content_type='text/plain')

        except HTTPError, e:
            self._safe_kill(req, image_id)
            self.notifier.error('image.upload', e.explanation)
            #NOTE(bcwaldon): Ideally, we would just call 'raise' here,
            # but something in the above function calls is affecting the
            # exception context and we must explicitly re-raise the
            # caught exception.
            raise e

        except Exception, e:
            tb_info = traceback.format_exc()
            LOG.error(tb_info)

            self._safe_kill(req, image_id)

            msg = _("Error uploading image: (%(class_name)s): "
                    "%(exc)s") % ({'class_name': e.__class__.__name__,
                    'exc': str(e)})

            self.notifier.error('image.upload', msg)
            raise HTTPBadRequest(explanation=msg, request=req)

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
            image_meta_data = registry.update_image_metadata(req.context,
                                                  image_id,
                                                  image_meta)
            self.notifier.info("image.update", image_meta_data)
            return image_meta_data
        except exception.Invalid, e:
            msg = (_("Failed to activate image. Got error: %(e)s")
                   % locals())
            for line in msg.split('\n'):
                LOG.error(line)
            self.notifier.error('image.update', msg)
            raise HTTPBadRequest(explanation=msg,
                                 request=req,
                                 content_type="text/plain")

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
            LOG.error(_("Unable to kill image %(id)s: "
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
        return self._activate(req, image_id, location) if location else None

    def _get_size(self, context, image_meta, location):
        # retrieve the image size from remote store (if not provided)
        return image_meta.get('size', 0) or get_size_from_backend(context,
                                                                  location)

    def _handle_source(self, req, image_id, image_meta, image_data):
        if image_data:
            image_meta = self._validate_image_for_activation(req, image_id,
                                                        image_meta)
            image_meta = self._upload_and_activate(req, image_meta)
        elif self._copy_from(req):
            msg = _('Triggering asynchronous copy from external source')
            LOG.info(msg)
            self.pool.spawn_n(self._upload_and_activate, req, image_meta)
        else:
            location = image_meta.get('location')
            if location:
                self._validate_image_for_activation(req, image_id, image_meta)
                image_meta = self._activate(req, image_id, location)
        return image_meta

    def _validate_image_for_activation(self, req, id, values):
        """Ensures that all required image metadata values are valid."""
        image = self.get_image_meta_or_404(req, id)
        if not 'disk_format' in values:
            values['disk_format'] = image['disk_format']
        if not 'container_format' in values:
            values['container_format'] = image['container_format']
        if not 'name' in values:
            values['name'] = image['name']

        values = validate_image_meta(req, values)
        return values

    @utils.mutating
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
        is_public = image_meta.get('is_public')
        if is_public:
            self._enforce(req, 'publicize_image')

        image_meta = self._reserve(req, image_meta)
        id = image_meta['id']

        image_meta = self._handle_source(req, id, image_meta, image_data)

        location_uri = image_meta.get('location')
        if location_uri:
            self.update_store_acls(req, id, location_uri, public=is_public)

        # Prevent client from learning the location, as it
        # could contain security credentials
        image_meta.pop('location', None)

        return {'image_meta': image_meta}

    @utils.mutating
    def update(self, req, id, image_meta, image_data):
        """
        Updates an existing image with the registry.

        :param request: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :retval Returns the updated image information as a mapping
        """
        self._enforce(req, 'modify_image')
        is_public = image_meta.get('is_public')
        if is_public:
            self._enforce(req, 'publicize_image')

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

        # Make image public in the backend store (if implemented)
        orig_or_updated_loc = location or orig_image_meta.get('location', None)
        if orig_or_updated_loc:
            self.update_store_acls(req, id, orig_or_updated_loc,
                                   public=is_public)

        if reactivating:
            msg = _("Attempted to update Location field for an image "
                    "not in queued status.")
            raise HTTPBadRequest(explanation=msg,
                                 request=req,
                                 content_type="text/plain")

        try:
            if location:
                image_meta['size'] = self._get_size(req.context, image_meta,
                                                    location)

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
                LOG.error(line)
            self.notifier.error('image.update', msg)
            raise HTTPBadRequest(explanation=msg,
                                 request=req,
                                 content_type="text/plain")
        except exception.NotFound, e:
            msg = ("Failed to find image to update: %(e)s" % locals())
            for line in msg.split('\n'):
                LOG.info(line)
            self.notifier.info('image.update', msg)
            raise HTTPNotFound(explanation=msg,
                               request=req,
                               content_type="text/plain")
        except exception.Forbidden, e:
            msg = ("Forbidden to update image: %(e)s" % locals())
            for line in msg.split('\n'):
                LOG.info(line)
            self.notifier.info('image.update', msg)
            raise HTTPForbidden(explanation=msg,
                                request=req,
                                content_type="text/plain")
        else:
            self.notifier.info('image.update', image_meta)

        # Prevent client from learning the location, as it
        # could contain security credentials
        image_meta.pop('location', None)

        return {'image_meta': image_meta}

    @utils.mutating
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

        image = self.get_image_meta_or_404(req, id)
        if image['protected']:
            msg = _("Image is protected")
            LOG.debug(msg)
            raise HTTPForbidden(explanation=msg,
                                request=req,
                                content_type="text/plain")

        if image['location'] and CONF.delayed_delete:
            status = 'pending_delete'
        else:
            status = 'deleted'

        try:
            # Delete the image from the registry first, since we rely on it
            # for authorization checks.
            # See https://bugs.launchpad.net/glance/+bug/1065187
            registry.update_image_metadata(req.context, id, {'status': status})
            registry.delete_image_metadata(req.context, id)

            # The image's location field may be None in the case
            # of a saving or queued image, therefore don't ask a backend
            # to delete the image if the backend doesn't yet store it.
            # See https://bugs.launchpad.net/glance/+bug/747799
            if image['location']:
                if CONF.delayed_delete:
                    schedule_delayed_delete_from_backend(image['location'], id)
                else:
                    safe_delete_from_backend(image['location'],
                                             req.context, id)
        except exception.NotFound, e:
            msg = ("Failed to find image to delete: %(e)s" % locals())
            for line in msg.split('\n'):
                LOG.info(line)
            self.notifier.info('image.delete', msg)
            raise HTTPNotFound(explanation=msg,
                               request=req,
                               content_type="text/plain")
        except exception.Forbidden, e:
            msg = ("Forbidden to delete image: %(e)s" % locals())
            for line in msg.split('\n'):
                LOG.info(line)
            self.notifier.info('image.delete', msg)
            raise HTTPForbidden(explanation=msg,
                                request=req,
                                content_type="text/plain")
        else:
            self.notifier.info('image.delete', image)

    def get_store_or_400(self, request, scheme):
        """
        Grabs the storage backend for the supplied store name
        or raises an HTTPBadRequest (400) response

        :param request: The WSGI/Webob Request object
        :param scheme: The backend store scheme

        :raises HTTPNotFound if store does not exist
        """
        try:
            return get_store_from_scheme(request.context, scheme)
        except exception.UnknownScheme:
            msg = _("Store for scheme %s not found")
            LOG.error(msg % scheme)
            raise HTTPBadRequest(explanation=msg,
                                 request=request,
                                 content_type='text/plain')

    def verify_scheme_or_exit(self, scheme):
        """
        Verifies availability of the storage backend for the
        given scheme or exits

        :param scheme: The backend store scheme
        """
        try:
            get_store_from_scheme(context.RequestContext(), scheme)
        except exception.UnknownScheme:
            msg = _("Store for scheme %s not found")
            LOG.error(msg % scheme)
            # message on stderr will only be visible if started directly via
            # bin/glance-api, as opposed to being daemonized by glance-control
            sys.stderr.write(msg % scheme)
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
            raise HTTPBadRequest(explanation=msg, request=request)

        image_meta = result['image_meta']
        image_meta = validate_image_meta(request, image_meta)
        if request.content_length:
            image_size = request.content_length
        elif 'size' in image_meta:
            image_size = image_meta['size']
        else:
            image_size = None

        data = request.body_file if self.has_body(request) else None

        if image_size is None and data is not None:
            data = utils.LimitingReader(data, CONF.image_size_cap)

            #NOTE(bcwaldon): this is a hack to make sure the downstream code
            # gets the correct image data
            request.body_file = data

        elif image_size > CONF.image_size_cap:
            max_image_size = CONF.image_size_cap
            msg = _("Denying attempt to upload image larger than %d bytes.")
            LOG.warn(msg % max_image_size)
            raise HTTPBadRequest(explanation=msg % max_image_size,
                                 request=request)

        result['image_data'] = data
        return result

    def create(self, request):
        return self._deserialize(request)

    def update(self, request):
        return self._deserialize(request)


class ImageSerializer(wsgi.JSONResponseSerializer):
    """Handles serialization of specific controller method responses."""

    def __init__(self):
        self.notifier = notifier.Notifier()

    def _inject_location_header(self, response, image_meta):
        location = self._get_image_location(image_meta)
        response.headers['Location'] = location.encode('utf-8')

    def _inject_checksum_header(self, response, image_meta):
        if image_meta['checksum'] is not None:
            response.headers['ETag'] = image_meta['checksum'].encode('utf-8')

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
            response.headers[k.encode('utf-8')] = v.encode('utf-8')

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
        image_id = image_meta['id']

        image_iter = result['image_iterator']
        # image_meta['size'] should be an int, but could possibly be a str
        expected_size = int(image_meta['size'])
        response.app_iter = common.size_checked_iter(
                response, image_meta, expected_size, image_iter, self.notifier)
        # Using app_iter blanks content-length, so we set it here...
        response.headers['Content-Length'] = str(image_meta['size'])
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


def create_resource():
    """Images resource factory method"""
    deserializer = ImageDeserializer()
    serializer = ImageSerializer()
    return wsgi.Resource(Controller(), deserializer, serializer)
