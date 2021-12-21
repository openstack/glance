# Copyright 2012 OpenStack Foundation
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

import http.client

from oslo_config import cfg
from oslo_serialization import jsonutils

from glance.tests.integration.v2 import base

CONF = cfg.CONF


class TestPropertyQuotaViolations(base.ApiTest):
    def __init__(self, *args, **kwargs):
        super(TestPropertyQuotaViolations, self).__init__(*args, **kwargs)
        self.api_flavor = 'noauth'

    def _headers(self, custom_headers=None):
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': "foo",
            'X-Roles': 'member',
        }
        base_headers.update(custom_headers or {})
        return base_headers

    def _get(self, image_id=""):
        path = ('/v2/images/%s' % image_id).rstrip('/')
        rsp, content = self.http.request(path, 'GET', headers=self._headers())
        self.assertEqual(http.client.OK, rsp.status)
        content = jsonutils.loads(content)
        return content

    def _create_image(self, body):
        path = '/v2/images'
        headers = self._headers({'content-type': 'application/json'})
        rsp, content = self.http.request(path, 'POST', headers=headers,
                                         body=jsonutils.dumps(body))
        self.assertEqual(http.client.CREATED, rsp.status)
        return jsonutils.loads(content)

    def _patch(self, image_id, body, expected_status):
        path = '/v2/images/%s' % image_id
        media_type = 'application/openstack-images-v2.1-json-patch'
        headers = self._headers({'content-type': media_type})
        rsp, content = self.http.request(path, 'PATCH', headers=headers,
                                         body=jsonutils.dumps(body))
        self.assertEqual(expected_status, rsp.status, content)
        return content

    def test_property_ops_when_quota_violated(self):
        # Image list must be empty to begin with
        image_list = self._get()['images']
        self.assertEqual(0, len(image_list))

        orig_property_quota = 10
        CONF.set_override('image_property_quota', orig_property_quota)

        # Create an image (with deployer-defined properties)
        req_body = {'name': 'testimg',
                    'disk_format': 'aki',
                    'container_format': 'aki'}
        for i in range(orig_property_quota):
            req_body['k_%d' % i] = 'v_%d' % i
        image = self._create_image(req_body)
        image_id = image['id']
        for i in range(orig_property_quota):
            self.assertEqual('v_%d' % i, image['k_%d' % i])

        # Now reduce property quota. We should be allowed to modify/delete
        # existing properties (even if the result still exceeds property quota)
        # but not add new properties nor replace existing properties with new
        # properties (as long as we're over the quota)
        self.config(image_property_quota=2)

        patch_body = [{'op': 'replace', 'path': '/k_4', 'value': 'v_4.new'}]
        image = jsonutils.loads(self._patch(image_id, patch_body,
                                            http.client.OK))
        self.assertEqual('v_4.new', image['k_4'])

        patch_body = [{'op': 'remove', 'path': '/k_7'}]
        image = jsonutils.loads(self._patch(image_id, patch_body,
                                            http.client.OK))
        self.assertNotIn('k_7', image)

        patch_body = [{'op': 'add', 'path': '/k_100', 'value': 'v_100'}]
        self._patch(image_id, patch_body, http.client.REQUEST_ENTITY_TOO_LARGE)
        image = self._get(image_id)
        self.assertNotIn('k_100', image)

        patch_body = [
            {'op': 'remove', 'path': '/k_5'},
            {'op': 'add', 'path': '/k_100', 'value': 'v_100'},
        ]
        self._patch(image_id, patch_body, http.client.REQUEST_ENTITY_TOO_LARGE)
        image = self._get(image_id)
        self.assertNotIn('k_100', image)
        self.assertIn('k_5', image)

        # temporary violations to property quota should be allowed as long as
        # it's within one PATCH request and the end result does not violate
        # quotas.
        patch_body = [{'op': 'add', 'path': '/k_100', 'value': 'v_100'},
                      {'op': 'add', 'path': '/k_99', 'value': 'v_99'}]
        to_rm = ['k_%d' % i for i in range(orig_property_quota) if i != 7]
        patch_body.extend([{'op': 'remove', 'path': '/%s' % k} for k in to_rm])
        image = jsonutils.loads(self._patch(image_id, patch_body,
                                            http.client.OK))
        self.assertEqual('v_99', image['k_99'])
        self.assertEqual('v_100', image['k_100'])
        for k in to_rm:
            self.assertNotIn(k, image)
