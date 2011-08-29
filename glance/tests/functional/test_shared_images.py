# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack, LLC
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

"""Functional test case that verifies private images functionality"""

import httplib2
import json

from glance.tests import functional
from glance.tests.functional import keystone_utils
from glance.tests.utils import execute, skip_if_disabled

FIVE_KB = 5 * 1024
FIVE_GB = 5 * 1024 * 1024 * 1024


class TestSharedImagesApi(keystone_utils.KeystoneTests):
    def _push_image(self):
        # First, we need to push an image up
        image_data = "*" * FIVE_KB
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'Image1'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        response, content = self._request(path, 'POST',
                                          keystone_utils.pattieblack_token,
                                          headers=headers,
                                          body=image_data)
        self.assertEqual(response.status, 201)
        data = json.loads(content)
        self.assertEqual(data['image']['id'], 1)
        self.assertEqual(data['image']['size'], FIVE_KB)
        self.assertEqual(data['image']['name'], "Image1")
        self.assertEqual(data['image']['is_public'], False)
        self.assertEqual(data['image']['owner'], 'pattieblack')
        return content

    def _request(self, path, method, auth_token, headers=None, body=None):
        http = httplib2.Http()
        headers = headers or {}
        headers['X-Auth-Token'] = auth_token
        if body:
            return http.request(path, method, headers=headers,
                                body=body)
        else:
            return http.request(path, method, headers=headers)

    @skip_if_disabled
    def test_share_image(self):
        self.cleanup()
        self.start_servers()
        # First, we need to push an image up
        data = json.loads(self._push_image())

        # Now add froggy as a shared image member
        path = "http://%s:%d/v1/images/%s/members/%s" % \
                ("0.0.0.0", self.api_port, data['image']['id'], 'froggy')

        response, _ = self._request(path, 'PUT',
                                    keystone_utils.pattieblack_token)
        self.assertEqual(response.status, 204)

        # Ensure pattieblack can still see the image
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        response, content = self._request(path, 'GET',
                                          keystone_utils.pattieblack_token)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 1)
        self.assertEqual(data['images'][0]['id'], 1)
        self.assertEqual(data['images'][0]['size'], FIVE_KB)
        self.assertEqual(data['images'][0]['name'], "Image1")

        # Ensure froggy can see the image now
        response, content = self._request(path, 'GET',
                                          keystone_utils.froggy_token)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 1)
        self.assertEqual(data['images'][0]['id'], 1)
        self.assertEqual(data['images'][0]['size'], FIVE_KB)
        self.assertEqual(data['images'][0]['name'], "Image1")

        # ensure that no one else can see the image
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        response, content = self._request(path, 'GET',
                                          keystone_utils.bacon_token)
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        self.stop_servers()

    @skip_if_disabled
    def test_share_and_replace_members(self):
        self.cleanup()
        self.start_servers()
        # First, we need to push an image up
        data = json.loads(self._push_image())

        image = data['image']
        # Now add froggy as a shared image member
        path = "http://%s:%d/v1/images/%s/members/%s" % \
                ("0.0.0.0", self.api_port, data['image']['id'], 'froggy')

        response, _ = self._request(path, 'PUT',
                                    keystone_utils.pattieblack_token)
        self.assertEqual(response.status, 204)

        # Ensure pattieblack can still see the image
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        response, content = self._request(path, 'GET',
                                          keystone_utils.pattieblack_token)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 1)
        self.assertEqual(data['images'][0]['id'], 1)
        self.assertEqual(data['images'][0]['size'], FIVE_KB)
        self.assertEqual(data['images'][0]['name'], "Image1")

        # Ensure froggy can see the image now
        response, content = self._request(path, 'GET',
                                          keystone_utils.froggy_token)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 1)
        self.assertEqual(data['images'][0]['id'], 1)
        self.assertEqual(data['images'][0]['size'], FIVE_KB)
        self.assertEqual(data['images'][0]['name'], "Image1")

        # ensure that no one else can see the image
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        response, content = self._request(path, 'GET',
                                          keystone_utils.bacon_token)
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # Replace froggy with bacon
        body = json.dumps({'memberships': [{'member_id': 'bacon',
                                            'can_share': False}]})
        path = "http://%s:%d/v1/images/%s/members" % \
                ("0.0.0.0", self.api_port, image['id'])

        response, content = self._request(path, 'PUT',
                                          keystone_utils.pattieblack_token,
                                          body=body)
        self.assertEqual(response.status, 204)

        # Ensure bacon can see the image
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        response, content = self._request(path, 'GET',
                                          keystone_utils.bacon_token)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 1)
        self.assertEqual(data['images'][0]['id'], 1)
        self.assertEqual(data['images'][0]['size'], FIVE_KB)
        self.assertEqual(data['images'][0]['name'], "Image1")

        # ensure that no one else can see the image
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        response, content = self._request(path, 'GET',
                                          keystone_utils.froggy_token)
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        self.stop_servers()

    @skip_if_disabled
    def test_unshare_image(self):
        self.cleanup()
        self.start_servers()
        # First, we need to push an image up
        data = json.loads(self._push_image())

        # Now add froggy as a shared image member
        path = "http://%s:%d/v1/images/%s/members/%s" % \
                ("0.0.0.0", self.api_port, data['image']['id'], 'froggy')

        response, _ = self._request(path, 'PUT',
                                    keystone_utils.pattieblack_token)
        self.assertEqual(response.status, 204)
        image = data['image']

        # Ensure pattieblack can still see the image
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        response, content = self._request(path, 'GET',
                                          keystone_utils.pattieblack_token)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 1)
        self.assertEqual(data['images'][0]['id'], 1)
        self.assertEqual(data['images'][0]['size'], FIVE_KB)
        self.assertEqual(data['images'][0]['name'], "Image1")

        # Ensure froggy can see the image now
        response, content = self._request(path, 'GET',
                                          keystone_utils.froggy_token)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 1)
        self.assertEqual(data['images'][0]['id'], 1)
        self.assertEqual(data['images'][0]['size'], FIVE_KB)
        self.assertEqual(data['images'][0]['name'], "Image1")

        # ensure that no one else can see the image
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        response, content = self._request(path, 'GET',
                                          keystone_utils.bacon_token)
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # Now remove froggy as a shared image member
        path = "http://%s:%d/v1/images/%s/members/%s" % \
                ("0.0.0.0", self.api_port, image['id'], 'froggy')

        response, content = self._request(path, 'DELETE',
                                    keystone_utils.pattieblack_token)
        self.assertEqual(response.status, 204)

        # ensure that no one else can see the image
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        response, content = self._request(path, 'GET',
                                          keystone_utils.froggy_token)
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # ensure that no one else can access the image
        path = "http://%s:%d/v1/images/%s" % ("0.0.0.0", self.api_port,
                                              image['id'])
        response, content = self._request(path, 'GET',
                                          keystone_utils.froggy_token)
        self.assertEqual(response.status, 404)

        # Ensure pattieblack can still see the image
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        response, content = self._request(path, 'GET',
                                          keystone_utils.pattieblack_token)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 1)
        self.assertEqual(data['images'][0]['id'], 1)
        self.assertEqual(data['images'][0]['size'], FIVE_KB)
        self.assertEqual(data['images'][0]['name'], "Image1")

        self.stop_servers()

    @skip_if_disabled
    def test_share_and_can_share_image(self):
        self.cleanup()
        self.start_servers()
        # First, we need to push an image up
        data = json.loads(self._push_image())

        # Now add froggy as a shared image member
        body = json.dumps({'member': {'can_share': True}})
        path = "http://%s:%d/v1/images/%s/members/%s" % \
                ("0.0.0.0", self.api_port, data['image']['id'], 'froggy')

        response, content = self._request(path, 'PUT',
                                    keystone_utils.pattieblack_token,
                                    body=body)
        self.assertEqual(response.status, 204)

        image = data['image']

        # Ensure froggy can see the image now
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        response, content = self._request(path, 'GET',
                                          keystone_utils.froggy_token)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 1)
        self.assertEqual(data['images'][0]['id'], 1)
        self.assertEqual(data['images'][0]['size'], FIVE_KB)
        self.assertEqual(data['images'][0]['name'], "Image1")

        # Froggy is going to share with bacon
        path = "http://%s:%d/v1/images/%s/members/%s" % \
                ("0.0.0.0", self.api_port, image['id'], 'bacon')

        response, _ = self._request(path, 'PUT',
                                    keystone_utils.froggy_token)
        self.assertEqual(response.status, 204)

        # Ensure bacon can see the image now
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        response, content = self._request(path, 'GET',
                                          keystone_utils.bacon_token)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['images']), 1)
        self.assertEqual(data['images'][0]['id'], 1)
        self.assertEqual(data['images'][0]['size'], FIVE_KB)
        self.assertEqual(data['images'][0]['name'], "Image1")

        # Ensure prosciutto cannot see the image
        response, content = self._request(path, 'GET',
                                          keystone_utils.prosciutto_token)
        self.assertEqual(response.status, 200)
        self.assertEqual(content, '{"images": []}')

        # Redundant, but prove prosciutto cannot share it
        path = "http://%s:%d/v1/images/%s/members/%s" % \
                ("0.0.0.0", self.api_port, image['id'], 'franknbeans')
        response, _ = self._request(path, 'PUT',
                                    keystone_utils.prosciutto_token)
        self.assertEqual(response.status, 404)

        self.stop_servers()

    @skip_if_disabled
    def test_get_members(self):
        self.cleanup()
        self.start_servers()
        # First, we need to push an image up
        data = json.loads(self._push_image())

        # Now add froggy as a shared image member
        path = "http://%s:%d/v1/images/%s/members/%s" % \
                ("0.0.0.0", self.api_port, data['image']['id'], 'froggy')

        response, content = self._request(path, 'PUT',
                                    keystone_utils.pattieblack_token)
        self.assertEqual(response.status, 204)

        path = "http://%s:%d/v1/images/%s/members" % \
                ("0.0.0.0", self.api_port, data['image']['id'])

        response, content = self._request(path, 'GET',
                                    keystone_utils.pattieblack_token)
        self.assertEqual(response.status, 200)
        body = json.loads(content)
        self.assertEqual(body['members'][0]['can_share'], False)
        self.assertEqual(body['members'][0]['member_id'], 'froggy')

        self.stop_servers()


