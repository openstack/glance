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

import webob

from glance import image_cache
from glance import registry
from glance.api.v1 import images
from glance.common import exception
from glance.common import utils
from glance.common import wsgi

logger = logging.getLogger(__name__)
get_images_re = re.compile(r'^(/v\d+)*/images/([^\/]+)$')


class CacheFilter(wsgi.Middleware):

    def __init__(self, app, conf, **local_conf):
        self.conf = conf
        self.cache = image_cache.ImageCache(conf)
        self.serializer = images.ImageSerializer(conf)
        logger.info(_("Initialized image cache middleware"))
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

        # /images/detail is unfortunately supported, so here we
        # cut out those requests and anything with a query
        # parameter...
        # See LP Bug #879136
        if '?' in image_id or image_id == 'detail':
            return None

        if self.cache.is_cached(image_id):
            logger.debug(_("Cache hit for image '%s'"), image_id)
            image_iterator = self.get_from_cache(image_id)
            context = request.context
            try:
                image_meta = registry.get_image_metadata(context, image_id)

                if not image_meta['size']:
                    # override image size metadata with the actual cached
                    # file size, see LP Bug #900959
                    image_meta['size'] = self.cache.get_image_size(image_id)

                response = webob.Response(request=request)
                return self.serializer.show(response, {
                    'image_iterator': image_iterator,
                    'image_meta': image_meta})
            except exception.NotFound:
                msg = _("Image cache contained image file for image '%s', "
                        "however the registry did not contain metadata for "
                        "that image!" % image_id)
                logger.error(msg)
        return None

    def process_response(self, resp):
        """
        We intercept the response coming back from the main
        images Resource, caching image files to the cache
        """
        if not self.get_status_code(resp) == httplib.OK:
            return resp

        request = resp.request
        if request.method not in ('GET', 'DELETE'):
            return resp

        match = get_images_re.match(request.path)
        if match is None:
            return resp

        image_id = match.group(2)
        if '?' in image_id or image_id == 'detail':
            return resp

        if self.cache.is_cached(image_id):
            if request.method == 'DELETE':
                logger.info(_("Removing image %s from cache"), image_id)
                self.cache.delete_cached_image(image_id)
            return resp

        resp.app_iter = self.cache.get_caching_iter(image_id, resp.app_iter)
        return resp

    def get_status_code(self, response):
        """
        Returns the integer status code from the response, which
        can be either a Webob.Response (used in testing) or httplib.Response
        """
        if hasattr(response, 'status_int'):
            return response.status_int
        return response.status

    def get_from_cache(self, image_id):
        """Called if cache hit"""
        with self.cache.open_for_read(image_id) as cache_file:
            chunks = utils.chunkiter(cache_file)
            for chunk in chunks:
                yield chunk
