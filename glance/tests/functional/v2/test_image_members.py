# Copyright 2025 RedHat Inc.
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

import http.client as http
import uuid

from oslo_config import cfg
from oslo_serialization import jsonutils

from glance.tests import functional


CONF = cfg.CONF

TENANT1 = str(uuid.uuid4())
TENANT2 = str(uuid.uuid4())
TENANT3 = str(uuid.uuid4())
TENANT4 = str(uuid.uuid4())


def get_auth_header(tenant, tenant_id=None,
                    role='reader,member', headers=None):
    """Return headers to authenticate as a specific tenant.

    :param tenant: Tenant for the auth token
    :param tenant_id: Optional tenant ID for the X-Tenant-Id header
    :param role: Optional user role
    :param headers: Optional list of headers to add to
    """
    if not headers:
        headers = {}
    auth_token = 'user:%s:%s' % (tenant, role)
    headers.update({'X-Auth-Token': auth_token})
    if tenant_id:
        headers.update({'X-Tenant-Id': tenant_id})
    return headers


class TestImageMembers(functional.SynchronousAPIBase):

    def setUp(self, single_store=True, bypass_headers=False):
        super().setUp(single_store=single_store,
                      bypass_headers=bypass_headers)
        self.config(image_member_quota=10)
        self.start_server(enable_cache=False, use_fake_auth=True)

    def _headers(self, custom_headers=None):
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': TENANT1,
            'X-Roles': 'reader,member',
        }
        base_headers.update(custom_headers or {})
        return base_headers

    def test_image_member_lifecycle(self):

        # Image list should be empty
        path = '/v2/images'
        response = self.api_get(path, headers=get_auth_header('tenant1'))
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        owners = ['tenant1', 'tenant2', 'admin']
        visibilities = ['community', 'private', 'public', 'shared']
        image_fixture = []
        for owner in owners:
            for visibility in visibilities:
                path = '/v2/images'
                role = 'member'
                if visibility == 'public':
                    role = 'admin'
                headers = {
                    'content-type': 'application/json',
                    'X-Auth-Token': 'createuser:%s:admin' % owner,
                    'X-Roles': role,
                }
                data = {
                    'name': '%s-%s' % (owner, visibility),
                    'visibility': visibility,
                }
                response = self.api_post(path, headers=headers, json=data)
                self.assertEqual(http.CREATED, response.status_code)
                image_fixture.append(jsonutils.loads(response.text))

        # Image list should contain 6 images for tenant1
        path = '/v2/images'
        response = self.api_get(path, headers=get_auth_header('tenant1'))
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(6, len(images))

        # Image list should contain 3 images for TENANT3
        path = '/v2/images'
        response = self.api_get(path, headers=get_auth_header(TENANT3))
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(3, len(images))

        # Add Image member for tenant1-shared image
        path = '/v2/images/%s/members' % image_fixture[3]['id']
        body = {'member': TENANT3}
        response = self.api_post(path, headers=get_auth_header('tenant1'),
                                 json=body)
        self.assertEqual(http.OK, response.status_code)
        image_member = jsonutils.loads(response.text)
        self.assertEqual(image_fixture[3]['id'], image_member['image_id'])
        self.assertEqual(TENANT3, image_member['member_id'])
        self.assertIn('created_at', image_member)
        self.assertIn('updated_at', image_member)
        self.assertEqual('pending', image_member['status'])

        # Image list should contain 3 images for TENANT3
        path = '/v2/images'
        response = self.api_get(path, headers=get_auth_header(TENANT3))
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(3, len(images))

        # Image list should contain 0 shared images for TENANT3
        # because default is accepted
        path = '/v2/images?visibility=shared'
        response = self.api_get(path, headers=get_auth_header(TENANT3))
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Image list should contain 4 images for TENANT3 with status pending
        path = '/v2/images?member_status=pending'
        response = self.api_get(path, headers=get_auth_header(TENANT3))
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(4, len(images))

        # Image list should contain 4 images for TENANT3 with status all
        path = '/v2/images?member_status=all'
        response = self.api_get(path, headers=get_auth_header(TENANT3))
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(4, len(images))

        # Image list should contain 1 image for TENANT3 with status pending
        # and visibility shared
        path = '/v2/images?member_status=pending&visibility=shared'
        response = self.api_get(path, headers=get_auth_header(TENANT3))
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(1, len(images))
        self.assertEqual(images[0]['name'], 'tenant1-shared')

        # Image list should contain 0 image for TENANT3 with status rejected
        # and visibility shared
        path = '/v2/images?member_status=rejected&visibility=shared'
        response = self.api_get(path, headers=get_auth_header(TENANT3))
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Image list should contain 0 image for TENANT3 with status accepted
        # and visibility shared
        path = '/v2/images?member_status=accepted&visibility=shared'
        response = self.api_get(path, headers=get_auth_header(TENANT3))
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Image list should contain 0 image for TENANT3 with status accepted
        # and visibility private
        path = '/v2/images?visibility=private'
        response = self.api_get(path, headers=get_auth_header(TENANT3))
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(0, len(images))

        # Image tenant2-shared's image members list should contain no members
        path = '/v2/images/%s/members' % image_fixture[7]['id']
        response = self.api_get(path, headers=get_auth_header('tenant2'))
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual(0, len(body['members']))

        # Tenant 1, who is the owner cannot change status of image member
        path = '/v2/images/%s/members/%s' % (image_fixture[3]['id'], TENANT3)
        body = {'status': 'accepted'}
        response = self.api_put(path, headers=get_auth_header('tenant1'),
                                json=body)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Tenant 1, who is the owner can get status of its own image member
        path = '/v2/images/%s/members/%s' % (image_fixture[3]['id'], TENANT3)
        response = self.api_get(path, headers=get_auth_header('tenant1'))
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual('pending', body['status'])
        self.assertEqual(image_fixture[3]['id'], body['image_id'])
        self.assertEqual(TENANT3, body['member_id'])

        # Tenant 3, who is the member can get status of its own status
        path = '/v2/images/%s/members/%s' % (image_fixture[3]['id'], TENANT3)
        response = self.api_get(path, headers=get_auth_header(TENANT3))
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual('pending', body['status'])
        self.assertEqual(image_fixture[3]['id'], body['image_id'])
        self.assertEqual(TENANT3, body['member_id'])

        # Tenant 2, who not the owner cannot get status of image member
        path = '/v2/images/%s/members/%s' % (image_fixture[3]['id'], TENANT3)
        response = self.api_get(path, headers=get_auth_header('tenant2'))
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # Tenant 3 can change status of image member
        path = '/v2/images/%s/members/%s' % (image_fixture[3]['id'], TENANT3)
        body = {'status': 'accepted'}
        response = self.api_put(path, headers=get_auth_header(TENANT3),
                                json=body)
        self.assertEqual(http.OK, response.status_code)
        image_member = jsonutils.loads(response.text)
        self.assertEqual(image_fixture[3]['id'], image_member['image_id'])
        self.assertEqual(TENANT3, image_member['member_id'])
        self.assertEqual('accepted', image_member['status'])

        # Image list should contain 4 images for TENANT3 because status is
        # accepted
        path = '/v2/images'
        response = self.api_get(path, headers=get_auth_header(TENANT3))
        self.assertEqual(http.OK, response.status_code)
        images = jsonutils.loads(response.text)['images']
        self.assertEqual(4, len(images))

        # Tenant 3 invalid status change
        path = '/v2/images/%s/members/%s' % (image_fixture[3]['id'], TENANT3)
        body = {'status': 'invalid-status'}
        response = self.api_put(path, headers=get_auth_header(TENANT3),
                                json=body)
        self.assertEqual(http.BAD_REQUEST, response.status_code)

        # Owner can Upload data to staging image
        image_id = image_fixture[3]['id']
        path = '/v2/images/%s/stage' % image_id
        headers = get_auth_header('tenant1')
        headers.update({'Content-Type': 'application/octet-stream'})
        image_data = b'YYYYY'
        response = self.api_put(path, headers=headers,
                                json=image_data)
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Tenant3: can't upload data to tenant1-shared staging image
        path = '/v2/images/%s/stage' % image_id
        image_data = b'YYYYY'
        headers.update(get_auth_header(TENANT3))
        response = self.api_put(path, headers=headers,
                                json=image_data)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Owner cannot change status of image
        path = '/v2/images/%s/members/%s' % (image_fixture[3]['id'], TENANT3)
        body = {'status': 'accepted'}
        response = self.api_put(path, headers=get_auth_header('tenant1'),
                                json=body)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Add Image member for tenant2-shared image
        path = '/v2/images/%s/members' % image_fixture[7]['id']
        body = {'member': TENANT4}
        response = self.api_post(path, headers=get_auth_header('tenant2'),
                                 json=body)
        self.assertEqual(http.OK, response.status_code)
        image_member = jsonutils.loads(response.text)
        self.assertEqual(image_fixture[7]['id'], image_member['image_id'])
        self.assertEqual(TENANT4, image_member['member_id'])
        self.assertIn('created_at', image_member)
        self.assertIn('updated_at', image_member)

        # Add Image member to public image
        path = '/v2/images/%s/members' % image_fixture[2]['id']
        body = {'member': TENANT2}
        response = self.api_post(path, headers=get_auth_header('tenant1'),
                                 json=body)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Add Image member to private image
        path = '/v2/images/%s/members' % image_fixture[1]['id']
        body = {'member': TENANT2}
        response = self.api_post(path, headers=get_auth_header('tenant1'),
                                 json=body)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Add Image member to community image
        path = '/v2/images/%s/members' % image_fixture[0]['id']
        body = {'member': TENANT2}
        response = self.api_post(path, headers=get_auth_header('tenant1'),
                                 json=body)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Image tenant1-shared's members list should contain 1 member
        path = '/v2/images/%s/members' % image_fixture[3]['id']
        response = self.api_get(path, headers=get_auth_header('tenant1'))
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual(1, len(body['members']))

        # Admin can see any members
        path = '/v2/images/%s/members' % image_fixture[3]['id']
        response = self.api_get(path, headers=get_auth_header('tenant1',
                                                              role='admin'))
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual(1, len(body['members']))

        # Image members not found for private image not owned by TENANT 1
        path = '/v2/images/%s/members' % image_fixture[7]['id']
        response = self.api_get(path, headers=get_auth_header('tenant1'))
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # Image members forbidden for public image
        path = '/v2/images/%s/members' % image_fixture[2]['id']
        response = self.api_get(path, headers=get_auth_header('tenant1'))
        self.assertIn("Only shared images have members", response.text)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Image members forbidden for community image
        path = '/v2/images/%s/members' % image_fixture[0]['id']
        response = self.api_get(path, headers=get_auth_header('tenant1'))
        self.assertIn("Only shared images have members", response.text)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Image members forbidden for private image
        path = '/v2/images/%s/members' % image_fixture[1]['id']
        response = self.api_get(path, headers=get_auth_header('tenant1'))
        self.assertIn("Only shared images have members", response.text)
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Image Member Cannot delete Image membership
        path = '/v2/images/%s/members/%s' % (image_fixture[3]['id'], TENANT3)
        response = self.api_delete(path, headers=get_auth_header(TENANT3))
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Delete Image member
        path = '/v2/images/%s/members/%s' % (image_fixture[3]['id'], TENANT3)
        response = self.api_delete(path, headers=get_auth_header('tenant1'))
        self.assertEqual(http.NO_CONTENT, response.status_code)

        # Now the image has no members
        path = '/v2/images/%s/members' % image_fixture[3]['id']
        response = self.api_get(path, headers=get_auth_header('tenant1'))
        self.assertEqual(http.OK, response.status_code)
        body = jsonutils.loads(response.text)
        self.assertEqual(0, len(body['members']))

        # Adding 11 image members should fail since configured limit is 10
        path = '/v2/images/%s/members' % image_fixture[3]['id']
        for i in range(10):
            body = {'member': str(uuid.uuid4())}
            response = self.api_post(path, headers=get_auth_header('tenant1'),
                                     json=body)
            self.assertEqual(http.OK, response.status_code)

        body = {'member': str(uuid.uuid4())}
        response = self.api_post(path, headers=get_auth_header('tenant1'),
                                 json=body)
        self.assertEqual(http.REQUEST_ENTITY_TOO_LARGE, response.status_code)

        # Get Image member should return not found for public image
        path = '/v2/images/%s/members/%s' % (image_fixture[2]['id'], TENANT3)
        response = self.api_get(path, headers=get_auth_header('tenant1'))
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # Get Image member should return not found for community image
        path = '/v2/images/%s/members/%s' % (image_fixture[0]['id'], TENANT3)
        response = self.api_get(path, headers=get_auth_header('tenant1'))
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # Get Image member should return not found for private image
        path = '/v2/images/%s/members/%s' % (image_fixture[1]['id'], TENANT3)
        response = self.api_get(path, headers=get_auth_header('tenant1'))
        self.assertEqual(http.NOT_FOUND, response.status_code)

        # Delete Image member should return forbidden for public image
        path = '/v2/images/%s/members/%s' % (image_fixture[2]['id'], TENANT3)
        response = self.api_delete(path, headers=get_auth_header('tenant1'))
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Delete Image member should return forbidden for community image
        path = '/v2/images/%s/members/%s' % (image_fixture[0]['id'], TENANT3)
        response = self.api_delete(path, headers=get_auth_header('tenant1'))
        self.assertEqual(http.FORBIDDEN, response.status_code)

        # Delete Image member should return forbidden for private image
        path = '/v2/images/%s/members/%s' % (image_fixture[1]['id'], TENANT3)
        response = self.api_delete(path, headers=get_auth_header('tenant1'))
        self.assertEqual(http.FORBIDDEN, response.status_code)


class TestMultiStoreImageMembers(TestImageMembers):

    def setUp(self):
        super().setUp(single_store=False, bypass_headers=True)
