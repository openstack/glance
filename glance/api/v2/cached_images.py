# Copyright 2018 RedHat Inc.
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
Controller for Image Cache Management API
"""

import queue
import threading

import glance_store
from oslo_config import cfg
from oslo_log import log as logging
import webob.exc

from glance.api import policy
from glance.api.v2 import policy as api_policy
from glance.common import exception
from glance.common import wsgi
import glance.db
import glance.gateway
from glance.i18n import _
from glance import image_cache
import glance.notifier


CONF = cfg.CONF
LOG = logging.getLogger(__name__)
WORKER = None


class CacheController(object):
    """
    A controller for managing cached images.
    """

    def __init__(self, db_api=None, policy_enforcer=None, notifier=None,
                 store_api=None):
        global WORKER
        if not CONF.image_cache_dir:
            self.cache = None
        else:
            self.cache = image_cache.ImageCache()

        self.policy = policy_enforcer or policy.Enforcer()
        self.db_api = db_api or glance.db.get_api()
        self.notifier = notifier or glance.notifier.Notifier()
        self.store_api = store_api or glance_store
        self.gateway = glance.gateway.Gateway(self.db_api, self.store_api,
                                              self.notifier, self.policy)

        # Initialize the worker only if cache is enabled
        if CONF.image_cache_dir and not WORKER:
            # If we're the first, start the thread
            WORKER = CacheWorker()
            WORKER.start()
            LOG.debug('Started cache worker thread')

    def _enforce(self, req, image=None, new_policy=None):
        """Authorize request against given policy"""
        if not new_policy:
            new_policy = 'manage_image_cache'
        try:
            api_policy.CacheImageAPIPolicy(
                req.context, image=image, enforcer=self.policy,
                policy_str=new_policy).manage_image_cache()
        except exception.Forbidden:
            LOG.debug("User not permitted by '%s' policy", new_policy)
            raise webob.exc.HTTPForbidden()

        if not CONF.image_cache_dir:
            msg = _("Caching via API is not supported at this site.")
            raise webob.exc.HTTPNotFound(explanation=msg)

    def get_cached_images(self, req):
        """
        GET /cached_images

        Returns a mapping of records about cached images.
        """
        self._enforce(req)
        images = self.cache.get_cached_images()
        return dict(cached_images=images)

    def delete_cached_image(self, req, image_id):
        """
        DELETE /cached_images/<IMAGE_ID>

        Removes an image from the cache.
        """
        self._enforce(req)
        self.cache.delete_cached_image(image_id)

    def delete_cached_images(self, req):
        """
        DELETE /cached_images - Clear all active cached images

        Removes all images from the cache.
        """
        self._enforce(req)
        return dict(num_deleted=self.cache.delete_all_cached_images())

    def get_queued_images(self, req):
        """
        GET /queued_images

        Returns a mapping of records about queued images.
        """
        self._enforce(req)
        images = self.cache.get_queued_images()
        return dict(queued_images=images)

    def queue_image(self, req, image_id):
        """
        PUT /queued_images/<IMAGE_ID>

        Queues an image for caching. We do not check to see if
        the image is in the registry here. That is done by the
        prefetcher...
        """
        self._enforce(req)
        self.cache.queue_image(image_id)

    def delete_queued_image(self, req, image_id):
        """
        DELETE /queued_images/<IMAGE_ID>

        Removes an image from the cache.
        """
        self._enforce(req)
        self.cache.delete_queued_image(image_id)

    def delete_queued_images(self, req):
        """
        DELETE /queued_images - Clear all active queued images

        Removes all images from the cache.
        """
        self._enforce(req)
        return dict(num_deleted=self.cache.delete_all_queued_images())

    def delete_cache_entry(self, req, image_id):
        """
        DELETE /cache/<IMAGE_ID> - Remove image from cache

        Removes the image from cache or queue.
        """
        image_repo = self.gateway.get_repo(req.context)
        try:
            image = image_repo.get(image_id)
        except exception.NotFound:
            # We are going to raise this error only if image is
            # not present in cache or queue list
            image = None
            if not self.image_exists_in_cache(image_id):
                msg = _("Image %s not found.") % image_id
                LOG.warning(msg)
                raise webob.exc.HTTPNotFound(explanation=msg)

        self._enforce(req, new_policy='cache_delete', image=image)
        self.cache.delete_cached_image(image_id)
        self.cache.delete_queued_image(image_id)

    def image_exists_in_cache(self, image_id):
        queued_images = self.cache.get_queued_images()
        if image_id in queued_images:
            return True

        cached_images = self.cache.get_cached_images()
        if image_id in [image['image_id'] for image in cached_images]:
            return True

        return False

    def clear_cache(self, req):
        """
        DELETE /cache - Clear cache and queue

        Removes all images from cache and queue.
        """
        self._enforce(req, new_policy='cache_delete')
        target = req.headers.get('x-image-cache-clear-target', '').lower()
        if target == '':
            res = dict(cache_deleted=self.cache.delete_all_cached_images(),
                       queue_deleted=self.cache.delete_all_queued_images())
        elif target == 'cache':
            res = dict(cache_deleted=self.cache.delete_all_cached_images())
        elif target == 'queue':
            res = dict(queue_deleted=self.cache.delete_all_queued_images())
        else:
            reason = (_("If provided 'x-image-cache-clear-target' must be "
                        "'cache', 'queue' or empty string."))
            raise webob.exc.HTTPBadRequest(explanation=reason,
                                           request=req,
                                           content_type='text/plain')
        return res

    def get_cache_state(self, req):
        """
        GET /cache/ - Get currently cached and queued images

        Returns dict of cached and queued images
        """
        self._enforce(req, new_policy='cache_list')
        return dict(cached_images=self.cache.get_cached_images(),
                    queued_images=self.cache.get_queued_images())

    def queue_image_from_api(self, req, image_id):
        """
        PUT /cache/<IMAGE_ID>

        Queues an image for caching. We do not check to see if
        the image is in the registry here. That is done by the
        prefetcher...
        """
        image_repo = self.gateway.get_repo(req.context)
        try:
            image = image_repo.get(image_id)
        except exception.NotFound:
            msg = _("Image %s not found.") % image_id
            LOG.warning(msg)
            raise webob.exc.HTTPNotFound(explanation=msg)

        self._enforce(req, new_policy='cache_image', image=image)

        if image.status != 'active':
            msg = _("Only images with status active can be targeted for "
                    "queueing")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        self.cache.queue_image(image_id)
        WORKER.submit(image_id)


class CacheWorker(threading.Thread):
    EXIT_SENTINEL = object()

    def __init__(self, *args, **kwargs):
        self.q = queue.Queue(maxsize=-1)
        # NOTE(abhishekk): Importing the prefetcher just in time to avoid
        # import loop during initialization
        from glance.image_cache import prefetcher  # noqa
        self.prefetcher = prefetcher.Prefetcher()
        super().__init__(*args, **kwargs)
        # NOTE(abhishekk): Setting daemon to True because if `atexit` event
        # handler is not called due to some reason the main process will
        # not hang for the thread which will never exit.
        self.daemon = True

    def submit(self, job):
        self.q.put(job)

    def terminate(self):
        # NOTE(danms): Make the API workers call this before we exit
        # to make sure any cache operations finish.
        LOG.info('Signaling cache worker thread to exit')
        self.q.put(self.EXIT_SENTINEL)
        self.join()
        LOG.info('Cache worker thread exited')

    def run(self):
        while True:
            task = self.q.get()
            if task == self.EXIT_SENTINEL:
                LOG.debug("CacheWorker thread exiting")
                break

            LOG.debug("Processing image '%s' for caching", task)
            self.prefetcher.fetch_image_into_cache(task)
            # do whatever work you have to do on task
            self.q.task_done()
            LOG.debug("Caching of an image '%s' is complete", task)


class CachedImageDeserializer(wsgi.JSONRequestDeserializer):
    pass


class CachedImageSerializer(wsgi.JSONResponseSerializer):

    def queue_image_from_api(self, response, result):
        response.status_int = 202

    def clear_cache(self, response, result):
        response.status_int = 204

    def delete_cache_entry(self, response, result):
        response.status_int = 204


def create_resource():
    """Cached Images resource factory method"""
    deserializer = CachedImageDeserializer()
    serializer = CachedImageSerializer()
    return wsgi.Resource(CacheController(), deserializer, serializer)
