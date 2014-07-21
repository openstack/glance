# Copyright 2013 OpenStack Foundation
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

import copy

import eventlet
from oslo.config import cfg
import six.moves.urllib.parse as urlparse
from webob.exc import HTTPBadRequest
from webob.exc import HTTPConflict
from webob.exc import HTTPForbidden
from webob.exc import HTTPMethodNotAllowed
from webob.exc import HTTPNotFound
from webob.exc import HTTPRequestEntityTooLarge
from webob import Response

from glance.api import common
from glance.api import policy
import glance.api.v1
from glance.api.v1 import controller
from glance.api.v1 import filters
from glance.api.v1 import upload_utils
from glance.common import exception
from glance.common import property_utils
from glance.common import utils
from glance.common import wsgi
from glance import notifier
from glance.openstack.common import excutils
from glance.openstack.common import gettextutils
import glance.openstack.common.log as logging
from glance.openstack.common import strutils
import glance.registry.client.v1.api as registry
from glance.store import get_from_backend
from glance.store import get_known_schemes
from glance.store import get_known_stores
from glance.store import get_size_from_backend
from glance.store import get_store_from_location
from glance.store import get_store_from_scheme
from glance.store import validate_location

try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

LOG = logging.getLogger(__name__)
_LI = gettextutils._LI
SUPPORTED_PARAMS = glance.api.v1.SUPPORTED_PARAMS
SUPPORTED_FILTERS = glance.api.v1.SUPPORTED_FILTERS
ACTIVE_IMMUTABLE = glance.api.v1.ACTIVE_IMMUTABLE

CONF = cfg.CONF
CONF.import_opt('disk_formats', 'glance.common.config', group='image_format')
CONF.import_opt('container_formats', 'glance.common.config',
                group='image_format')
CONF.import_opt('image_property_quota', 'glance.common.config')


def validate_image_meta(req, values):

    name = values.get('name')
    disk_format = values.get('disk_format')
    container_format = values.get('container_format')

    if 'disk_format' in values:
        if disk_format not in CONF.image_format.disk_formats:
            msg = _("Invalid disk format '%s' for image.") % disk_format
            raise HTTPBadRequest(explanation=msg, request=req)

    if 'container_format' in values:
        if container_format not in CONF.image_format.container_formats:
            msg = _("Invalid container format '%s' "
                    "for image.") % container_format
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
            msg = (_("Invalid mix of disk and container formats. "
                     "When setting a disk or container format to "
                     "one of 'aki', 'ari', or 'ami', the container "
                     "and disk formats must match."))
            raise HTTPBadRequest(explanation=msg, request=req)

    return values


def redact_loc(image_meta, copy_dict=True):
    """
    Create a shallow copy of image meta with 'location' removed
    for security (as it can contain credentials).
    """
    if copy_dict:
        new_image_meta = copy.copy(image_meta)
    else:
        new_image_meta = image_meta
    new_image_meta.pop('location', None)
    new_image_meta.pop('location_data', None)
    return new_image_meta


def _ns(tag):
    ovf="{http://schemas.dmtf.org/ovf/envelope/1}"
    return ovf+tag

