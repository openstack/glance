# Copyright 2013 Red Hat, Inc.
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
Use gzip compression if the client accepts it.
"""

import re

from oslo_log import log as logging

from glance.common import wsgi
from glance.i18n import _LI

LOG = logging.getLogger(__name__)


class GzipMiddleware(wsgi.Middleware):

    re_zip = re.compile(r'\bgzip\b')

    def __init__(self, app):
        LOG.info(_LI("Initialized gzip middleware"))
        super(GzipMiddleware, self).__init__(app)

    def process_response(self, response):
        request = response.request
        accept_encoding = request.headers.get('Accept-Encoding', '')

        if self.re_zip.search(accept_encoding):
            # NOTE(flaper87): Webob removes the content-md5 when
            # app_iter is called. We'll keep it and reset it later
            checksum = response.headers.get("Content-MD5")

            # NOTE(flaper87): We'll use lazy for images so
            # that they can be compressed without reading
            # the whole content in memory. Notice that using
            # lazy will set response's content-length to 0.
            content_type = response.headers.get("Content-Type", "")
            lazy = content_type == "application/octet-stream"

            # NOTE(flaper87): Webob takes care of the compression
            # process, it will replace the body either with a
            # compressed body or a generator - used for lazy com
            # pression - depending on the lazy value.
            #
            # Webob itself will set the Content-Encoding header.
            response.encode_content(lazy=lazy)

            if checksum:
                response.headers['Content-MD5'] = checksum

        return response
