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

import re

from oslo_concurrency import lockutils
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import excutils
from oslo_utils import units

import glance.async_
from glance.common import exception
from glance.i18n import _, _LE, _LW

LOG = logging.getLogger(__name__)
CONF = cfg.CONF

GLANCE_RESERVED_NS = 'os_glance'
_CACHED_THREAD_POOL = {}


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
        with excutils.save_and_reraise_exception():
            msg = (_LE("An error occurred reading from backend storage for "
                       "image %(image_id)s: %(err)s") % {'image_id': image_id,
                                                         'err': err})
            LOG.error(msg)

    if expected_size != bytes_written:
        msg = (_LE("Backend storage for image %(image_id)s "
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
            'receiver_tenant_id': context.project_id,
            'receiver_user_id': context.user_id,
            'destination_ip': request.remote_addr,
        }
        if bytes_written != expected_size:
            notify = notifier.error
        else:
            notify = notifier.info

        notify('image.send', payload)

    except Exception as err:
        msg = (_LE("An error occurred during image.send"
                   " notification: %(err)s") % {'err': err})
        LOG.error(msg)


def get_remaining_quota(context, db_api, image_id=None):
    """Method called to see if the user is allowed to store an image.

    Checks if it is allowed based on the given size in glance based on their
    quota and current usage.

    :param context:
    :param db_api:  The db_api in use for this configuration
    :param image_id: The image that will be replaced with this new data size
    :returns: The number of bytes the user has remaining under their quota.
             None means infinity
    """

    # NOTE(jbresnah) in the future this value will come from a call to
    # keystone.
    users_quota = CONF.user_storage_quota

    # set quota must have a number optionally followed by B, KB, MB,
    # GB or TB without any spaces in between
    pattern = re.compile(r'^(\d+)((K|M|G|T)?B)?$')
    match = pattern.match(users_quota)

    if not match:
        LOG.error(_LE("Invalid value for option user_storage_quota: "
                      "%(users_quota)s"),
                  {'users_quota': users_quota})
        raise exception.InvalidOptionValue(option='user_storage_quota',
                                           value=users_quota)

    quota_value, quota_unit = (match.groups())[0:2]
    # fall back to Bytes if user specified anything other than
    # permitted values
    quota_unit = quota_unit or "B"
    factor = getattr(units, quota_unit.replace('B', 'i'), 1)
    users_quota = int(quota_value) * factor

    if users_quota <= 0:
        return

    usage = db_api.user_get_storage_usage(context,
                                          context.owner,
                                          image_id=image_id)
    return users_quota - usage


def check_quota(context, image_size, db_api, image_id=None):
    """Method called to see if the user is allowed to store an image.

    Checks if it is allowed based on the given size in glance based on their
    quota and current usage.

    :param context:
    :param image_size:  The size of the image we hope to store
    :param db_api:  The db_api in use for this configuration
    :param image_id: The image that will be replaced with this new data size
    :returns:
    """

    # NOTE(danms): If keystone quotas are enabled, those take
    # precedence and this check is a no-op.
    if CONF.use_keystone_limits:
        return

    remaining = get_remaining_quota(context, db_api, image_id=image_id)

    if remaining is None:
        return

    user = getattr(context, 'user_id', '<unknown>')

    if image_size is None:
        # NOTE(jbresnah) When the image size is None it means that it is
        # not known.  In this case the only time we will raise an
        # exception is when there is no room left at all, thus we know
        # it will not fit
        if remaining <= 0:
            LOG.warning(_LW("User %(user)s attempted to upload an image of"
                            " unknown size that will exceed the quota."
                            " %(remaining)d bytes remaining."),
                        {'user': user, 'remaining': remaining})
            raise exception.StorageQuotaFull(image_size=image_size,
                                             remaining=remaining)
        return

    if image_size > remaining:
        LOG.warning(_LW("User %(user)s attempted to upload an image of size"
                        " %(size)d that will exceed the quota. %(remaining)d"
                        " bytes remaining."),
                    {'user': user, 'size': image_size, 'remaining': remaining})
        raise exception.StorageQuotaFull(image_size=image_size,
                                         remaining=remaining)

    return remaining


def memoize(lock_name):
    def memoizer_wrapper(func):
        @lockutils.synchronized(lock_name)
        def memoizer(lock_name):
            if lock_name not in _CACHED_THREAD_POOL:
                _CACHED_THREAD_POOL[lock_name] = func()

            return _CACHED_THREAD_POOL[lock_name]

        return memoizer(lock_name)

    return memoizer_wrapper


# NOTE(danms): This is the default pool size that will be used for
# the get_thread_pool() cache wrapper below. This is a global here
# because it needs to be overridden for the pure-wsgi mode in
# wsgi_app.py where native threads are used.
DEFAULT_POOL_SIZE = 1024


def get_thread_pool(lock_name, size=None):
    """Initializes thread pool.

    If thread pool is present in cache, then returns it from cache
    else create new pool, stores it in cache and return newly created
    pool.

    @param lock_name:  Name of the lock.
    @param size: Size of pool.

    @return: ThreadPoolModel
    """

    if size is None:
        size = DEFAULT_POOL_SIZE

    @memoize(lock_name)
    def _get_thread_pool():
        threadpool_cls = glance.async_.get_threadpool_model()
        LOG.debug('Initializing named threadpool %r', lock_name)
        return threadpool_cls(size)

    return _get_thread_pool
