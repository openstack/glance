# Copyright 2012 OpenStack Foundation.
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

from glance.common import exception
from glance.openstack.common import log as logging

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


def size_checked_iter(response, image_meta, expected_size, image_iter,
                      notifier):
    image_id = image_meta['id']
    bytes_written = 0

    def notify_image_sent_hook(env):
        image_send_notification(bytes_written, expected_size,
                                image_meta, response.request, notifier)

    # Add hook to process after response is fully sent
    if 'eventlet.posthooks' in response.request.environ:
        response.request.environ['eventlet.posthooks'].append(
            (notify_image_sent_hook, (), {}))

    try:
        for chunk in image_iter:
            yield chunk
            bytes_written += len(chunk)
    except Exception as err:
        msg = (_("An error occurred reading from backend storage "
                 "for image %(image_id)s: %(err)s") % {'image_id': image_id,
                                                       'err': err})
        LOG.error(msg)
        raise

    if expected_size != bytes_written:
        msg = (_("Backend storage for image %(image_id)s "
                 "disconnected after writing only %(bytes_written)d "
                 "bytes") % {'image_id': image_id,
                             'bytes_written': bytes_written})
        LOG.error(msg)
        raise exception.GlanceException(_("Corrupt image download for "
                                          "image %(image_id)s") %
                                        {'image_id': image_id})


def image_send_notification(bytes_written, expected_size, image_meta, request,
                            notifier):
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
            notify = notifier.error
        else:
            notify = notifier.info

        notify('image.send', payload)

    except Exception as err:
        msg = (_("An error occurred during image.send"
                 " notification: %(err)s") % {'err': err})
        LOG.error(msg)


def get_remaining_quota(context, db_api, image_id=None):
    """
    This method is called to see if the user is allowed to store an image
    of the given size in glance based on their quota and current usage.
    :param context:
    :param db_api:  The db_api in use for this configuration
    :param image_id: The image that will be replaced with this new data size
    :return: The number of bytes the user has remaining under their quota.
             None means infinity
    """

    #NOTE(jbresnah) in the future this value will come from a call to
    # keystone.
    users_quota = CONF.user_storage_quota
    if users_quota <= 0:
        return None

    usage = db_api.user_get_storage_usage(context,
                                          context.owner,
                                          image_id=image_id)
    return users_quota - usage


def check_quota(context, image_size, db_api, image_id=None):
    """
    This method is called to see if the user is allowed to store an image
    of the given size in glance based on their quota and current usage.
    :param context:
    :param image_size:  The size of the image we hope to store
    :param db_api:  The db_api in use for this configuration
    :param image_id: The image that will be replaced with this new data size
    :return:
    """

    remaining = get_remaining_quota(context, db_api, image_id=image_id)

    if remaining is None:
        return

    user = getattr(context, 'user', '<unknown>')

    if image_size is None:
        #NOTE(jbresnah) When the image size is None it means that it is
        # not known.  In this case the only time we will raise an
        # exception is when there is no room left at all, thus we know
        # it will not fit
        if remaining <= 0:
            LOG.info(_("User %(user)s attempted to upload an image of"
                       " unknown size that will exceeed the quota."
                       " %(remaining)d bytes remaining.")
                     % {'user': user, 'remaining': remaining})
            raise exception.StorageQuotaFull(image_size=image_size,
                                             remaining=remaining)
        return

    if image_size > remaining:
        LOG.info(_("User %(user)s attempted to upload an image of size"
                   " %(size)d that will exceeed the quota. %(remaining)d"
                   " bytes remaining.")
                 % {'user': user, 'size': image_size, 'remaining': remaining})
        raise exception.StorageQuotaFull(image_size=image_size,
                                         remaining=remaining)

    return remaining
