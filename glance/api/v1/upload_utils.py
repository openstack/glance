# vim: tabstop=4 shiftwidth=4 softtabstop=4

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

from oslo.config import cfg
import webob.exc

from glance.common import exception
from glance.openstack.common import excutils
from glance.common import utils
import glance.openstack.common.log as logging
import glance.registry.client.v1.api as registry
import glance.store


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def initiate_deletion(req, location, id, delayed_delete=False):
    """
    Deletes image data from the backend store.

    :param req: The WSGI/Webob Request object
    :param location: URL to the image data in a data store
    :param image_id: Opaque image identifier
    :param delayed_delete: whether data deletion will be delayed
    """
    if delayed_delete:
        glance.store.schedule_delayed_delete_from_backend(location, id)
    else:
        glance.store.safe_delete_from_backend(location, req.context, id)


def _kill(req, image_id):
    """
    Marks the image status to `killed`.

    :param req: The WSGI/Webob Request object
    :param image_id: Opaque image identifier
    """
    registry.update_image_metadata(req.context, image_id,
                                   {'status': 'killed'})


def safe_kill(req, image_id):
    """
    Mark image killed without raising exceptions if it fails.

    Since _kill is meant to be called from exceptions handlers, it should
    not raise itself, rather it should just log its error.

    :param req: The WSGI/Webob Request object
    :param image_id: Opaque image identifier
    """
    try:
        _kill(req, image_id)
    except Exception as e:
        LOG.exception(_("Unable to kill image %(id)s: ") % {'id': image_id})


def upload_data_to_store(req, image_meta, image_data, store, notifier):
    """
    Upload image data to specified store.

    Upload image data to the store and cleans up on error.
    """
    image_id = image_meta['id']
    try:
        location, size, checksum = store.add(
            image_meta['id'],
            utils.CooperativeReader(image_data),
            image_meta['size'])

        def _kill_mismatched(image_meta, attr, actual):
            supplied = image_meta.get(attr)
            if supplied and supplied != actual:
                msg = _("Supplied %(attr)s (%(supplied)s) and "
                        "%(attr)s generated from uploaded image "
                        "(%(actual)s) did not match. Setting image "
                        "status to 'killed'.") % locals()
                LOG.error(msg)
                safe_kill(req, image_id)
                initiate_deletion(req, location, image_id, CONF.delayed_delete)
                raise webob.exc.HTTPBadRequest(explanation=msg,
                                               content_type="text/plain",
                                               request=req)

        # Verify any supplied size/checksum value matches size/checksum
        # returned from store when adding image
        _kill_mismatched(image_meta, 'size', size)
        _kill_mismatched(image_meta, 'checksum', checksum)

        # Update the database with the checksum returned
        # from the backend store
        LOG.debug(_("Updating image %(image_id)s data. "
                  "Checksum set to %(checksum)s, size set "
                  "to %(size)d"), locals())
        update_data = {'checksum': checksum,
                       'size': size}
        try:
            image_meta = registry.update_image_metadata(req.context,
                                                        image_id,
                                                        update_data)

        except exception.NotFound as e:
            msg = _("Image %s could not be found after upload. The image may "
                    "have been deleted during the upload.") % image_id
            LOG.info(msg)
            raise webob.exc.HTTPPreconditionFailed(explanation=msg,
                                                   request=req,
                                                   content_type='text/plain')

    except exception.Duplicate as e:
        msg = _("Attempt to upload duplicate image: %s") % e
        LOG.debug(msg)
        safe_kill(req, image_id)
        raise webob.exc.HTTPConflict(explanation=msg,
                                     request=req,
                                     content_type="text/plain")

    except exception.Forbidden as e:
        msg = _("Forbidden upload attempt: %s") % e
        LOG.debug(msg)
        safe_kill(req, image_id)
        raise webob.exc.HTTPForbidden(explanation=msg,
                                      request=req,
                                      content_type="text/plain")

    except exception.StorageFull as e:
        msg = _("Image storage media is full: %s") % e
        LOG.error(msg)
        safe_kill(req, image_id)
        notifier.error('image.upload', msg)
        raise webob.exc.HTTPRequestEntityTooLarge(explanation=msg,
                                                  request=req,
                                                  content_type='text/plain')

    except exception.StorageWriteDenied as e:
        msg = _("Insufficient permissions on image storage media: %s") % e
        LOG.error(msg)
        safe_kill(req, image_id)
        notifier.error('image.upload', msg)
        raise webob.exc.HTTPServiceUnavailable(explanation=msg,
                                               request=req,
                                               content_type='text/plain')

    except exception.ImageSizeLimitExceeded as e:
        msg = _("Denying attempt to upload image larger than %d bytes."
                % CONF.image_size_cap)
        LOG.info(msg)
        safe_kill(req, image_id)
        raise webob.exc.HTTPRequestEntityTooLarge(explanation=msg,
                                                  request=req,
                                                  content_type='text/plain')

    except webob.exc.HTTPError:
        #NOTE(bcwaldon): Ideally, we would just call 'raise' here,
        # but something in the above function calls is affecting the
        # exception context and we must explicitly re-raise the
        # caught exception.
        with excutils.save_and_reraise_exception():
            msg = _("Received HTTP error while uploading image %s" % image_id)
            LOG.exception(msg)
            safe_kill(req, image_id)

    except (ValueError, IOError) as e:
        msg = _("Client disconnected before sending all data to backend")
        LOG.debug(msg)
        safe_kill(req, image_id)
        raise webob.exc.HTTPBadRequest(explanation=msg,
                                       content_type="text/plain",
                                       request=req)

    except Exception as e:
        msg = _("Failed to upload image %s" % image_id)
        LOG.exception(msg)
        safe_kill(req, image_id)
        raise webob.exc.HTTPInternalServerError(explanation=msg,
                                                request=req,
                                                content_type='text/plain')

    return image_meta, location