def _rns(tag):
    ovf="{http://schemas.dmtf.org/ovf/envelope/1}"
    return tag[len(ovf):]

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
        self.notifier = notifier.Notifier()
        registry.configure_registry_client()
        self.policy = policy.Enforcer()
        self.pool = eventlet.GreenPool(size=1024)
        if property_utils.is_property_protection_enabled():
            self.prop_enforcer = property_utils.PropertyRules(self.policy)
        else:
            self.prop_enforcer = None

    def _enforce(self, req, action):
        """Authorize an action against our policies"""
        try:
            self.policy.enforce(req.context, action, {})
        except exception.Forbidden:
            raise HTTPForbidden()

    def _enforce_image_property_quota(self,
                                      image_meta,
                                      orig_image_meta=None,
                                      purge_props=False,
                                      req=None):
        if CONF.image_property_quota < 0:
            # If value is negative, allow unlimited number of properties
            return

        props = image_meta['properties'].keys()

        # NOTE(ameade): If we are not removing existing properties,
        # take them in to account
        if (not purge_props) and orig_image_meta:
            original_props = orig_image_meta['properties'].keys()
            props.extend(original_props)
            props = set(props)

        if len(props) > CONF.image_property_quota:
            msg = (_("The limit has been exceeded on the number of allowed "
                     "image properties. Attempted: %(num)s, Maximum: "
                     "%(quota)s") % {'num': len(props),
                                     'quota': CONF.image_property_quota})
            LOG.info(msg)
            raise HTTPRequestEntityTooLarge(explanation=msg,
                                            request=req,
                                            content_type="text/plain")

    def _enforce_create_protected_props(self, create_props, req):
        """
        Check request is permitted to create certain properties

        :param create_props: List of properties to check
        :param req: The WSGI/Webob Request object

        :raises HTTPForbidden if request forbidden to create a property
        """
        if property_utils.is_property_protection_enabled():
            for key in create_props:
                if (self.prop_enforcer.check_property_rules(
                        key, 'create', req.context) is False):
                    msg = "Property '%s' is protected" % key
                    LOG.debug(msg)
                    raise HTTPForbidden(explanation=msg,
                                        request=req,
                                        content_type="text/plain")

    def _enforce_read_protected_props(self, image_meta, req):
        """
        Remove entries from metadata properties if they are read protected

        :param image_meta: Mapping of metadata about image
        :param req: The WSGI/Webob Request object
        """
        if property_utils.is_property_protection_enabled():
            for key in image_meta['properties'].keys():
                if (self.prop_enforcer.check_property_rules(
                        key, 'read', req.context) is False):
                    image_meta['properties'].pop(key)

    def _enforce_update_protected_props(self, update_props, image_meta,
                                        orig_meta, req):
        """
        Check request is permitted to update certain properties.  Read
        permission is required to delete a property.

        If the property value is unchanged, i.e. a noop, it is permitted,
        however, it is important to ensure read access first.  Otherwise the
        value could be discovered using brute force.

        :param update_props: List of properties to check
        :param image_meta: Mapping of proposed new metadata about image
        :param orig_meta: Mapping of existing metadata about image
        :param req: The WSGI/Webob Request object

        :raises HTTPForbidden if request forbidden to create a property
        """
        if property_utils.is_property_protection_enabled():
            for key in update_props:
                has_read = self.prop_enforcer.check_property_rules(
                    key, 'read', req.context)
                if ((self.prop_enforcer.check_property_rules(
                        key, 'update', req.context) is False and
                        image_meta['properties'][key] !=
                        orig_meta['properties'][key]) or not has_read):
                    msg = "Property '%s' is protected" % key
                    LOG.debug(msg)
                    raise HTTPForbidden(explanation=msg,
                                        request=req,
                                        content_type="text/plain")

    def _enforce_delete_protected_props(self, delete_props, image_meta,
                                        orig_meta, req):
        """
        Check request is permitted to delete certain properties.  Read
        permission is required to delete a property.

        Note, the absence of a property in a request does not necessarily
        indicate a delete.  The requester may not have read access, and so can
        not know the property exists.  Hence, read access is a requirement for
        delete, otherwise the delete is ignored transparently.

        :param delete_props: List of properties to check
        :param image_meta: Mapping of proposed new metadata about image
        :param orig_meta: Mapping of existing metadata about image
        :param req: The WSGI/Webob Request object

        :raises HTTPForbidden if request forbidden to create a property
        """
        if property_utils.is_property_protection_enabled():
            for key in delete_props:
                if (self.prop_enforcer.check_property_rules(
                        key, 'read', req.context) is False):
                    # NOTE(bourke): if read protected, re-add to image_meta to
                    # prevent deletion
                    image_meta['properties'][key] = \
                        orig_meta['properties'][key]
                elif (self.prop_enforcer.check_property_rules(
                        key, 'delete', req.context) is False):
                    msg = "Property '%s' is protected" % key
                    LOG.debug(msg)
                    raise HTTPForbidden(explanation=msg,
                                        request=req,
                                        content_type="text/plain")

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
        except exception.Invalid as e:
            raise HTTPBadRequest(explanation=e.msg, request=req)

        return dict(images=images)

    def detail(self, req):
        """
        Returns detailed information for all available images

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
        if req.method == 'HEAD':
            msg = (_("This operation is currently not permitted on "
                     "Glance images details."))
            raise HTTPMethodNotAllowed(explanation=msg,
                                       headers={'Allow': 'GET'},
                                       body_template='${explanation}')
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
                redact_loc(image, copy_dict=False)
                self._enforce_read_protected_props(image, req)
        except exception.Invalid as e:
            raise HTTPBadRequest(explanation=e.msg, request=req)
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

        # Fix for LP Bug #1132294
        # Ensure all shared images are returned in v1
        params['member_status'] = 'all'
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
                    raise HTTPBadRequest(_('Bad value passed to filter '
                                           '%(filter)s got %(val)s')
                                         % {'filter': param,
                                            'val': query_filters[param]})
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
        image_meta = redact_loc(image_meta)
        self._enforce_read_protected_props(image_meta, req)
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
            pieces = urlparse.urlparse(source)
            schemes = [scheme for scheme in get_known_schemes()
                       if scheme != 'file']
            for scheme in schemes:
                if pieces.scheme == scheme:
                    return source
            msg = "External sourcing not supported for store %s" % source
            LOG.debug(msg)
            raise HTTPBadRequest(explanation=msg,
                                 request=req,
                                 content_type="text/plain")

    @staticmethod
    def _copy_from(req):
        return req.headers.get('x-glance-api-copy-from')

    def _external_source(self, image_meta, req):
        source = image_meta.get('location')
        if source is not None:
            self._enforce(req, 'set_image_location')
        else:
            source = Controller._copy_from(req)
        return Controller._validate_source(source, req)

    @staticmethod
    def _get_from_store(context, where):
        try:
            image_data, image_size = get_from_backend(context, where)
        except exception.NotFound as e:
            raise HTTPNotFound(explanation=e.msg)
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

        self._enforce_read_protected_props(image_meta, req)

        if image_meta.get('size') == 0:
            image_iterator = iter([])
        else:
            image_iterator, size = self._get_from_store(req.context,
                                                        image_meta['location'])
            image_iterator = utils.cooperative_iter(image_iterator)
            image_meta['size'] = size or image_meta['size']

        image_meta = redact_loc(image_meta)
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
        store = image_meta.get('store')
        if store and store not in get_known_stores():
            msg = "Required store %s is invalid" % store
            LOG.debug(msg)
            raise HTTPBadRequest(explanation=msg,
                                 content_type='text/plain')

        image_meta['status'] = ('active' if image_meta.get('size') == 0
                                else 'queued')

        if location:
            try:
                store = get_store_from_location(location)
            except exception.BadStoreUri:
                msg = "Invalid location %s" % location
                LOG.debug(msg)
                raise HTTPBadRequest(explanation=msg,
                                     request=req,
                                     content_type="text/plain")
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
            self.notifier.info("image.create", redact_loc(image_meta))
            return image_meta
        except exception.Duplicate:
            msg = ("An image with identifier %s already exists" %
                   image_meta['id'])
            LOG.debug(msg)
            raise HTTPConflict(explanation=msg,
                               request=req,
                               content_type="text/plain")
        except exception.Invalid as e:
            msg = (_("Failed to reserve image. Got error: %s") %
                   utils.exception_to_str(e))
            for line in msg.split('\n'):
                LOG.debug(line)
            raise HTTPBadRequest(explanation=msg,
                                 request=req,
                                 content_type="text/plain")
        except exception.Forbidden:
            msg = "Forbidden to reserve image."
            LOG.debug(msg)
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
                upload_utils.safe_kill(req, image_meta['id'])
                msg = ("Copy from external source failed: %s" %
                       utils.exception_to_str(e))
                LOG.debug(msg)
                return
            image_meta['size'] = image_size or image_meta['size']
        else:
            try:
                req.get_content_type(('application/octet-stream',))
            except exception.InvalidContentType:
                upload_utils.safe_kill(req, image_meta['id'])
                msg = "Content-Type must be application/octet-stream"
                LOG.debug(msg)
                raise HTTPBadRequest(explanation=msg)

            image_data = req.body_file

        scheme = req.headers.get('x-image-meta-store', CONF.default_store)

        store = self.get_store_or_400(req, scheme)

        image_id = image_meta['id']
        LOG.debug("Setting image %s to status 'saving'", image_id)
        registry.update_image_metadata(req.context, image_id,
                                       {'status': 'saving'})

        LOG.debug("Uploading image data for image %(image_id)s "
                  "to %(scheme)s store", {'image_id': image_id,
                                          'scheme': scheme})

        self.notifier.info("image.prepare", redact_loc(image_meta))

        image_meta, location_data = upload_utils.upload_data_to_store(
            req, image_meta, image_data, store, self.notifier)

        self.notifier.info('image.upload', redact_loc(image_meta))

        return location_data

    def _activate(self, req, image_id, location_data, from_state=None):
        """
        Sets the image status to `active` and the image's location
        attribute.

        :param req: The WSGI/Webob Request object
        :param image_id: Opaque image identifier
        :param location_data: Location of where Glance stored this image
        """
        image_meta = {}
        image_meta['location'] = location_data['url']
        image_meta['status'] = 'active'
        image_meta['location_data'] = [location_data]

        try:
            s = from_state
            image_meta_data = registry.update_image_metadata(req.context,
                                                             image_id,
                                                             image_meta,
                                                             from_state=s)
            self.notifier.info("image.activate", redact_loc(image_meta_data))
            self.notifier.info("image.update", redact_loc(image_meta_data))
            return image_meta_data
        except exception.Duplicate:
            with excutils.save_and_reraise_exception():
                # Delete image data since it has been supersceded by another
                # upload and re-raise.
                LOG.debug("duplicate operation - deleting image data for "
                          " %(id)s (location:%(location)s)" %
                          {'id': image_id, 'location': image_meta['location']})
                upload_utils.initiate_deletion(req, image_meta['location'],
                                               image_id, CONF.delayed_delete)
        except exception.Invalid as e:
            msg = ("Failed to activate image. Got error: %s" %
                   utils.exception_to_str(e))
            LOG.debug(msg)
            raise HTTPBadRequest(explanation=msg,
                                 request=req,
                                 content_type="text/plain")

    def _upload_and_activate(self, req, image_meta):
        """
        Safely uploads the image data in the request payload
        and activates the image in the registry after a successful
        upload.

        :param req: The WSGI/Webob Request object
        :param image_meta: Mapping of metadata about image

        :retval Mapping of updated image data
        """
        location_data = self._upload(req, image_meta)
        return self._activate(req,
                              image_meta['id'],
                              location_data,
                              from_state='saving') if location_data else None

    def _get_size(self, context, image_meta, location):
        # retrieve the image size from remote store (if not provided)
        try:
            return (image_meta.get('size', 0) or
                    get_size_from_backend(context, location))
        except (exception.NotFound, exception.BadStoreUri) as e:
            LOG.debug(e)
            raise HTTPBadRequest(explanation=e.msg, content_type="text/plain")

    def _handle_source(self, req, image_id, image_meta, image_data):
        copy_from = self._copy_from(req)
        location = image_meta.get('location')
        sources = filter(lambda x: x, (copy_from, location, image_data))
        if len(sources) >= 2:
            msg = "It's invalid to provide multiple image sources."
            LOG.debug(msg)
            raise HTTPBadRequest(explanation=msg,
                                 request=req,
                                 content_type="text/plain")
        if image_data:
            image_meta = self._validate_image_for_activation(req,
                                                             image_id,
                                                             image_meta)
            image_meta = self._upload_and_activate(req, image_meta)
        elif copy_from:
            msg = _LI('Triggering asynchronous copy from external source')
            LOG.info(msg)
            self.pool.spawn_n(self._upload_and_activate, req, image_meta)
        else:
            if location:
                try:
                    validate_location(req.context, location)
                except exception.BadStoreUri as bse:
                    raise HTTPBadRequest(explanation=bse.msg,
                                         request=req)

                self._validate_image_for_activation(req, image_id, image_meta)
                image_size_meta = image_meta.get('size')
                if image_size_meta:
                    image_size_store = get_size_from_backend(req.context,
                                                             location)
                    # NOTE(zhiyan): A returned size of zero usually means
                    # the driver encountered an error. In this case the
                    # size provided by the client will be used as-is.
                    if (image_size_store and
                            image_size_store != image_size_meta):
                        msg = ("Provided image size must match the stored "
                               "image size. (provided size: %(ps)d, "
                               "stored size: %(ss)d)" % {
                                   "ps": image_size_meta,
                                   "ss": image_size_store})
                        LOG.debug(msg)
                        raise HTTPConflict(explanation=msg,
                                           request=req,
                                           content_type="text/plain")
                location_data = {'url': location, 'metadata': {},
                                 'status': 'active'}
                image_meta = self._activate(req, image_id, location_data)
        return image_meta

    def _validate_image_for_activation(self, req, id, values):
        """Ensures that all required image metadata values are valid."""
        image = self.get_image_meta_or_404(req, id)
        if 'disk_format' not in values:
            values['disk_format'] = image['disk_format']
        if 'container_format' not in values:
            values['container_format'] = image['container_format']
        if 'name' not in values:
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
        if image_meta.get('ovf_meta_import_enable') == 'true':
            # need to break up the ova file from image_data
            # pass in ovf file for parsing
            with open('log', 'w') as f:
                xml_tags = ['Disk', 'Property']
                ovf_prop = self._parse_ovf('sampleovf.xml', xml_tags)
                image_meta['properties'].update(ovf_prop)
                f.write(str(image_meta)+'\n')
                #f.write('\n\n\n'+str(image_data)+'\n')
        else:
            with open('log', 'w') as f:
                f.write('ovf_meta_import_enable is false or not set\n')

        self._enforce(req, 'add_image')
        is_public = image_meta.get('is_public')
        if is_public:
            self._enforce(req, 'publicize_image')
        if Controller._copy_from(req):
            self._enforce(req, 'copy_from')
        if image_data or Controller._copy_from(req):
            self._enforce(req, 'upload_image')

        self._enforce_create_protected_props(image_meta['properties'].keys(),
                                             req)

        self._enforce_image_property_quota(image_meta, req=req)

        image_meta = self._reserve(req, image_meta)
        id = image_meta['id']

        image_meta = self._handle_source(req, id, image_meta, image_data)

        location_uri = image_meta.get('location')
        if location_uri:
            self.update_store_acls(req, id, location_uri, public=is_public)

        # Prevent client from learning the location, as it
        # could contain security credentials
        image_meta = redact_loc(image_meta)

        return {'image_meta': image_meta}

    def _parse_ovf(self, ovf_file, xml_tags):
        """
        :param ovf_file: The ovf filename as a string
        :param xml_tags: List of interested xml element tags to parse 

        :retval Returns the ovf properties as a key-value mapping
        """
        tree = ET.ElementTree(file=ovf_file)
        ovf_prop = {}
        with open('parse-log', 'w') as f:
            elems = (elem for elem in tree.iter() if _rns(elem.tag) in xml_tags)
            for elem in elems:
                f.write(_rns(elem.tag)+'\n')
                for attr in elem.attrib:
                    f.write(_rns(attr)+': '+elem.attrib[attr]+'\n')
                    ovf_prop[_rns(attr)] = elem.attrib[attr]
                f.write('~'*20+'\n')

        return ovf_prop

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
        if Controller._copy_from(req):
            self._enforce(req, 'copy_from')
        if image_data or Controller._copy_from(req):
            self._enforce(req, 'upload_image')

        orig_image_meta = self.get_image_meta_or_404(req, id)
        orig_status = orig_image_meta['status']

        # Do not allow any updates on a deleted image.
        # Fix for LP Bug #1060930
        if orig_status == 'deleted':
            msg = _("Forbidden to update deleted image.")
            raise HTTPForbidden(explanation=msg,
                                request=req,
                                content_type="text/plain")

        if req.context.is_admin is False:
            # Once an image is 'active' only an admin can
            # modify certain core metadata keys
            for key in ACTIVE_IMMUTABLE:
                if (orig_status == 'active' and image_meta.get(key) is not None
                        and image_meta.get(key) != orig_image_meta.get(key)):
                    msg = _("Forbidden to modify '%s' of active image.") % key
                    raise HTTPForbidden(explanation=msg,
                                        request=req,
                                        content_type="text/plain")

        # The default behaviour for a PUT /images/<IMAGE_ID> is to
        # override any properties that were previously set. This, however,
        # leads to a number of issues for the common use case where a caller
        # registers an image with some properties and then almost immediately
        # uploads an image file along with some more properties. Here, we
        # check for a special header value to be false in order to force
        # properties NOT to be purged. However we also disable purging of
        # properties if an image file is being uploaded...
        purge_props = req.headers.get('x-glance-registry-purge-props', True)
        purge_props = (strutils.bool_from_string(purge_props) and
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
        orig_or_updated_loc = location or orig_image_meta.get('location')
        if orig_or_updated_loc:
            try:
                self.update_store_acls(req, id, orig_or_updated_loc,
                                       public=is_public)
            except exception.BadStoreUri:
                msg = "Invalid location %s" % location
                LOG.debug(msg)
                raise HTTPBadRequest(explanation=msg,
                                     request=req,
                                     content_type="text/plain")

        if reactivating:
            msg = _("Attempted to update Location field for an image "
                    "not in queued status.")
            raise HTTPBadRequest(explanation=msg,
                                 request=req,
                                 content_type="text/plain")

        # ensure requester has permissions to create/update/delete properties
        # according to property-protections.conf
        orig_keys = set(orig_image_meta['properties'])
        new_keys = set(image_meta['properties'])
        self._enforce_update_protected_props(
            orig_keys.intersection(new_keys), image_meta,
            orig_image_meta, req)
        self._enforce_create_protected_props(
            new_keys.difference(orig_keys), req)
        if purge_props:
            self._enforce_delete_protected_props(
                orig_keys.difference(new_keys), image_meta,
                orig_image_meta, req)

        self._enforce_image_property_quota(image_meta,
                                           orig_image_meta=orig_image_meta,
                                           purge_props=purge_props,
                                           req=req)

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

        except exception.Invalid as e:
            msg = ("Failed to update image metadata. Got error: %s" %
                   utils.exception_to_str(e))
            LOG.debug(msg)
            raise HTTPBadRequest(explanation=msg,
                                 request=req,
                                 content_type="text/plain")
        except exception.NotFound as e:
            msg = (_("Failed to find image to update: %s") %
                   utils.exception_to_str(e))
            for line in msg.split('\n'):
                LOG.info(line)
            raise HTTPNotFound(explanation=msg,
                               request=req,
                               content_type="text/plain")
        except exception.Forbidden as e:
            msg = (_("Forbidden to update image: %s") %
                   utils.exception_to_str(e))
            for line in msg.split('\n'):
                LOG.info(line)
            raise HTTPForbidden(explanation=msg,
                                request=req,
                                content_type="text/plain")
        except (exception.Conflict, exception.Duplicate) as e:
            LOG.info(utils.exception_to_str(e))
            raise HTTPConflict(body='Image operation conflicts',
                               request=req,
                               content_type='text/plain')
        else:
            self.notifier.info('image.update', redact_loc(image_meta))

        # Prevent client from learning the location, as it
        # could contain security credentials
        image_meta = redact_loc(image_meta)

        self._enforce_read_protected_props(image_meta, req)

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
            msg = "Image is protected"
            LOG.debug(msg)
            raise HTTPForbidden(explanation=msg,
                                request=req,
                                content_type="text/plain")

        if image['status'] == 'pending_delete':
            msg = "Forbidden to delete a %s image." % image['status']
            LOG.debug(msg)
            raise HTTPForbidden(explanation=msg, request=req,
                                content_type="text/plain")
        elif image['status'] == 'deleted':
            msg = "Image %s not found." % id
            LOG.debug(msg)
            raise HTTPNotFound(explanation=msg, request=req,
                               content_type="text/plain")

        if image['location'] and CONF.delayed_delete:
            status = 'pending_delete'
        else:
            status = 'deleted'

        ori_status = image['status']

        try:
            # Update the image from the registry first, since we rely on it
            # for authorization checks.
            # See https://bugs.launchpad.net/glance/+bug/1065187
            image = registry.update_image_metadata(req.context, id,
                                                   {'status': status})

            try:
                # The image's location field may be None in the case
                # of a saving or queued image, therefore don't ask a backend
                # to delete the image if the backend doesn't yet store it.
                # See https://bugs.launchpad.net/glance/+bug/747799
                if image['location']:
                    for loc_data in image['location_data']:
                        if loc_data['status'] == 'active':
                            upload_utils.initiate_deletion(req, loc_data, id)
            except Exception:
                with excutils.save_and_reraise_exception():
                    registry.update_image_metadata(req.context, id,
                                                   {'status': ori_status})
            registry.delete_image_metadata(req.context, id)
        except exception.NotFound as e:
            msg = (_("Failed to find image to delete: %s") %
                   utils.exception_to_str(e))
            for line in msg.split('\n'):
                LOG.info(line)
            raise HTTPNotFound(explanation=msg,
                               request=req,
                               content_type="text/plain")
        except exception.Forbidden as e:
            msg = (_("Forbidden to delete image: %s") %
                   utils.exception_to_str(e))
            for line in msg.split('\n'):
                LOG.info(line)
            raise HTTPForbidden(explanation=msg,
                                request=req,
                                content_type="text/plain")
        else:
            self.notifier.info('image.delete', redact_loc(image))
            return Response(body='', status=200)

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
            msg = "Store for scheme %s not found" % scheme
            LOG.debug(msg)
            raise HTTPBadRequest(explanation=msg,
                                 request=request,
                                 content_type='text/plain')


class ImageDeserializer(wsgi.JSONRequestDeserializer):
    """Handles deserialization of specific controller method requests."""

    def _deserialize(self, request):
        result = {}
        try:
            result['image_meta'] = utils.get_image_meta_from_headers(request)
        except exception.InvalidParameterValue as e:
            msg = utils.exception_to_str(e)
            LOG.warn(msg, exc_info=True)
            raise HTTPBadRequest(explanation=e.msg, request=request)

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
            msg = (_("Denying attempt to upload image larger than %d"
                     " bytes.") % max_image_size)
            LOG.warn(msg)
            raise HTTPBadRequest(explanation=msg, request=request)

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
        self._inject_checksum_header(response, image_meta)
        return response

    def show(self, response, result):
        image_meta = result['image_meta']

        image_iter = result['image_iterator']
        # image_meta['size'] should be an int, but could possibly be a str
        expected_size = int(image_meta['size'])
        response.app_iter = common.size_checked_iter(
            response, image_meta, expected_size, image_iter, self.notifier)
        # Using app_iter blanks content-length, so we set it here...
        response.headers['Content-Length'] = str(image_meta['size'])
        response.headers['Content-Type'] = 'application/octet-stream'

        self._inject_image_meta_headers(response, image_meta)
        self._inject_checksum_header(response, image_meta)

        return response

    def update(self, response, result):
        image_meta = result['image_meta']
        response.body = self.to_json(dict(image=image_meta))
        response.headers['Content-Type'] = 'application/json'
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
