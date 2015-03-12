# Copyright 2011 OpenStack Foundation
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

from oslo_log import log as logging
import webob

from glance.api.common import size_checked_iter
from glance.api import policy
from glance.api.v1 import images
from glance.common import exception
from glance.common import utils
from glance.common import wsgi
import glance.db
from glance import i18n
from glance import image_cache
from glance import notifier
import glance.registry.client.v1.api as registry

LOG = logging.getLogger(__name__)
_LI = i18n._LI
_LE = i18n._LE

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
        self.policy = policy.Enforcer()
        LOG.info(_LI("Initialized image cache middleware"))
        super(CacheFilter, self).__init__(app)

    def _verify_metadata(self, image_meta):
        """
        Sanity check the 'deleted' and 'size' metadata values.
        """
        # NOTE: admins can see image metadata in the v1 API, but shouldn't
        # be able to download the actual image data.
        if image_meta['status'] == 'deleted' and image_meta['deleted']:
            raise exception.NotFound()

        if not image_meta['size']:
            # override image size metadata with the actual cached
            # file size, see LP Bug #900959
            image_meta['size'] = self.cache.get_image_size(image_meta['id'])

    @staticmethod
    def _match_request(request):
        """Determine the version of the url and extract the image id

        :returns tuple of version and image id if the url is a cacheable,
                 otherwise None
        """
        for ((version, method), pattern) in PATTERNS.items():
            if request.method != method:
                continue
            match = pattern.match(request.path_info)
            if match is None:
                continue
            image_id = match.group(1)
            # Ensure the image id we got looks like an image id to filter
            # out a URI like /images/detail. See LP Bug #879136
            if image_id != 'detail':
                return (version, method, image_id)

    def _enforce(self, req, action, target=None):
        """Authorize an action against our policies"""
        if target is None:
            target = {}
        try:
            self.policy.enforce(req.context, action, target)
        except exception.Forbidden as e:
            LOG.debug("User not permitted to perform '%s' action", action)
            raise webob.exc.HTTPForbidden(explanation=e.msg, request=req)

    def _get_v1_image_metadata(self, request, image_id):
        """
        Retrieves image metadata using registry for v1 api and creates
        dictionary-like mash-up of image core and custom properties.
        """
        try:
            image_metadata = registry.get_image_metadata(request.context,
                                                         image_id)
            return utils.create_mashup_dict(image_metadata)
        except exception.NotFound as e:
            LOG.debug("No metadata found for image '%s'", image_id)
            raise webob.exc.HTTPNotFound(explanation=e.msg, request=request)

    def _get_v2_image_metadata(self, request, image_id):
        """
        Retrieves image and for v2 api and creates adapter like object
        to access image core or custom properties on request.
        """
        db_api = glance.db.get_api()
        image_repo = glance.db.ImageRepo(request.context, db_api)
        try:
            image = image_repo.get(image_id)
            # Storing image object in request as it is required in
            # _process_v2_request call.
            request.environ['api.cache.image'] = image

            return policy.ImageTarget(image)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg, request=request)

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

        self._stash_request_info(request, image_id, method, version)

        if request.method != 'GET' or not self.cache.is_cached(image_id):
            return None
        method = getattr(self, '_get_%s_image_metadata' % version)
        image_metadata = method(request, image_id)

        # Deactivated images shall not be served from cache
        if image_metadata['status'] == 'deactivated':
            return None

        try:
            self._enforce(request, 'download_image', target=image_metadata)
        except exception.Forbidden:
            return None

        LOG.debug("Cache hit for image '%s'", image_id)
        image_iterator = self.get_from_cache(image_id)
        method = getattr(self, '_process_%s_request' % version)

        try:
            return method(request, image_id, image_iterator, image_metadata)
        except exception.ImageNotFound:
            msg = _LE("Image cache contained image file for image '%s', "
                      "however the registry did not contain metadata for "
                      "that image!") % image_id
            LOG.error(msg)
            self.cache.delete_cached_image(image_id)

    @staticmethod
    def _stash_request_info(request, image_id, method, version):
        """
        Preserve the image id, version and request method for later retrieval
        """
        request.environ['api.cache.image_id'] = image_id
        request.environ['api.cache.method'] = method
        request.environ['api.cache.version'] = version

    @staticmethod
    def _fetch_request_info(request):
        """
        Preserve the cached image id, version for consumption by the
        process_response method of this middleware
        """
        try:
            image_id = request.environ['api.cache.image_id']
            method = request.environ['api.cache.method']
            version = request.environ['api.cache.version']
        except KeyError:
            return None
        else:
            return (image_id, method, version)

    def _process_v1_request(self, request, image_id, image_iterator,
                            image_meta):
        # Don't display location
        if 'location' in image_meta:
            del image_meta['location']
        image_meta.pop('location_data', None)
        self._verify_metadata(image_meta)

        response = webob.Response(request=request)
        raw_response = {
            'image_iterator': image_iterator,
            'image_meta': image_meta,
        }
        return self.serializer.show(response, raw_response)

    def _process_v2_request(self, request, image_id, image_iterator,
                            image_meta):
        # We do some contortions to get the image_metadata so
        # that we can provide it to 'size_checked_iter' which
        # will generate a notification.
        # TODO(mclaren): Make notification happen more
        # naturally once caching is part of the domain model.
        image = request.environ['api.cache.image']
        self._verify_metadata(image_meta)
        response = webob.Response(request=request)
        response.app_iter = size_checked_iter(response, image_meta,
                                              image_meta['size'],
                                              image_iterator,
                                              notifier.Notifier())
        # NOTE (flwang): Set the content-type, content-md5 and content-length
        # explicitly to be consistent with the non-cache scenario.
        # Besides, it's not worth the candle to invoke the "download" method
        # of ResponseSerializer under image_data. Because method "download"
        # will reset the app_iter. Then we have to call method
        # "size_checked_iter" to avoid missing any notification. But after
        # call "size_checked_iter", we will lose the content-md5 and
        # content-length got by the method "download" because of this issue:
        # https://github.com/Pylons/webob/issues/86
        response.headers['Content-Type'] = 'application/octet-stream'
        response.headers['Content-MD5'] = image.checksum
        response.headers['Content-Length'] = str(image.size)
        return response

    def process_response(self, resp):
        """
        We intercept the response coming back from the main
        images Resource, removing image file from the cache
        if necessary
        """
        status_code = self.get_status_code(resp)
        if not 200 <= status_code < 300:
            return resp

        try:
            (image_id, method, version) = self._fetch_request_info(
                resp.request)
        except TypeError:
            return resp

        if method == 'GET' and status_code == 204:
            # Bugfix:1251055 - Don't cache non-existent image files.
            # NOTE: Both GET for an image without locations and DELETE return
            # 204 but DELETE should be processed.
            return resp

        method_str = '_process_%s_response' % method
        try:
            process_response_method = getattr(self, method_str)
        except AttributeError:
            LOG.error(_LE('could not find %s') % method_str)
            # Nothing to do here, move along
            return resp
        else:
            return process_response_method(resp, image_id, version=version)

    def _process_DELETE_response(self, resp, image_id, version=None):
        if self.cache.is_cached(image_id):
            LOG.debug("Removing image %s from cache", image_id)
            self.cache.delete_cached_image(image_id)
        return resp

    def _process_GET_response(self, resp, image_id, version=None):
        image_checksum = resp.headers.get('Content-MD5')
        if not image_checksum:
            # API V1 stores the checksum in a different header:
            image_checksum = resp.headers.get('x-image-meta-checksum')

        if not image_checksum:
            LOG.error(_LE("Checksum header is missing."))

        # fetch image_meta on the basis of version
        image_metadata = None
        if version:
            method = getattr(self, '_get_%s_image_metadata' % version)
            image_metadata = method(resp.request, image_id)
        # NOTE(zhiyan): image_cache return a generator object and set to
        # response.app_iter, it will be called by eventlet.wsgi later.
        # So we need enforce policy firstly but do it by application
        # since eventlet.wsgi could not catch webob.exc.HTTPForbidden and
        # return 403 error to client then.
        self._enforce(resp.request, 'download_image', target=image_metadata)

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
