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


class TestImagesPolicy(functional.SynchronousAPIBase):
    def setUp(self):
        super(TestImagesPolicy, self).setUp()
        self.policy = policy.Enforcer(suppress_deprecation_warnings=True)

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

    def test_image_delete(self):
        self.start_server()

        image_id = self._create_and_upload()

        # Make sure we can delete the image
        resp = self.api_delete('/v2/images/%s' % image_id)
        self.assertEqual(204, resp.status_code)

        # Make sure it is really gone
        resp = self.api_get('/v2/images/%s' % image_id)
        self.assertEqual(404, resp.status_code)

        # Make sure we get a 404 trying to delete a non-existent image
        resp = self.api_delete('/v2/images/%s' % image_id)
        self.assertEqual(404, resp.status_code)

        image_id = self._create_and_upload()

        # Now disable delete permissions, but allow get_image
        self.set_policy_rules({'get_image': '',
                               'delete_image': '!'})

        # Make sure delete returns 403 because we can see the image,
        # just not delete it
        resp = self.api_delete('/v2/images/%s' % image_id)
        self.assertEqual(403, resp.status_code)

        # Now disable delete permissions, including get_image
        self.set_policy_rules({'get_image': '!',
                               'delete_image': '!'})

        # Make sure delete returns 404 because we can not see nor
        # delete it
        resp = self.api_delete('/v2/images/%s' % image_id)
        self.assertEqual(404, resp.status_code)

        # Now allow delete, but disallow get_image, just to prove that
        # you do not need get_image in order to be granted delete, and
        # that we only use it for error code determination if
        # permission is denied.
        self.set_policy_rules({'get_image': '!',
                               'delete_image': ''})

        # Make sure delete returns 204 because even though we can not
        # see the image, we can delete it
        resp = self.api_delete('/v2/images/%s' % image_id)
        self.assertEqual(204, resp.status_code)

    def test_image_upload(self):
        self.start_server()

        # Make sure we can upload the image
        self._create_and_upload(expected_code=204)

        # Now disable upload permissions, but allow get_image
        self.set_policy_rules({
            'add_image': '',
            'get_image': '',
            'upload_image': '!'
        })

        # Make sure upload returns 403 because we can see the image,
        # just not upload data to it
        self._create_and_upload(expected_code=403)

        # Now disable upload permissions, including get_image
        self.set_policy_rules({
            'add_image': '',
            'get_image': '!',
            'upload_image': '!',
        })

        # Make sure upload returns 404 because we can not see nor
        # upload data to it
        self._create_and_upload(expected_code=404)

        # Now allow upload, but disallow get_image, just to prove that
        # you do not need get_image in order to be granted upload, and
        # that we only use it for error code determination if
        # permission is denied.
        self.set_policy_rules({
            'add_image': '',
            'get_image': '!',
            'upload_image': ''})

        # Make sure upload returns 204 because even though we can not
        # see the image, we can upload data to it
        self._create_and_upload(expected_code=204)

    def test_image_download(self):
        # NOTE(abhishekk): These tests are running without cache middleware
        self.start_server()
        image_id = self._create_and_upload()

        # First make sure we can download image
        path = '/v2/images/%s/file' % image_id
        response = self.api_get(path)
        self.assertEqual(200, response.status_code)
        self.assertEqual('IMAGEDATA', response.text)

        # Now disable download permissions, but allow get_image
        self.set_policy_rules({
            'get_image': '',
            'download_image': '!'
        })

        # Make sure download returns 403 because we can see the image,
        # just not download it
        response = self.api_get(path)
        self.assertEqual(403, response.status_code)

        # Now disable download permissions, including get_image
        self.set_policy_rules({
            'get_image': '!',
            'download_image': '!',
        })

        # Make sure download returns 404 because we can not see nor
        # download it
        response = self.api_get(path)
        self.assertEqual(404, response.status_code)

        # Now allow download, but disallow get_image, just to prove that
        # you do not need get_image in order to be granted download, and
        # that we only use it for error code determination if
        # permission is denied.
        self.set_policy_rules({
            'get_image': '!',
            'download_image': ''})

        # Make sure download returns 200 because even though we can not
        # see the image, we can download it
        response = self.api_get(path)
        self.assertEqual(200, response.status_code)
        self.assertEqual('IMAGEDATA', response.text)

    def test_image_stage(self):
        self.start_server()
        # First make sure we can perform staging operation
        self._create_and_stage(expected_code=204)

        # Now disable get_image permissions, but allow modify_image
        # should return 204 as well, means even if we can not see
        # image details, we can stage data for it.
        self.set_policy_rules({
            'get_image': '!',
            'modify_image': '',
            'add_image': ''
        })
        self._create_and_stage(expected_code=204)

        # Now allow get_image and disable modify_image should return 403
        self.set_policy_rules({
            'get_image': '',
            'modify_image': '!',
            'add_image': ''
        })
        self._create_and_stage(expected_code=403)

        # Now disabling both permissions will return 404
        self.set_policy_rules({
            'get_image': '!',
            'modify_image': '!',
            'add_image': ''
        })
        self._create_and_stage(expected_code=404)

        # create shared visibility image and stage by 2nd project should
        # return 404 until it is actually shared with that project.
        self.set_policy_rules({
            'get_image': '',
            'modify_image': '!',
            'add_image': '',
            'add_member': ''
        })
        resp = self.api_post('/v2/images',
                             json={'name': 'foo',
                                   'container_format': 'bare',
                                   'disk_format': 'raw',
                                   'visibility': 'shared'})
        self.assertEqual(201, resp.status_code, resp.text)
        image = resp.json
        # Now stage data using another project details
        headers = self._headers({
            'X-Project-Id': 'fake-tenant-id',
            'Content-Type': 'application/octet-stream'
        })
        resp = self.api_put(
            '/v2/images/%s/stage' % image['id'],
            headers=headers,
            data=b'IMAGEDATA')
        self.assertEqual(404, resp.status_code)

        # Now share image with another project and then staging
        # data by that project should return 403
        path = '/v2/images/%s/members' % image['id']
        data = {
            'member': uuids.random_member
        }
        response = self.api_post(path, json=data)
        member = response.json
        self.assertEqual(200, response.status_code)
        self.assertEqual(image['id'], member['image_id'])

        # Now stage data using another project details
        headers = self._headers({
            'X-Project-Id': uuids.random_member,
            'X-Roles': 'member',
            'Content-Type': 'application/octet-stream'
        })
        resp = self.api_put(
            '/v2/images/%s/stage' % image['id'],
            headers=headers,
            data=b'IMAGEDATA')
        self.assertEqual(403, resp.status_code)

    def test_image_deactivate(self):
        self.start_server()

        image_id = self._create_and_upload()

        # Make sure we can deactivate the image
        resp = self.api_post('/v2/images/%s/actions/deactivate' % image_id)
        self.assertEqual(204, resp.status_code)

        # Make sure it is really deactivated
        resp = self.api_get('/v2/images/%s' % image_id)
        self.assertEqual('deactivated', resp.json['status'])

        # Create another image
        image_id = self._create_and_upload()

        # Now disable deactivate permissions, but allow get_image
        self.set_policy_rules({'get_image': '',
                               'deactivate': '!'})

        # Make sure deactivate returns 403 because we can see the image,
        # just not deactivate it
        resp = self.api_post('/v2/images/%s/actions/deactivate' % image_id)
        self.assertEqual(403, resp.status_code)

        # Now disable deactivate permissions, including get_image
        self.set_policy_rules({'get_image': '!',
                               'deactivate': '!'})

        # Make sure deactivate returns 404 because we can not see nor
        # reactivate it
        resp = self.api_post('/v2/images/%s/actions/deactivate' % image_id)
        self.assertEqual(404, resp.status_code)

        # Now allow deactivate, but disallow get_image, just to prove that
        # you do not need get_image in order to be granted deactivate, and
        # that we only use it for error code determination if
        # permission is denied.
        self.set_policy_rules({'get_image': '!',
                               'deactivate': ''})

        # Make sure deactivate returns 204 because even though we can not
        # see the image, we can deactivate it
        resp = self.api_post('/v2/images/%s/actions/deactivate' % image_id)
        self.assertEqual(204, resp.status_code)

        # Make sure you can not deactivate image using non-admin role of
        # different project
        self.set_policy_rules({
            'get_image': '',
            'modify_image': '',
            'add_image': '',
            'upload_image': '',
            'add_member': '',
            'deactivate': '',
            'publicize_image': '',
            'communitize_image': ''
        })
        headers = self._headers({
            'X-Project-Id': 'fake-project-id',
            'X-Roles': 'member'
        })
        for visibility in ('community', 'shared', 'private', 'public'):
            image_id = self._create_and_upload(visibility=visibility)
            resp = self.api_post(
                '/v2/images/%s/actions/deactivate' % image_id, headers=headers)
            # 'shared' image will return 404 until it is not shared with
            # project accessing it
            if visibility == 'shared':
                self.assertEqual(404, resp.status_code)
                # Now lets share the image and try to deactivate it
                share_path = '/v2/images/%s/members' % image_id
                data = {
                    'member': 'fake-project-id'
                }
                response = self.api_post(share_path, json=data)
                member = response.json
                self.assertEqual(200, response.status_code)
                self.assertEqual(image_id, member['image_id'])

                # Now ensure deactivating image by another tenant will
                # return 403
                resp = self.api_post(
                    '/v2/images/%s/actions/deactivate' % image_id,
                    headers=headers)
                self.assertEqual(403, resp.status_code)
            elif visibility == 'private':
                # private image will also return 404 as it is not visible
                self.assertEqual(404, resp.status_code)
            else:
                # public and community visibility will return 403
                self.assertEqual(403, resp.status_code)

    def test_image_reactivate(self):
        self.start_server()

        image_id = self._create_and_upload()

        # deactivate the image
        resp = self.api_post('/v2/images/%s/actions/deactivate' % image_id)
        self.assertEqual(204, resp.status_code)

        # Make sure it is really deactivated
        resp = self.api_get('/v2/images/%s' % image_id)
        self.assertEqual('deactivated', resp.json['status'])

        # Make sure you can reactivate the image
        resp = self.api_post('/v2/images/%s/actions/reactivate' % image_id)
        self.assertEqual(204, resp.status_code)

        # Make sure it is really reactivated
        resp = self.api_get('/v2/images/%s' % image_id)
        self.assertEqual('active', resp.json['status'])

        # Deactivate it again to test further scenarios
        resp = self.api_post('/v2/images/%s/actions/deactivate' % image_id)
        self.assertEqual(204, resp.status_code)

        # Now disable reactivate permissions, but allow get_image
        self.set_policy_rules({'get_image': '',
                               'reactivate': '!'})

        # Make sure reactivate returns 403 because we can see the image,
        # just not reactivate it
        resp = self.api_post('/v2/images/%s/actions/reactivate' % image_id)
        self.assertEqual(403, resp.status_code)

        # Now disable reactivate permissions, including get_image
        self.set_policy_rules({'get_image': '!',
                               'reactivate': '!'})

        # Make sure reactivate returns 404 because we can not see nor
        # reactivate it
        resp = self.api_post('/v2/images/%s/actions/reactivate' % image_id)
        self.assertEqual(404, resp.status_code)

        # Now allow reactivate, but disallow get_image, just to prove that
        # you do not need get_image in order to be granted reactivate, and
        # that we only use it for error code determination if
        # permission is denied.
        self.set_policy_rules({'get_image': '!',
                               'reactivate': ''})

        # Make sure reactivate returns 204 because even though we can not
        # see the image, we can reactivate it
        resp = self.api_post('/v2/images/%s/actions/reactivate' % image_id)
        self.assertEqual(204, resp.status_code)

        # Make sure you can not reactivate image using non-admin role of
        # different project
        self.set_policy_rules({
            'get_image': '',
            'modify_image': '',
            'add_image': '',
            'upload_image': '',
            'add_member': '',
            'deactivate': '',
            'reactivate': '',
            'publicize_image': '',
            'communitize_image': ''
        })
        headers = self._headers({
            'X-Project-Id': 'fake-project-id',
            'X-Roles': 'member'
        })
        for visibility in ('public', 'community', 'shared', 'private'):
            image_id = self._create_and_upload(visibility=visibility)
            # deactivate the image
            resp = self.api_post(
                '/v2/images/%s/actions/deactivate' % image_id)
            self.assertEqual(204, resp.status_code)

            # try to reactivate the image
            resp = self.api_post(
                '/v2/images/%s/actions/reactivate' % image_id, headers=headers)

            # 'shared' image will return 404 until it is not shared with
            # project accessing it
            if visibility == 'shared':
                self.assertEqual(404, resp.status_code)
                # Now lets share the image and try to reactivate it
                share_path = '/v2/images/%s/members' % image_id
                data = {
                    'member': 'fake-project-id'
                }
                response = self.api_post(share_path, json=data)
                member = response.json
                self.assertEqual(200, response.status_code)
                self.assertEqual(image_id, member['image_id'])

                # Now ensure reactivating image by another tenant will
                # return 403
                resp = self.api_post(
                    '/v2/images/%s/actions/reactivate' % image_id,
                    headers=headers)
                self.assertEqual(403, resp.status_code)
            elif visibility == 'private':
                # private image will also return 404 as it is not visible
                self.assertEqual(404, resp.status_code)
            else:
                # public and community visibility will return 403
                self.assertEqual(403, resp.status_code)

    def test_delete_from_store(self):
        self.start_server()
        # First create image in multiple stores
        image_id = self._create_and_import(stores=['store1', 'store2',
                                                   'store3'])

        # Make sure we are able to delete image from the specific store
        path = "/v2/stores/store1/%s" % image_id
        response = self.api_delete(path)
        self.assertEqual(204, response.status_code)

        # Disable get_image_location and verify you will get 403
        self.set_policy_rules({
            'get_image': '',
            'delete_image_location': '',
            'get_image_location': '!'
        })
        path = "/v2/stores/store2/%s" % image_id
        response = self.api_delete(path)
        self.assertEqual(403, response.status_code)

        # Disable delete_image_location and verify you will get 403
        self.set_policy_rules({
            'get_image': '',
            'delete_image_location': '!',
            'get_image_location': ''
        })
        path = "/v2/stores/store2/%s" % image_id
        response = self.api_delete(path)
        self.assertEqual(403, response.status_code)

        # Disabling all, you will get 404
        self.set_policy_rules({
            'get_image': '!',
            'delete_image_location': '!',
            'get_image_location': '!'
        })
        path = "/v2/stores/store2/%s" % image_id
        response = self.api_delete(path)
        self.assertEqual(404, response.status_code)

        # Now allow delete_image_location and get_image_location, but disallow
        # get_image, just to prove that you do not need get_image in order
        # to be granted delete image from particular store, and
        # that we only use it for error code determination if
        # permission is denied.
        self.set_policy_rules({
            'get_image': '!',
            'delete_image_location': '',
            'get_image_location': ''
        })
        path = "/v2/stores/store2/%s" % image_id
        response = self.api_delete(path)
        self.assertEqual(204, response.status_code)

        # deleting image with non-admin will get 403
        self.set_policy_rules({
            'get_image': '',
            'delete_image_location': '',
            'get_image_location': ''
        })
        headers = self._headers({
            'X-Roles': 'member'
        })

        path = "/v2/stores/store2/%s" % image_id
        response = self.api_delete(path, headers=headers)
        self.assertEqual(403, response.status_code)
