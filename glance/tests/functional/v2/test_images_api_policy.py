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

from glance.api import policy
from glance.tests import functional


class TestImagesPolicy(functional.SynchronousAPIBase):
    def setUp(self):
        super(TestImagesPolicy, self).setUp()
        self.policy = policy.Enforcer()

    def set_policy_rules(self, rules):
        self.policy.set_rules(
            oslo_policy.policy.Rules.from_dict(rules),
            overwrite=True)

    def start_server(self):
        with mock.patch.object(policy, 'Enforcer') as mock_enf:
            mock_enf.return_value = self.policy
            super(TestImagesPolicy, self).start_server()

    def test_image_update_basic(self):
        self.start_server()
        image_id = self._create_and_upload()

        # First make sure image update works with the default policy
        resp = self.api_patch('/v2/images/%s' % image_id,
                              {'op': 'add',
                               'path': '/mykey1',
                               'value': 'foo'})
        self.assertEqual(200, resp.status_code, resp.text)
        self.assertEqual(
            'foo',
            self.api_get('/v2/images/%s' % image_id).json['mykey1'])

        # Now disable modify_image permissions and make sure any other
        # attempts fail
        self.set_policy_rules({'get_image': '',
                               'modify_image': '!'})

        # Add should fail
        resp = self.api_patch('/v2/images/%s' % image_id,
                              {'op': 'add',
                               'path': '/mykey2',
                               'value': 'foo'})
        self.assertEqual(403, resp.status_code)
        self.assertNotIn(
            'mykey2',
            self.api_get('/v2/images/%s' % image_id).json)

        # Replace should fail, old value should persist
        resp = self.api_patch('/v2/images/%s' % image_id,
                              {'op': 'replace',
                               'path': '/mykey1',
                               'value': 'bar'})
        self.assertEqual(403, resp.status_code)
        self.assertEqual(
            'foo',
            self.api_get('/v2/images/%s' % image_id).json['mykey1'])

        # Remove should fail, old value should persist
        resp = self.api_patch('/v2/images/%s' % image_id,
                              {'op': 'remove',
                               'path': '/mykey1'})
        self.assertEqual(403, resp.status_code)
        self.assertEqual(
            'foo',
            self.api_get('/v2/images/%s' % image_id).json['mykey1'])

        # Now disable get_image permissions and we should get a 404
        # instead of a 403 when trying to do the same operation as above.
        # Remove should fail, old value should persist
        self.set_policy_rules({'get_image': '!',
                               'modify_image': '!'})
        resp = self.api_patch('/v2/images/%s' % image_id,
                              {'op': 'remove',
                               'path': '/mykey1'})
        self.assertEqual(404, resp.status_code)

    @mock.patch('glance.location._check_image_location', new=lambda *a: 0)
    @mock.patch('glance.location.ImageRepoProxy._set_acls', new=lambda *a: 0)
    def test_image_update_locations(self):
        self.config(show_multiple_locations=True)
        self.start_server()
        image_id = self._create_and_upload()

        # First make sure we can add and delete locations
        resp = self.api_patch('/v2/images/%s' % image_id,
                              {'op': 'add',
                               'path': '/locations/0',
                               'value': {'url': 'http://foo.bar',
                                         'metadata': {}}})
        self.assertEqual(200, resp.status_code, resp.text)
        self.assertEqual(2,
                         len(self.api_get(
                             '/v2/images/%s' % image_id).json['locations']))
        self.assertEqual(
            'http://foo.bar',
            self.api_get(
                '/v2/images/%s' % image_id).json['locations'][1]['url'])

        resp = self.api_patch('/v2/images/%s' % image_id,
                              {'op': 'remove',
                               'path': '/locations/0'})
        self.assertEqual(200, resp.status_code, resp.text)
        self.assertEqual(1,
                         len(self.api_get(
                             '/v2/images/%s' % image_id).json['locations']))

        # Add another while we still can so we can try to delete it below
        resp = self.api_patch('/v2/images/%s' % image_id,
                              {'op': 'add',
                               'path': '/locations/0',
                               'value': {'url': 'http://foo.baz',
                                         'metadata': {}}})
        self.assertEqual(200, resp.status_code, resp.text)
        self.assertEqual(2,
                         len(self.api_get(
                             '/v2/images/%s' % image_id).json['locations']))

        # Now disable set/delete_image_location permissions and make
        # sure any other attempts fail
        self.set_policy_rules({'get_image': '',
                               'get_image_location': '',
                               'set_image_location': '!',
                               'delete_image_location': '!'})

        # Make sure we cannot delete the above or add another
        resp = self.api_patch('/v2/images/%s' % image_id,
                              {'op': 'remove',
                               'path': '/locations/0'})
        self.assertEqual(403, resp.status_code, resp.text)
        self.assertEqual(2,
                         len(self.api_get(
                             '/v2/images/%s' % image_id).json['locations']))

        resp = self.api_patch('/v2/images/%s' % image_id,
                              {'op': 'add',
                               'path': '/locations/0',
                               'value': {'url': 'http://foo.baz',
                                         'metadata': {}}})
        self.assertEqual(403, resp.status_code, resp.text)
        self.assertEqual(2,
                         len(self.api_get(
                             '/v2/images/%s' % image_id).json['locations']))

    def test_image_get(self):
        self.start_server()

        image_id = self._create_and_upload()

        # Make sure we can get the image
        image = self.api_get('/v2/images/%s' % image_id).json
        self.assertEqual(image_id, image['id'])

        # Make sure we can list the image
        images = self.api_get('/v2/images').json['images']
        self.assertEqual(1, len(images))
        self.assertEqual(image_id, images[0]['id'])

        # Now disable get_images but allow get_image
        self.set_policy_rules({'get_images': '!',
                               'get_image': ''})

        # We should not be able to list, but still fetch the image by id
        resp = self.api_get('/v2/images')
        self.assertEqual(403, resp.status_code)
        image = self.api_get('/v2/images/%s' % image_id).json
        self.assertEqual(image_id, image['id'])

        # Now disable get_image but allow get_images
        self.set_policy_rules({'get_images': '',
                               'get_image': '!'})

        # We should be able to list, but not actually see the image in the list
        images = self.api_get('/v2/images').json['images']
        self.assertEqual(0, len(images))
        resp = self.api_get('/v2/images/%s' % image_id)
        self.assertEqual(404, resp.status_code)

        # Now disable both get_image and get_images
        self.set_policy_rules({'get_images': '!',
                               'get_image': '!'})

        # We should not be able to list or fetch by id
        resp = self.api_get('/v2/images')
        self.assertEqual(403, resp.status_code)
        resp = self.api_get('/v2/images/%s' % image_id)
        self.assertEqual(404, resp.status_code)
