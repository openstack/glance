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

import re

import webob

from glance.api.common import size_checked_iter
from glance.api.v1 import images
from glance.common import exception
from glance.common import utils
from glance.common import wsgi
import glance.db
from glance import image_cache
import glance.openstack.common.log as logging
from glance import notifier
from glance import registry

LOG = logging.getLogger(__name__)

PATTERNS = {
    ('v1', 'GET'): re.compile(r'^/v1/images/([^\/]+)$'),
    ('v1', 'DELETE'): re.compile(r'^/v1/images/([^\/]+)$'),
    ('v2', 'GET'): re.compile(r'^/v2/images/([^\/]+)/file$'),
    ('v2', 'DELETE'): re.compile(r'^/v2/images/([^\/]+)$')
}


class CacheFilter(wsgi.Middleware):

    def __init__(self, app):
        self.cache = image_cache.ImageCache()
        self.serializer = images.ImageSerializer()
        LOG.info(_("Initialized image cache middleware"))
        super(CacheFilter, self).__init__(app)

    def _verify_metadata(self, image_meta):
        """
        Sanity check the 'deleted' and 'size' metadata values.
        """
        # NOTE: admins can see image metadata in the v1 API, but shouldn't
        # be able to download the actual image data.
        if image_meta['deleted']:
            raise exception.NotFound()

        if not image_meta['size']:
            # override image size metadata with the actual cached
            # file size, see LP Bug #900959
            image_meta['size'] = self.cache.get_image_size(image_id)

    @staticmethod
    def _match_request(request):
        """Determine the version of the url and extract the image id

        :returns tuple of version and image id if the url is a cacheable,
                 otherwise None
        """
        for ((version, method), pattern) in PATTERNS.items():
            match = pattern.match(request.path_info)
            try:
                assert request.method == method
                image_id = match.group(1)
                # Ensure the image id we got looks like an image id to filter
                # out a URI like /images/detail. See LP Bug #879136
                assert image_id != 'detail'
            except (AttributeError, AssertionError):
                continue
            else:
                return (version, method, image_id)

    def process_request(self, request):
        """
        For requests for an image file, we check the local image
        cache. If present, we return the image file, appending
        the image metadata in headers. If not present, we pass
        the request on to the next application in the pipeline.
        """
        match = self._match_request(request)
        try:
            (version, method, image_id) = match
        except TypeError:
            # Trying to unpack None raises this exception
            return None

        self._stash_request_info(request, image_id, method)

        if request.method != 'GET' or not self.cache.is_cached(image_id):
            return None

        LOG.debug(_("Cache hit for image '%s'"), image_id)
        image_iterator = self.get_from_cache(image_id)
        method = getattr(self, '_process_%s_request' % version)

        try:
            return method(request, image_id, image_iterator)
        except exception.NotFound:
            msg = _("Image cache contained image file for image '%s', "
                    "however the registry did not contain metadata for "
                    "that image!" % image_id)
            LOG.error(msg)
            self.cache.delete_cached_image(image_id)

    @staticmethod
    def _stash_request_info(request, image_id, method):
        """
        Preserve the image id and request method for later retrieval
        """
        request.environ['api.cache.image_id'] = image_id
        request.environ['api.cache.method'] = method

    @staticmethod
    def _fetch_request_info(request):
        """
        Preserve the cached image id for consumption by the
        process_response method of this middleware
        """
        try:
            image_id = request.environ['api.cache.image_id']
            method = request.environ['api.cache.method']
        except KeyError:
            return None
        else:
            return (image_id, method)

    def _process_v1_request(self, request, image_id, image_iterator):
        image_meta = registry.get_image_metadata(request.context, image_id)
        # Don't display location
        if 'location' in image_meta:
            del image_meta['location']
        self._verify_metadata(image_meta)

        response = webob.Response(request=request)
        raw_response = {
            'image_iterator': image_iterator,
            'image_meta': image_meta,
        }
        return self.serializer.show(response, raw_response)

    def _process_v2_request(self, request, image_id, image_iterator):
        # We do some contortions to get the image_metadata so
        # that we can provide it to 'size_checked_iter' which
        # will generate a notification.
        # TODO(mclaren): Make notification happen more
        # naturally once caching is part of the domain model.
        db_api = glance.db.get_api()
        image_repo = glance.db.ImageRepo(request.context, db_api)
        image = image_repo.get(image_id)
        image_meta = glance.notifier.format_image_notification(image)
        self._verify_metadata(image_meta)
        response = webob.Response(request=request)
        response.app_iter = size_checked_iter(response, image_meta,
                                              image_meta['size'],
                                              image_iterator,
                                              notifier.Notifier())
        return response

    def process_response(self, resp):
        """
        We intercept the response coming back from the main
        images Resource, removing image file from the cache
        if necessary
        """
        if not 200 <= self.get_status_code(resp) < 300:
            return resp

        try:
            (image_id, method) = self._fetch_request_info(resp.request)
        except TypeError:
            return resp

        method_str = '_process_%s_response' % method
        try:
            process_response_method = getattr(self, method_str)
        except AttributeError:
            LOG.error(_('could not find %s') % method_str)
            # Nothing to do here, move along
            return resp
        else:
            return process_response_method(resp, image_id)

    def _process_DELETE_response(self, resp, image_id):
        if self.cache.is_cached(image_id):
            LOG.debug(_("Removing image %s from cache"), image_id)
            self.cache.delete_cached_image(image_id)
        return resp

    def _process_GET_response(self, resp, image_id):
        image_checksum = resp.headers.get('Content-MD5', None)

        if not image_checksum:
            # API V1 stores the checksum in a different header:
            image_checksum = resp.headers.get('x-image-meta-checksum', None)

        if not image_checksum:
            LOG.error(_("Checksum header is missing."))

        resp.app_iter = self.cache.get_caching_iter(image_id, image_checksum,
                                                    resp.app_iter)
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
