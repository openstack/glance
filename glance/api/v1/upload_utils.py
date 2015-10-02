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
import glance_store as store_api
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import encodeutils
from oslo_utils import excutils
import webob.exc

from glance.common import exception
from glance.common import store_utils
from glance.common import utils
import glance.db
from glance import i18n
import glance.registry.client.v1.api as registry


CONF = cfg.CONF
LOG = logging.getLogger(__name__)
_ = i18n._
_LE = i18n._LE
_LI = i18n._LI


def initiate_deletion(req, location_data, id):
    """
    Deletes image data from the location of backend store.

    :param req: The WSGI/Webob Request object
    :param location_data: Location to the image data in a data store
    :param id: Opaque image identifier
    """
    store_utils.delete_image_location_from_backend(req.context,
                                                   id, location_data)


def _kill(req, image_id, from_state):
    """
    Marks the image status to `killed`.

    :param req: The WSGI/Webob Request object
    :param image_id: Opaque image identifier
    :param from_state: Permitted current status for transition to 'killed'
    """
    # TODO(dosaboy): http://docs.openstack.org/developer/glance/statuses.html
    # needs updating to reflect the fact that queued->killed and saving->killed
    # are both allowed.
    registry.update_image_metadata(req.context, image_id,
                                   {'status': 'killed'},
                                   from_state=from_state)


def safe_kill(req, image_id, from_state):
    """
    Mark image killed without raising exceptions if it fails.

    Since _kill is meant to be called from exceptions handlers, it should
    not raise itself, rather it should just log its error.

    :param req: The WSGI/Webob Request object
    :param image_id: Opaque image identifier
    :param from_state: Permitted current status for transition to 'killed'
    """
    try:
        _kill(req, image_id, from_state)
    except Exception:
        LOG.exception(_LE("Unable to kill image %(id)s: ") % {'id': image_id})


