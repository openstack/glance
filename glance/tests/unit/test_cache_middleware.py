# Copyright 2012 OpenStack, LLC
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

import webob

import glance.api.middleware.cache
from glance.tests.unit import base


class TestCacheMiddleware(base.IsolatedUnitTest):
    def test_no_match_detail(self):
        req = webob.Request.blank('/v1/images/detail')
        out = glance.api.middleware.cache.CacheFilter._match_request(req)
        self.assertTrue(out is None)

    def test_no_match_detail_with_query_params(self):
        req = webob.Request.blank('/v1/images/detail?limit=10')
        out = glance.api.middleware.cache.CacheFilter._match_request(req)
        self.assertTrue(out is None)

    def test_match_id_with_query_param(self):
        req = webob.Request.blank('/v1/images/asdf?ping=pong')
        out = glance.api.middleware.cache.CacheFilter._match_request(req)
        self.assertEqual(out, ('v1', 'GET', 'asdf'))