class TestSharedImagesCli(keystone_utils.KeystoneTests):
    def _push_image(self, name=1):
        # First, we need to push an image up
        image_data = "*" * FIVE_KB
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': str(name)}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", self.api_port)
        response, content = self._request(path, 'POST',
                                          keystone_utils.pattieblack_token,
                                          headers=headers,
                                          body=image_data)
        self.assertEqual(response.status, 201)
        data = json.loads(content)
        self.assertEqual(data['image']['size'], FIVE_KB)
        self.assertEqual(data['image']['name'], str(name))
        self.assertEqual(data['image']['is_public'], False)
        self.assertEqual(data['image']['owner'], 'pattieblack')
        return content

    def _request(self, path, method, auth_token, headers=None, body=None):
        http = httplib2.Http()
        headers = headers or {}
        headers['X-Auth-Token'] = auth_token
        if body:
            return http.request(path, method, headers=headers,
                                body=body)
        else:
            return http.request(path, method, headers=headers)

    def _outsplit(self, out):
        return [l.strip() for l in out.strip().split('\n')]

    @skip_if_disabled
    def test_share_image(self):
        self.cleanup()
        self.start_servers()

        # Push an image up
        data = json.loads(self._push_image())

        image_id = data['image']['id']

        # Test that we can add froggy as a shared image member
        cmd = ("bin/glance --port=%d --auth_token=%s member-add %s %s" %
               (self.api_port, keystone_utils.pattieblack_token,
                image_id, 'froggy'))
        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)

        # Verify the membership of the image
        path = ("http://%s:%d/v1/images/%s/members" %
                ("0.0.0.0", self.api_port, image_id))
        response, content = self._request(path, 'GET',
                                          keystone_utils.pattieblack_token)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['members']), 1)
        self.assertEqual(data['members'][0]['member_id'], 'froggy')
        self.assertEqual(data['members'][0]['can_share'], False)

        # Test that we can replace a shared image membership list
        cmd = ("bin/glance --port=%d --auth_token=%s members-replace %s %s "
               "--can-share" %
               (self.api_port, keystone_utils.pattieblack_token,
                image_id, 'bacon'))
        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)

        # Verify the membership of the image
        path = ("http://%s:%d/v1/images/%s/members" %
                ("0.0.0.0", self.api_port, image_id))
        response, content = self._request(path, 'GET',
                                          keystone_utils.pattieblack_token)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['members']), 1)
        self.assertEqual(data['members'][0]['member_id'], 'bacon')
        self.assertEqual(data['members'][0]['can_share'], True)

        # Test that we can delete an image membership
        cmd = ("bin/glance --port=%d --auth_token=%s member-delete %s %s" %
               (self.api_port, keystone_utils.pattieblack_token,
                image_id, 'bacon'))
        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)

        # Verify the membership of the image
        path = ("http://%s:%d/v1/images/%s/members" %
                ("0.0.0.0", self.api_port, image_id))
        response, content = self._request(path, 'GET',
                                          keystone_utils.pattieblack_token)
        self.assertEqual(response.status, 200)
        data = json.loads(content)
        self.assertEqual(len(data['members']), 0)

        self.stop_servers()

    @skip_if_disabled
    def test_list_shares(self):
        self.cleanup()
        self.start_servers()

        # Push an image up
        data = json.loads(self._push_image(1))

        image1_id = data['image']['id']

        # Push a second image up
        data = json.loads(self._push_image(2))

        image2_id = data['image']['id']

        # Share images with froggy and bacon
        cmd = ("bin/glance --port=%d --auth_token=%s member-add %s %s" %
               (self.api_port, keystone_utils.pattieblack_token,
                image1_id, 'froggy'))
        exitcode, out, err = execute(cmd)
        self.assertEqual(0, exitcode)
        cmd = ("bin/glance --port=%d --auth_token=%s member-add %s %s" %
               (self.api_port, keystone_utils.pattieblack_token,
                image1_id, 'bacon'))
        exitcode, out, err = execute(cmd)
        self.assertEqual(0, exitcode)
        cmd = ("bin/glance --port=%d --auth_token=%s member-add %s %s "
               "--can-share" %
               (self.api_port, keystone_utils.pattieblack_token,
                image2_id, 'froggy'))
        exitcode, out, err = execute(cmd)
        self.assertEqual(0, exitcode)
        cmd = ("bin/glance --port=%d --auth_token=%s member-add %s %s "
               "--can-share" %
               (self.api_port, keystone_utils.pattieblack_token,
                image2_id, 'bacon'))
        exitcode, out, err = execute(cmd)
        self.assertEqual(0, exitcode)

        # Get the list of image members
        cmd = ("bin/glance --port=%d --auth_token=%s image-members %s" %
               (self.api_port, keystone_utils.pattieblack_token, image1_id))
        exitcode, out, err = execute(cmd)
        self.assertEqual(0, exitcode)

        result = self._outsplit(out)
        self.assertTrue('froggy' in result)
        self.assertTrue('bacon' in result)

        # Try again for can_share
        cmd = ("bin/glance --port=%d --auth_token=%s image-members %s" %
               (self.api_port, keystone_utils.pattieblack_token, image2_id))
        exitcode, out, err = execute(cmd)
        self.assertEqual(0, exitcode)

        result = self._outsplit(out)
        self.assertEqual(result[-1], '(*: Can share image)')
        self.assertTrue('froggy *' in result[:-2])
        self.assertTrue('bacon *' in result[:-2])

        # Get the list of member images
        cmd = ("bin/glance --port=%d --auth_token=%s member-images %s" %
               (self.api_port, keystone_utils.pattieblack_token, 'froggy'))
        exitcode, out, err = execute(cmd)
        self.assertEqual(0, exitcode)

        result = self._outsplit(out)
        self.assertEqual(result[-1], '(*: Can share image)')
        self.assertTrue(('%s' % image1_id) in result)
        self.assertTrue(('%s *' % image2_id) in result)

        self.stop_servers()
