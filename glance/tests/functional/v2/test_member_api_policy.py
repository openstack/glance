# Copyright 2021 Red Hat, Inc.
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

from unittest import mock

import oslo_policy.policy
from oslo_utils.fixture import uuidsentinel as uuids

from glance.api import policy
from glance.tests import functional


class TestImageMembersPolicy(functional.SynchronousAPIBase):
    def setUp(self):
        super(TestImageMembersPolicy, self).setUp()
        self.policy = policy.Enforcer(suppress_deprecation_warnings=True)

    def load_data(self, share_image=False):
        output = {}
        path = "/v2/images"
        data = {
            'name': 'shared-image',
            'visibility': 'shared',
        }
        response = self.api_post(path, json=data)
        self.assertEqual(201, response.status_code)
        image_id = response.json['id']
        output['image_id'] = image_id

        if share_image:
            path = '/v2/images/%s/members' % image_id
            data = {
                'member': uuids.random_member
            }
            response = self.api_post(path, json=data)
            member = response.json
            self.assertEqual(200, response.status_code)
            self.assertEqual(image_id, member['image_id'])
            self.assertEqual('pending', member['status'])
            output['member_id'] = member['member_id']

        return output

    def set_policy_rules(self, rules):
        self.policy.set_rules(
            oslo_policy.policy.Rules.from_dict(rules),
            overwrite=True)

    def start_server(self):
        with mock.patch.object(policy, 'Enforcer') as mock_enf:
            mock_enf.return_value = self.policy
            super(TestImageMembersPolicy, self).start_server()

    def test_member_add_basic(self):
        self.start_server()
        output = self.load_data()
        path = '/v2/images/%s/members' % output['image_id']

        # Make sure we can add member to image (can share image)
        data = {
            'member': uuids.random_member
        }
        response = self.api_post(path, json=data)
        self.assertEqual(200, response.status_code)
        member = response.json
        self.assertEqual(output['image_id'], member['image_id'])
        self.assertEqual('pending', member['status'])

        # Now disable add permissions
        self.set_policy_rules({
            'add_member': '!',
            'get_image': '@'
        })

        # Make sure add returns 403
        response = self.api_post(path, json=data)
        self.assertEqual(403, response.status_code)

        # Now disable both permissions and make sure you will get
        # 404 Not Found
        self.set_policy_rules({
            'add_member': '!',
            'get_image': '!'
        })

        # Make sure add returns 404
        response = self.api_post(path, json=data)
        self.assertEqual(404, response.status_code)

    def test_member_update_basic(self):
        self.start_server()
        output = self.load_data(share_image=True)
        path = '/v2/images/%s/members/%s' % (output['image_id'],
                                             output['member_id'])
        # Make sure we can update image membership
        data = {
            'status': 'accepted'
        }
        response = self.api_put(path, json=data)
        self.assertEqual(200, response.status_code)
        member = response.json
        self.assertEqual(output['image_id'], member['image_id'])
        self.assertEqual('accepted', member['status'])

        # Now disable modify permissions
        self.set_policy_rules({
            'modify_member': '!',
            'get_image': '@'
        })

        # Make sure update returns 403
        response = self.api_put(path, json=data)
        self.assertEqual(403, response.status_code)

        # Now disable both permissions and make sure you will get
        # 404 Not Found
        self.set_policy_rules({
            'modify_member': '!',
            'get_image': '!',
            'get_member': '@'
        })
        # image owner is not allowed to update image membership so
        # passing different project in headers
        headers = self._headers({
            'X-Tenant-Id': 'fake-tenant-id',
        })
        response = self.api_put(path, headers=headers, json=data)
        self.assertEqual(404, response.status_code)

    def test_member_list_basic(self):
        self.start_server()
        output = self.load_data(share_image=True)
        path = '/v2/images/%s/members' % (output['image_id'])
        # # Make sure we can list image members
        response = self.api_get(path)
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, len(response.json['members']))

        # Now disable list permissions
        self.set_policy_rules({
            'get_members': '!',
            'get_image': '@',
        })

        # Make sure get returns 403
        response = self.api_get(path)
        self.assertEqual(403, response.status_code)

        # Now disable both permissions and make sure you will get
        # 404 Not Found
        self.set_policy_rules({
            'get_members': '!',
            'get_image': '!',
        })

        # Make sure get returns 404
        response = self.api_get(path)
        self.assertEqual(404, response.status_code)

        # Now enable get_members and disable get_member
        self.set_policy_rules({
            'get_members': '@',
            'get_member': '!',
            'get_image': '@',
        })

        # Make sure we get empty list as get_member is disabled
        response = self.api_get(path)
        self.assertEqual(200, response.status_code)
        self.assertEqual(0, len(response.json['members']))

    def test_member_get_basic(self):
        self.start_server()
        output = self.load_data(share_image=True)
        path = '/v2/images/%s/members/%s' % (
            output['image_id'],
            output['member_id'])
        # Make sure we can get member
        response = self.api_get(path)
        self.assertEqual(200, response.status_code)
        member = response.json
        self.assertEqual(output['image_id'], member['image_id'])
        self.assertEqual('pending', member['status'])

        # Now disable get permissions
        self.set_policy_rules({'get_member': '!'})

        # Make sure get returns 404 as we are not exposing it
        response = self.api_get(path)
        self.assertEqual(404, response.status_code)

    def test_member_delete_basic(self):
        self.start_server()
        output = self.load_data(share_image=True)
        path = '/v2/images/%s/members/%s' % (output['image_id'],
                                             output['member_id'])
        # Make sure we can delete image member
        response = self.api_delete(path)
        self.assertEqual(204, response.status_code)
        # Verifiy it is deleted
        response = self.api_get(path)
        self.assertEqual(404, response.status_code)

        # Now disable delete permissions and create image
        # membership again
        self.set_policy_rules({
            'delete_member': '!',
            'add_member': '@',
            'get_image': '@'
        })
        add_path = '/v2/images/%s/members' % output['image_id']
        data = {
            'member': uuids.random_member
        }
        response = self.api_post(add_path, json=data)
        self.assertEqual(200, response.status_code)

        # Make sure delete returns 403
        response = self.api_delete(path)
        self.assertEqual(403, response.status_code)

        # Now disable delete_member and get_image permission and make
        # sure you will get 404 Not Found
        self.set_policy_rules({
            'delete_member': '!',
            'get_image': '!',
            'get_member': '@'
        })
        response = self.api_delete(path)
        self.assertEqual(404, response.status_code)

    def test_image_sharing_not_allowed(self):
        # This test verifies that image having visibility other than
        # shared is not allowed for sharing
        self.start_server()
        path = "/v2/images"
        for visibility in ('community', 'private', 'public'):
            data = {
                'name': '%s-image' % visibility,
                'visibility': visibility,
            }
            # create image
            response = self.api_post(path, json=data)
            image = response.json
            self.assertEqual(201, response.status_code)
            self.assertEqual(visibility, image['visibility'])

            # Sharing image should return 403 response
            member_path = '/v2/images/%s/members' % image['id']
            data = {
                'member': uuids.random_member
            }
            response = self.api_post(member_path, json=data)
            self.assertEqual(403, response.status_code)
