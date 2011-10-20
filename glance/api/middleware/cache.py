# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
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
Transparent image file caching middleware, designed to live on
Glance API nodes. When images are requested from the API node,
this middleware caches the returned image file to local filesystem.

When subsequent requests for the same image file are received,
the local cached copy of the image file is returned.
"""

import httplib
import logging
import re
import shutil

from glance import image_cache
from glance import registry
from glance.api.v1 import images
from glance.common import exception
from glance.common import utils
from glance.common import wsgi

import webob

logger = logging.getLogger(__name__)
get_images_re = re.compile(r'^(/v\d+)*/images/(.+)$')


class CacheFilter(wsgi.Middleware):

    def __init__(self, app, options):
        self.options = options
        self.cache = image_cache.ImageCache(options)
        self.serializer = images.ImageSerializer()
        logger.info(_("Initialized image cache middleware using datadir: %s"),
                    options.get('image_cache_datadir'))
        super(CacheFilter, self).__init__(app)

    def process_request(self, request):
        """
        For requests for an image file, we check the local image
        cache. If present, we return the image file, appending
        the image metadata in headers. If not present, we pass
        the request on to the next application in the pipeline.
        """
        if request.method != 'GET':
            return None

        match = get_images_re.match(request.path)
        if not match:
            return None

        image_id = match.group(2)
        if self.cache.hit(image_id):
            logger.debug(_("Cache hit for image '%s'"), image_id)
            image_iterator = self.get_from_cache(image_id)
            context = request.context
            try:
                image_meta = registry.get_image_metadata(context, image_id)

                response = webob.Response()
                return self.serializer.show(response, {
                    'image_iterator': image_iterator,
                    'image_meta': image_meta})
            except exception.NotFound:
                msg = _("Image cache contained image file for image '%s', "
                        "however the registry did not contain metadata for "
                        "that image!" % image_id)
                logger.error(msg)
                return None

        # Make sure we're not already prefetching or caching the image
        # that just generated the miss
        if self.cache.is_image_currently_prefetching(image_id):
            logger.debug(_("Image '%s' is already being prefetched,"
                         " not tee'ing into the cache"), image_id)
            return None
        elif self.cache.is_image_currently_being_written(image_id):
            logger.debug(_("Image '%s' is already being cached,"
                         " not tee'ing into the cache"), image_id)
            return None

        # NOTE(sirp): If we're about to download and cache an
        # image which is currently in the prefetch queue, just
        # delete the queue items since we're caching it anyway
        if self.cache.is_image_queued_for_prefetch(image_id):
            self.cache.delete_queued_prefetch_image(image_id)
        return None

    def process_response(self, resp):
        """
        We intercept the response coming back from the main
        images Resource, caching image files to the cache
        """
        if not self.get_status_code(resp) == httplib.OK:
            return resp

        request = resp.request
        if request.method != 'GET':
            return resp

        match = get_images_re.match(request.path)
        if match is None:
            return resp

        image_id = match.group(2)
        if not self.cache.hit(image_id):
            # Make sure we're not already prefetching or caching the image
            # that just generated the miss
            if self.cache.is_image_currently_prefetching(image_id):
                logger.debug(_("Image '%s' is already being prefetched,"
                             " not tee'ing into the cache"), image_id)
                return resp
            if self.cache.is_image_currently_being_written(image_id):
                logger.debug(_("Image '%s' is already being cached,"
                             " not tee'ing into the cache"), image_id)
                return resp

        logger.debug(_("Tee'ing image '%s' into cache"), image_id)
        # TODO(jaypipes): This is so incredibly wasteful, but because
        # the image cache needs the image's name, we have to do this.
        # In the next iteration, remove the image cache's need for
        # any attribute other than the id...
        image_meta = registry.get_image_metadata(request.context,
                                                 image_id)
        resp.app_iter = self.get_from_store_tee_into_cache(
            image_meta, resp.app_iter)
        return resp

    def get_status_code(self, response):
        """
        Returns the integer status code from the response, which
        can be either a Webob.Response (used in testing) or httplib.Response
        """
        if hasattr(response, 'status_int'):
            return response.status_int
        return response.status

    def get_from_store_tee_into_cache(self, image_meta, image_iterator):
        """Called if cache miss"""
        with self.cache.open(image_meta, "wb") as cache_file:
            for chunk in image_iterator:
                cache_file.write(chunk)
                yield chunk

    def get_from_cache(self, image_id):
        """Called if cache hit"""
        with self.cache.open_for_read(image_id) as cache_file:
            chunks = utils.chunkiter(cache_file)
            for chunk in chunks:
                yield chunk


def filter_factory(global_conf, **local_conf):
    """
    Factory method for paste.deploy
    """
    conf = global_conf.copy()
    conf.update(local_conf)

    def filter(app):
        return CacheFilter(app, conf)

    return filter
