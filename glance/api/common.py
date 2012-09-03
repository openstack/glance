# Copyright 2012 OpenStack LLC.
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

import errno

from glance.common import exception
from glance.openstack.common import log as logging

LOG = logging.getLogger(__name__)


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
    except Exception, err:
        msg = _("An error occurred reading from backend storage "
                "for image %(image_id)s: %(err)s") % locals()
        LOG.error(msg)
        raise

    if expected_size != bytes_written:
        msg = _("Backend storage for image %(image_id)s "
                "disconnected after writing only %(bytes_written)d "
                "bytes") % locals()
        LOG.error(msg)
        raise exception.GlanceException(_("Corrupt image download for "
                                          "image %(image_id)s") % locals())


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

    except Exception, err:
        msg = _("An error occurred during image.send"
                " notification: %(err)s") % locals()
        LOG.error(msg)