def upload_data_to_store(req, image_meta, image_data, store, notifier):
    """
    Upload image data to specified store.

    Upload image data to the store and cleans up on error.
    """
    image_id = image_meta['id']

    db_api = glance.db.get_api()
    image_size = image_meta.get('size')

    try:
        # By default image_data will be passed as CooperativeReader object.
        # But if 'user_storage_quota' is enabled and 'remaining' is not None
        # then it will be passed as object of LimitingReader to
        # 'store_add_to_backend' method.
        image_data = utils.CooperativeReader(image_data)

        remaining = glance.api.common.check_quota(
            req.context, image_size, db_api, image_id=image_id)
        if remaining is not None:
            image_data = utils.LimitingReader(image_data, remaining)

        (uri,
         size,
         checksum,
         location_metadata) = store_api.store_add_to_backend(
             image_meta['id'],
             image_data,
             image_meta['size'],
             store,
             context=req.context)

        location_data = {'url': uri,
                         'metadata': location_metadata,
                         'status': 'active'}

        try:
            # recheck the quota in case there were simultaneous uploads that
            # did not provide the size
            glance.api.common.check_quota(
                req.context, size, db_api, image_id=image_id)
        except exception.StorageQuotaFull:
            with excutils.save_and_reraise_exception():
                LOG.info(_LI('Cleaning up %s after exceeding '
                             'the quota') % image_id)
                store_utils.safe_delete_from_backend(
                    req.context, image_meta['id'], location_data)

        def _kill_mismatched(image_meta, attr, actual):
            supplied = image_meta.get(attr)
            if supplied and supplied != actual:
                msg = (_("Supplied %(attr)s (%(supplied)s) and "
                         "%(attr)s generated from uploaded image "
                         "(%(actual)s) did not match. Setting image "
                         "status to 'killed'.") % {'attr': attr,
                                                   'supplied': supplied,
                                                   'actual': actual})
                LOG.error(msg)
                safe_kill(req, image_id, 'saving')
                initiate_deletion(req, location_data, image_id)
                raise webob.exc.HTTPBadRequest(explanation=msg,
                                               content_type="text/plain",
                                               request=req)

        # Verify any supplied size/checksum value matches size/checksum
        # returned from store when adding image
        _kill_mismatched(image_meta, 'size', size)
        _kill_mismatched(image_meta, 'checksum', checksum)

        # Update the database with the checksum returned
        # from the backend store
        LOG.debug("Updating image %(image_id)s data. "
                  "Checksum set to %(checksum)s, size set "
                  "to %(size)d", {'image_id': image_id,
                                  'checksum': checksum,
                                  'size': size})
        update_data = {'checksum': checksum,
                       'size': size}
        try:
            try:
                state = 'saving'
                image_meta = registry.update_image_metadata(req.context,
                                                            image_id,
                                                            update_data,
                                                            from_state=state)
            except exception.Duplicate:
                image = registry.get_image_metadata(req.context, image_id)
                if image['status'] == 'deleted':
                    raise exception.ImageNotFound()
                else:
                    raise
        except exception.NotAuthenticated as e:
            # Delete image data due to possible token expiration.
            LOG.debug("Authentication error - the token may have "
                      "expired during file upload. Deleting image data for "
                      " %s " % image_id)
            initiate_deletion(req, location_data, image_id)
            raise webob.exc.HTTPUnauthorized(explanation=e.msg, request=req)
        except exception.ImageNotFound:
            msg = _LI("Image %s could not be found after upload. The image may"
                      " have been deleted during the upload.") % image_id
            LOG.info(msg)

            # NOTE(jculp): we need to clean up the datastore if an image
            # resource is deleted while the image data is being uploaded
            #
            # We get "location_data" from above call to store.add(), any
            # exceptions that occur there handle this same issue internally,
            # Since this is store-agnostic, should apply to all stores.
            initiate_deletion(req, location_data, image_id)
            raise webob.exc.HTTPPreconditionFailed(explanation=msg,
                                                   request=req,
                                                   content_type='text/plain')

    except store_api.StoreAddDisabled:
        msg = _("Error in store configuration. Adding images to store "
                "is disabled.")
        LOG.exception(msg)
        safe_kill(req, image_id, 'saving')
        notifier.error('image.upload', msg)
        raise webob.exc.HTTPGone(explanation=msg, request=req,
                                 content_type='text/plain')

    except (store_api.Duplicate, exception.Duplicate) as e:
        msg = (_("Attempt to upload duplicate image: %s") %
               encodeutils.exception_to_unicode(e))
        LOG.warn(msg)
        # NOTE(dosaboy): do not delete the image since it is likely that this
        # conflict is a result of another concurrent upload that will be
        # successful.
        notifier.error('image.upload', msg)
        raise webob.exc.HTTPConflict(explanation=msg,
                                     request=req,
                                     content_type="text/plain")

    except exception.Forbidden as e:
        msg = (_("Forbidden upload attempt: %s") %
               encodeutils.exception_to_unicode(e))
        LOG.warn(msg)
        safe_kill(req, image_id, 'saving')
        notifier.error('image.upload', msg)
        raise webob.exc.HTTPForbidden(explanation=msg,
                                      request=req,
                                      content_type="text/plain")

    except store_api.StorageFull as e:
        msg = (_("Image storage media is full: %s") %
               encodeutils.exception_to_unicode(e))
        LOG.error(msg)
        safe_kill(req, image_id, 'saving')
        notifier.error('image.upload', msg)
        raise webob.exc.HTTPRequestEntityTooLarge(explanation=msg,
                                                  request=req,
                                                  content_type='text/plain')

    except store_api.StorageWriteDenied as e:
        msg = (_("Insufficient permissions on image storage media: %s") %
               encodeutils.exception_to_unicode(e))
        LOG.error(msg)
        safe_kill(req, image_id, 'saving')
        notifier.error('image.upload', msg)
        raise webob.exc.HTTPServiceUnavailable(explanation=msg,
                                               request=req,
                                               content_type='text/plain')

    except exception.ImageSizeLimitExceeded as e:
        msg = (_("Denying attempt to upload image larger than %d bytes.")
               % CONF.image_size_cap)
        LOG.warn(msg)
        safe_kill(req, image_id, 'saving')
        notifier.error('image.upload', msg)
        raise webob.exc.HTTPRequestEntityTooLarge(explanation=msg,
                                                  request=req,
                                                  content_type='text/plain')

    except exception.StorageQuotaFull as e:
        msg = (_("Denying attempt to upload image because it exceeds the "
                 "quota: %s") % encodeutils.exception_to_unicode(e))
        LOG.warn(msg)
        safe_kill(req, image_id, 'saving')
        notifier.error('image.upload', msg)
        raise webob.exc.HTTPRequestEntityTooLarge(explanation=msg,
                                                  request=req,
                                                  content_type='text/plain')

    except webob.exc.HTTPError:
        # NOTE(bcwaldon): Ideally, we would just call 'raise' here,
        # but something in the above function calls is affecting the
        # exception context and we must explicitly re-raise the
        # caught exception.
        msg = _LE("Received HTTP error while uploading image %s") % image_id
        notifier.error('image.upload', msg)
        with excutils.save_and_reraise_exception():
            LOG.exception(msg)
            safe_kill(req, image_id, 'saving')

    except (ValueError, IOError) as e:
        msg = _("Client disconnected before sending all data to backend")
        LOG.warn(msg)
        safe_kill(req, image_id, 'saving')
        raise webob.exc.HTTPBadRequest(explanation=msg,
                                       content_type="text/plain",
                                       request=req)

    except Exception as e:
        msg = _("Failed to upload image %s") % image_id
        LOG.exception(msg)
        safe_kill(req, image_id, 'saving')
        notifier.error('image.upload', msg)
        raise webob.exc.HTTPInternalServerError(explanation=msg,
                                                request=req,
                                                content_type='text/plain')

    return image_meta, location_data
