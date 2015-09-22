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

import datetime
import hashlib
import os
import tempfile

from oslo_serialization import jsonutils
from oslo_utils import timeutils
from oslo_utils import units
import testtools

from glance.tests.integration.legacy_functional import base
from glance.tests.utils import minimal_headers

FIVE_KB = 5 * units.Ki
FIVE_GB = 5 * units.Gi


class TestApi(base.ApiTest):
    def test_get_head_simple_post(self):
        # 0. GET /images
        # Verify no public images
        path = "/v1/images"
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        self.assertEqual('{"images": []}', content)

        # 1. GET /images/detail
        # Verify no public images
        path = "/v1/images/detail"
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        self.assertEqual('{"images": []}', content)

        # 2. POST /images with public image named Image1
        # attribute and no custom properties. Verify a 200 OK is returned
        image_data = "*" * FIVE_KB
        headers = minimal_headers('Image1')
        path = "/v1/images"
        response, content = self.http.request(path, 'POST', headers=headers,
                                              body=image_data)
        self.assertEqual(201, response.status)
        data = jsonutils.loads(content)
        image_id = data['image']['id']
        self.assertEqual(hashlib.md5(image_data).hexdigest(),
                         data['image']['checksum'])
        self.assertEqual(FIVE_KB, data['image']['size'])
        self.assertEqual("Image1", data['image']['name'])
        self.assertTrue(data['image']['is_public'])

        # 3. HEAD image
        # Verify image found now
        path = "/v1/images/%s" % image_id
        response, content = self.http.request(path, 'HEAD')
        self.assertEqual(200, response.status)
        self.assertEqual("Image1", response['x-image-meta-name'])

        # 4. GET image
        # Verify all information on image we just added is correct
        path = "/v1/images/%s" % image_id
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)

        expected_image_headers = {
            'x-image-meta-id': image_id,
            'x-image-meta-name': 'Image1',
            'x-image-meta-is_public': 'True',
            'x-image-meta-status': 'active',
            'x-image-meta-disk_format': 'raw',
            'x-image-meta-container_format': 'ovf',
            'x-image-meta-size': str(FIVE_KB)}

        expected_std_headers = {
            'content-length': str(FIVE_KB),
            'content-type': 'application/octet-stream'}

        for expected_key, expected_value in expected_image_headers.items():
            self.assertEqual(expected_value, response[expected_key],
                             "For key '%s' expected header value '%s'. "
                             "Got '%s'" % (expected_key,
                                           expected_value,
                                           response[expected_key]))

        for expected_key, expected_value in expected_std_headers.items():
            self.assertEqual(expected_value, response[expected_key],
                             "For key '%s' expected header value '%s'. "
                             "Got '%s'" % (expected_key,
                                           expected_value,
                                           response[expected_key]))

        self.assertEqual("*" * FIVE_KB, content)
        self.assertEqual(hashlib.md5("*" * FIVE_KB).hexdigest(),
                         hashlib.md5(content).hexdigest())

        # 5. GET /images
        # Verify no public images
        path = "/v1/images"
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)

        expected_result = {"images": [
            {"container_format": "ovf",
             "disk_format": "raw",
             "id": image_id,
             "name": "Image1",
             "checksum": "c2e5db72bd7fd153f53ede5da5a06de3",
             "size": 5120}]}
        self.assertEqual(expected_result, jsonutils.loads(content))

        # 6. GET /images/detail
        # Verify image and all its metadata
        path = "/v1/images/detail"
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)

        expected_image = {
            "status": "active",
            "name": "Image1",
            "deleted": False,
            "container_format": "ovf",
            "disk_format": "raw",
            "id": image_id,
            "is_public": True,
            "deleted_at": None,
            "properties": {},
            "size": 5120}

        image = jsonutils.loads(content)

        for expected_key, expected_value in expected_image.items():
            self.assertEqual(expected_value, image['images'][0][expected_key],
                             "For key '%s' expected header value '%s'. "
                             "Got '%s'" % (expected_key,
                                           expected_value,
                                           image['images'][0][expected_key]))

        # 7. PUT image with custom properties of "distro" and "arch"
        # Verify 200 returned
        headers = {'X-Image-Meta-Property-Distro': 'Ubuntu',
                   'X-Image-Meta-Property-Arch': 'x86_64'}
        path = "/v1/images/%s" % image_id
        response, content = self.http.request(path, 'PUT', headers=headers)
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual("x86_64", data['image']['properties']['arch'])
        self.assertEqual("Ubuntu", data['image']['properties']['distro'])

        # 8. GET /images/detail
        # Verify image and all its metadata
        path = "/v1/images/detail"
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)

        expected_image = {
            "status": "active",
            "name": "Image1",
            "deleted": False,
            "container_format": "ovf",
            "disk_format": "raw",
            "id": image_id,
            "is_public": True,
            "deleted_at": None,
            "properties": {'distro': 'Ubuntu', 'arch': 'x86_64'},
            "size": 5120}

        image = jsonutils.loads(content)

        for expected_key, expected_value in expected_image.items():
            self.assertEqual(expected_value, image['images'][0][expected_key],
                             "For key '%s' expected header value '%s'. "
                             "Got '%s'" % (expected_key,
                                           expected_value,
                                           image['images'][0][expected_key]))

        # 9. PUT image and remove a previously existing property.
        headers = {'X-Image-Meta-Property-Arch': 'x86_64'}
        path = "/v1/images/%s" % image_id
        response, content = self.http.request(path, 'PUT', headers=headers)
        self.assertEqual(200, response.status)

        path = "/v1/images/detail"
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)['images'][0]
        self.assertEqual(1, len(data['properties']))
        self.assertEqual("x86_64", data['properties']['arch'])

        # 10. PUT image and add a previously deleted property.
        headers = {'X-Image-Meta-Property-Distro': 'Ubuntu',
                   'X-Image-Meta-Property-Arch': 'x86_64'}
        path = "/v1/images/%s" % image_id
        response, content = self.http.request(path, 'PUT', headers=headers)
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)

        path = "/v1/images/detail"
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)['images'][0]
        self.assertEqual(2, len(data['properties']))
        self.assertEqual("x86_64", data['properties']['arch'])
        self.assertEqual("Ubuntu", data['properties']['distro'])
        self.assertNotEqual(data['created_at'], data['updated_at'])

        # DELETE image
        path = "/v1/images/%s" % image_id
        response, content = self.http.request(path, 'DELETE')
        self.assertEqual(200, response.status)

    def test_queued_process_flow(self):
        """
        We test the process flow where a user registers an image
        with Glance but does not immediately upload an image file.
        Later, the user uploads an image file using a PUT operation.
        We track the changing of image status throughout this process.

        0. GET /images
        - Verify no public images
        1. POST /images with public image named Image1 with no location
           attribute and no image data.
        - Verify 201 returned
        2. GET /images
        - Verify one public image
        3. HEAD image
        - Verify image now in queued status
        4. PUT image with image data
        - Verify 200 returned
        5. HEAD images
        - Verify image now in active status
        6. GET /images
        - Verify one public image
        """

        # 0. GET /images
        # Verify no public images
        path = "/v1/images"
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        self.assertEqual('{"images": []}', content)

        # 1. POST /images with public image named Image1
        # with no location or image data
        headers = minimal_headers('Image1')
        path = "/v1/images"
        response, content = self.http.request(path, 'POST', headers=headers)
        self.assertEqual(201, response.status)
        data = jsonutils.loads(content)
        self.assertIsNone(data['image']['checksum'])
        self.assertEqual(0, data['image']['size'])
        self.assertEqual('ovf', data['image']['container_format'])
        self.assertEqual('raw', data['image']['disk_format'])
        self.assertEqual("Image1", data['image']['name'])
        self.assertTrue(data['image']['is_public'])

        image_id = data['image']['id']

        # 2. GET /images
        # Verify 1 public image
        path = "/v1/images"
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(image_id, data['images'][0]['id'])
        self.assertIsNone(data['images'][0]['checksum'])
        self.assertEqual(0, data['images'][0]['size'])
        self.assertEqual('ovf', data['images'][0]['container_format'])
        self.assertEqual('raw', data['images'][0]['disk_format'])
        self.assertEqual("Image1", data['images'][0]['name'])

        # 3. HEAD /images
        # Verify status is in queued
        path = "/v1/images/%s" % (image_id)
        response, content = self.http.request(path, 'HEAD')
        self.assertEqual(200, response.status)
        self.assertEqual("Image1", response['x-image-meta-name'])
        self.assertEqual("queued", response['x-image-meta-status'])
        self.assertEqual('0', response['x-image-meta-size'])
        self.assertEqual(image_id, response['x-image-meta-id'])

        # 4. PUT image with image data, verify 200 returned
        image_data = "*" * FIVE_KB
        headers = {'Content-Type': 'application/octet-stream'}
        path = "/v1/images/%s" % (image_id)
        response, content = self.http.request(path, 'PUT', headers=headers,
                                              body=image_data)
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(hashlib.md5(image_data).hexdigest(),
                         data['image']['checksum'])
        self.assertEqual(FIVE_KB, data['image']['size'])
        self.assertEqual("Image1", data['image']['name'])
        self.assertTrue(data['image']['is_public'])

        # 5. HEAD /images
        # Verify status is in active
        path = "/v1/images/%s" % (image_id)
        response, content = self.http.request(path, 'HEAD')
        self.assertEqual(200, response.status)
        self.assertEqual("Image1", response['x-image-meta-name'])
        self.assertEqual("active", response['x-image-meta-status'])

        # 6. GET /images
        # Verify 1 public image still...
        path = "/v1/images"
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(hashlib.md5(image_data).hexdigest(),
                         data['images'][0]['checksum'])
        self.assertEqual(image_id, data['images'][0]['id'])
        self.assertEqual(FIVE_KB, data['images'][0]['size'])
        self.assertEqual('ovf', data['images'][0]['container_format'])
        self.assertEqual('raw', data['images'][0]['disk_format'])
        self.assertEqual("Image1", data['images'][0]['name'])

        # DELETE image
        path = "/v1/images/%s" % (image_id)
        response, content = self.http.request(path, 'DELETE')
        self.assertEqual(200, response.status)

    def test_v1_not_enabled(self):
        self.config(enable_v1_api=False)
        path = "/v1/images"
        response, content = self.http.request(path, 'GET')
        self.assertEqual(300, response.status)

    def test_v1_enabled(self):
        self.config(enable_v1_api=True)
        path = "/v1/images"
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)

    def test_zero_initial_size(self):
        """
        A test to ensure that an image with size explicitly set to zero
        has status that immediately transitions to active.
        """
        # 1. POST /images with public image named Image1
        # attribute and a size of zero.
        # Verify a 201 OK is returned
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Size': '0',
                   'X-Image-Meta-Name': 'Image1',
                   'X-Image-Meta-disk_format': 'raw',
                   'X-image-Meta-container_format': 'ovf',
                   'X-Image-Meta-Is-Public': 'True'}
        path = "/v1/images"
        response, content = self.http.request(path, 'POST', headers=headers)
        self.assertEqual(201, response.status)
        image = jsonutils.loads(content)['image']
        self.assertEqual('active', image['status'])

        # 2. HEAD image-location
        # Verify image size is zero and the status is active
        path = response.get('location')
        response, content = self.http.request(path, 'HEAD')
        self.assertEqual(200, response.status)
        self.assertEqual('0', response['x-image-meta-size'])
        self.assertEqual('active', response['x-image-meta-status'])

        # 3. GET  image-location
        # Verify image content is empty
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        self.assertEqual(0, len(content))

    def test_traceback_not_consumed(self):
        """
        A test that errors coming from the POST API do not
        get consumed and print the actual error message, and
        not something like &lt;traceback object at 0x1918d40&gt;

        :see https://bugs.launchpad.net/glance/+bug/755912
        """
        # POST /images with binary data, but not setting
        # Content-Type to application/octet-stream, verify a
        # 400 returned and that the error is readable.
        with tempfile.NamedTemporaryFile() as test_data_file:
            test_data_file.write("XXX")
            test_data_file.flush()
        path = "/v1/images"
        headers = minimal_headers('Image1')
        headers['Content-Type'] = 'not octet-stream'
        response, content = self.http.request(path, 'POST',
                                              body=test_data_file.name,
                                              headers=headers)
        self.assertEqual(400, response.status)
        expected = "Content-Type must be application/octet-stream"
        self.assertIn(expected, content,
                      "Could not find '%s' in '%s'" % (expected, content))

    def test_filtered_images(self):
        """
        Set up four test images and ensure each query param filter works
        """

        # 0. GET /images
        # Verify no public images
        path = "/v1/images"
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        self.assertEqual('{"images": []}', content)

        image_ids = []

        # 1. POST /images with three public images, and one private image
        # with various attributes
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'Image1',
                   'X-Image-Meta-Status': 'active',
                   'X-Image-Meta-Container-Format': 'ovf',
                   'X-Image-Meta-Disk-Format': 'vdi',
                   'X-Image-Meta-Size': '19',
                   'X-Image-Meta-Is-Public': 'True',
                   'X-Image-Meta-Protected': 'True',
                   'X-Image-Meta-Property-pants': 'are on'}
        path = "/v1/images"
        response, content = self.http.request(path, 'POST', headers=headers)
        self.assertEqual(201, response.status)
        data = jsonutils.loads(content)
        self.assertEqual("are on", data['image']['properties']['pants'])
        self.assertTrue(data['image']['is_public'])
        image_ids.append(data['image']['id'])

        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'My Image!',
                   'X-Image-Meta-Status': 'active',
                   'X-Image-Meta-Container-Format': 'ovf',
                   'X-Image-Meta-Disk-Format': 'vhd',
                   'X-Image-Meta-Size': '20',
                   'X-Image-Meta-Is-Public': 'True',
                   'X-Image-Meta-Protected': 'False',
                   'X-Image-Meta-Property-pants': 'are on'}
        path = "/v1/images"
        response, content = self.http.request(path, 'POST', headers=headers)
        self.assertEqual(201, response.status)
        data = jsonutils.loads(content)
        self.assertEqual("are on", data['image']['properties']['pants'])
        self.assertTrue(data['image']['is_public'])
        image_ids.append(data['image']['id'])

        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'My Image!',
                   'X-Image-Meta-Status': 'saving',
                   'X-Image-Meta-Container-Format': 'ami',
                   'X-Image-Meta-Disk-Format': 'ami',
                   'X-Image-Meta-Size': '21',
                   'X-Image-Meta-Is-Public': 'True',
                   'X-Image-Meta-Protected': 'False',
                   'X-Image-Meta-Property-pants': 'are off'}
        path = "/v1/images"
        response, content = self.http.request(path, 'POST', headers=headers)
        self.assertEqual(201, response.status)
        data = jsonutils.loads(content)
        self.assertEqual("are off", data['image']['properties']['pants'])
        self.assertTrue(data['image']['is_public'])
        image_ids.append(data['image']['id'])

        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'My Private Image',
                   'X-Image-Meta-Status': 'active',
                   'X-Image-Meta-Container-Format': 'ami',
                   'X-Image-Meta-Disk-Format': 'ami',
                   'X-Image-Meta-Size': '22',
                   'X-Image-Meta-Is-Public': 'False',
                   'X-Image-Meta-Protected': 'False'}
        path = "/v1/images"
        response, content = self.http.request(path, 'POST', headers=headers)
        self.assertEqual(201, response.status)
        data = jsonutils.loads(content)
        self.assertFalse(data['image']['is_public'])
        image_ids.append(data['image']['id'])

        # 2. GET /images
        # Verify three public images
        path = "/v1/images"
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(3, len(data['images']))

        # 3. GET /images with name filter
        # Verify correct images returned with name
        params = "name=My%20Image!"
        path = "/v1/images?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(2, len(data['images']))
        for image in data['images']:
            self.assertEqual("My Image!", image['name'])

        # 4. GET /images with status filter
        # Verify correct images returned with status
        params = "status=queued"
        path = "/v1/images/detail?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(3, len(data['images']))
        for image in data['images']:
            self.assertEqual("queued", image['status'])

        params = "status=active"
        path = "/v1/images/detail?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(0, len(data['images']))

        # 5. GET /images with container_format filter
        # Verify correct images returned with container_format
        params = "container_format=ovf"
        path = "/v1/images?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(2, len(data['images']))
        for image in data['images']:
            self.assertEqual("ovf", image['container_format'])

        # 6. GET /images with disk_format filter
        # Verify correct images returned with disk_format
        params = "disk_format=vdi"
        path = "/v1/images?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(1, len(data['images']))
        for image in data['images']:
            self.assertEqual("vdi", image['disk_format'])

        # 7. GET /images with size_max filter
        # Verify correct images returned with size <= expected
        params = "size_max=20"
        path = "/v1/images?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(2, len(data['images']))
        for image in data['images']:
            self.assertTrue(image['size'] <= 20)

        # 8. GET /images with size_min filter
        # Verify correct images returned with size >= expected
        params = "size_min=20"
        path = "/v1/images?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(2, len(data['images']))
        for image in data['images']:
            self.assertTrue(image['size'] >= 20)

        # 9. Get /images with is_public=None filter
        # Verify correct images returned with property
        # Bug lp:803656  Support is_public in filtering
        params = "is_public=None"
        path = "/v1/images?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(4, len(data['images']))

        # 10. Get /images with is_public=False filter
        # Verify correct images returned with property
        # Bug lp:803656  Support is_public in filtering
        params = "is_public=False"
        path = "/v1/images?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(1, len(data['images']))
        for image in data['images']:
            self.assertEqual("My Private Image", image['name'])

        # 11. Get /images with is_public=True filter
        # Verify correct images returned with property
        # Bug lp:803656  Support is_public in filtering
        params = "is_public=True"
        path = "/v1/images?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(3, len(data['images']))
        for image in data['images']:
            self.assertNotEqual(image['name'], "My Private Image")

        # 12. Get /images with protected=False filter
        # Verify correct images returned with property
        params = "protected=False"
        path = "/v1/images?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(2, len(data['images']))
        for image in data['images']:
            self.assertNotEqual(image['name'], "Image1")

        # 13. Get /images with protected=True filter
        # Verify correct images returned with property
        params = "protected=True"
        path = "/v1/images?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(1, len(data['images']))
        for image in data['images']:
            self.assertEqual("Image1", image['name'])

        # 14. GET /images with property filter
        # Verify correct images returned with property
        params = "property-pants=are%20on"
        path = "/v1/images/detail?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(2, len(data['images']))
        for image in data['images']:
            self.assertEqual("are on", image['properties']['pants'])

        # 15. GET /images with property filter and name filter
        # Verify correct images returned with property and name
        # Make sure you quote the url when using more than one param!
        params = "name=My%20Image!&property-pants=are%20on"
        path = "/v1/images/detail?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(1, len(data['images']))
        for image in data['images']:
            self.assertEqual("are on", image['properties']['pants'])
            self.assertEqual("My Image!", image['name'])

        # 16. GET /images with past changes-since filter
        yesterday = timeutils.isotime(timeutils.utcnow() -
                                      datetime.timedelta(1))
        params = "changes-since=%s" % yesterday
        path = "/v1/images?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(3, len(data['images']))

        # one timezone west of Greenwich equates to an hour ago
        # taking care to pre-urlencode '+' as '%2B', otherwise the timezone
        # '+' is wrongly decoded as a space
        # TODO(eglynn): investigate '+' --> <SPACE> decoding, an artifact
        # of WSGI/webob dispatch?
        now = timeutils.utcnow()
        hour_ago = now.strftime('%Y-%m-%dT%H:%M:%S%%2B01:00')
        params = "changes-since=%s" % hour_ago
        path = "/v1/images?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(3, len(data['images']))

        # 17. GET /images with future changes-since filter
        tomorrow = timeutils.isotime(timeutils.utcnow() +
                                     datetime.timedelta(1))
        params = "changes-since=%s" % tomorrow
        path = "/v1/images?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(0, len(data['images']))

        # one timezone east of Greenwich equates to an hour from now
        now = timeutils.utcnow()
        hour_hence = now.strftime('%Y-%m-%dT%H:%M:%S-01:00')
        params = "changes-since=%s" % hour_hence
        path = "/v1/images?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(0, len(data['images']))

        # 18. GET /images with size_min filter
        # Verify correct images returned with size >= expected
        params = "size_min=-1"
        path = "/v1/images?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(400, response.status)
        self.assertIn("filter size_min got -1", content)

        # 19. GET /images with size_min filter
        # Verify correct images returned with size >= expected
        params = "size_max=-1"
        path = "/v1/images?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(400, response.status)
        self.assertIn("filter size_max got -1", content)

        # 20. GET /images with size_min filter
        # Verify correct images returned with size >= expected
        params = "min_ram=-1"
        path = "/v1/images?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(400, response.status)
        self.assertIn("Bad value passed to filter min_ram got -1", content)

        # 21. GET /images with size_min filter
        # Verify correct images returned with size >= expected
        params = "protected=imalittleteapot"
        path = "/v1/images?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(400, response.status)
        self.assertIn("protected got imalittleteapot", content)

        # 22. GET /images with size_min filter
        # Verify correct images returned with size >= expected
        params = "is_public=imalittleteapot"
        path = "/v1/images?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(400, response.status)
        self.assertIn("is_public got imalittleteapot", content)

    def test_limited_images(self):
        """
        Ensure marker and limit query params work
        """

        # 0. GET /images
        # Verify no public images
        path = "/v1/images"
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        self.assertEqual('{"images": []}', content)

        image_ids = []

        # 1. POST /images with three public images with various attributes
        headers = minimal_headers('Image1')
        path = "/v1/images"
        response, content = self.http.request(path, 'POST', headers=headers)
        self.assertEqual(201, response.status)
        image_ids.append(jsonutils.loads(content)['image']['id'])

        headers = minimal_headers('Image2')
        path = "/v1/images"
        response, content = self.http.request(path, 'POST', headers=headers)
        self.assertEqual(201, response.status)
        image_ids.append(jsonutils.loads(content)['image']['id'])

        headers = minimal_headers('Image3')
        path = "/v1/images"
        response, content = self.http.request(path, 'POST', headers=headers)
        self.assertEqual(201, response.status)
        image_ids.append(jsonutils.loads(content)['image']['id'])

        # 2. GET /images with all images
        path = "/v1/images"
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        images = jsonutils.loads(content)['images']
        self.assertEqual(3, len(images))

        # 3. GET /images with limit of 2
        # Verify only two images were returned
        params = "limit=2"
        path = "/v1/images?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)['images']
        self.assertEqual(2, len(data))
        self.assertEqual(images[0]['id'], data[0]['id'])
        self.assertEqual(images[1]['id'], data[1]['id'])

        # 4. GET /images with marker
        # Verify only two images were returned
        params = "marker=%s" % images[0]['id']
        path = "/v1/images?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)['images']
        self.assertEqual(2, len(data))
        self.assertEqual(images[1]['id'], data[0]['id'])
        self.assertEqual(images[2]['id'], data[1]['id'])

        # 5. GET /images with marker and limit
        # Verify only one image was returned with the correct id
        params = "limit=1&marker=%s" % images[1]['id']
        path = "/v1/images?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)['images']
        self.assertEqual(1, len(data))
        self.assertEqual(images[2]['id'], data[0]['id'])

        # 6. GET /images/detail with marker and limit
        # Verify only one image was returned with the correct id
        params = "limit=1&marker=%s" % images[1]['id']
        path = "/v1/images?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)['images']
        self.assertEqual(1, len(data))
        self.assertEqual(images[2]['id'], data[0]['id'])

        # DELETE images
        for image_id in image_ids:
            path = "/v1/images/%s" % (image_id)
            response, content = self.http.request(path, 'DELETE')
            self.assertEqual(200, response.status)

    def test_ordered_images(self):
        """
        Set up three test images and ensure each query param filter works
        """
        # 0. GET /images
        # Verify no public images
        path = "/v1/images"
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        self.assertEqual('{"images": []}', content)

        # 1. POST /images with three public images with various attributes
        image_ids = []
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'Image1',
                   'X-Image-Meta-Status': 'active',
                   'X-Image-Meta-Container-Format': 'ovf',
                   'X-Image-Meta-Disk-Format': 'vdi',
                   'X-Image-Meta-Size': '19',
                   'X-Image-Meta-Is-Public': 'True'}
        path = "/v1/images"
        response, content = self.http.request(path, 'POST', headers=headers)
        self.assertEqual(201, response.status)
        image_ids.append(jsonutils.loads(content)['image']['id'])

        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'ASDF',
                   'X-Image-Meta-Status': 'active',
                   'X-Image-Meta-Container-Format': 'bare',
                   'X-Image-Meta-Disk-Format': 'iso',
                   'X-Image-Meta-Size': '2',
                   'X-Image-Meta-Is-Public': 'True'}
        path = "/v1/images"
        response, content = self.http.request(path, 'POST', headers=headers)
        self.assertEqual(201, response.status)
        image_ids.append(jsonutils.loads(content)['image']['id'])

        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'XYZ',
                   'X-Image-Meta-Status': 'saving',
                   'X-Image-Meta-Container-Format': 'ami',
                   'X-Image-Meta-Disk-Format': 'ami',
                   'X-Image-Meta-Size': '5',
                   'X-Image-Meta-Is-Public': 'True'}
        path = "/v1/images"
        response, content = self.http.request(path, 'POST', headers=headers)
        self.assertEqual(201, response.status)
        image_ids.append(jsonutils.loads(content)['image']['id'])

        # 2. GET /images with no query params
        # Verify three public images sorted by created_at desc
        path = "/v1/images"
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(3, len(data['images']))
        self.assertEqual(image_ids[2], data['images'][0]['id'])
        self.assertEqual(image_ids[1], data['images'][1]['id'])
        self.assertEqual(image_ids[0], data['images'][2]['id'])

        # 3. GET /images sorted by name asc
        params = 'sort_key=name&sort_dir=asc'
        path = "/v1/images?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(3, len(data['images']))
        self.assertEqual(image_ids[1], data['images'][0]['id'])
        self.assertEqual(image_ids[0], data['images'][1]['id'])
        self.assertEqual(image_ids[2], data['images'][2]['id'])

        # 4. GET /images sorted by size desc
        params = 'sort_key=size&sort_dir=desc'
        path = "/v1/images?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(3, len(data['images']))
        self.assertEqual(image_ids[0], data['images'][0]['id'])
        self.assertEqual(image_ids[2], data['images'][1]['id'])
        self.assertEqual(image_ids[1], data['images'][2]['id'])

        # 5. GET /images sorted by size desc with a marker
        params = 'sort_key=size&sort_dir=desc&marker=%s' % image_ids[0]
        path = "/v1/images?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(2, len(data['images']))
        self.assertEqual(image_ids[2], data['images'][0]['id'])
        self.assertEqual(image_ids[1], data['images'][1]['id'])

        # 6. GET /images sorted by name asc with a marker
        params = 'sort_key=name&sort_dir=asc&marker=%s' % image_ids[2]
        path = "/v1/images?%s" % (params)
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        data = jsonutils.loads(content)
        self.assertEqual(0, len(data['images']))

        # DELETE images
        for image_id in image_ids:
            path = "/v1/images/%s" % (image_id)
            response, content = self.http.request(path, 'DELETE')
            self.assertEqual(200, response.status)

    def test_duplicate_image_upload(self):
        """
        Upload initial image, then attempt to upload duplicate image
        """
        # 0. GET /images
        # Verify no public images
        path = "/v1/images"
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        self.assertEqual('{"images": []}', content)

        # 1. POST /images with public image named Image1
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'Image1',
                   'X-Image-Meta-Status': 'active',
                   'X-Image-Meta-Container-Format': 'ovf',
                   'X-Image-Meta-Disk-Format': 'vdi',
                   'X-Image-Meta-Size': '19',
                   'X-Image-Meta-Is-Public': 'True'}
        path = "/v1/images"
        response, content = self.http.request(path, 'POST', headers=headers)
        self.assertEqual(201, response.status)

        image = jsonutils.loads(content)['image']

        # 2. POST /images with public image named Image1, and ID: 1
        headers = {'Content-Type': 'application/octet-stream',
                   'X-Image-Meta-Name': 'Image1 Update',
                   'X-Image-Meta-Status': 'active',
                   'X-Image-Meta-Container-Format': 'ovf',
                   'X-Image-Meta-Disk-Format': 'vdi',
                   'X-Image-Meta-Size': '19',
                   'X-Image-Meta-Id': image['id'],
                   'X-Image-Meta-Is-Public': 'True'}
        path = "/v1/images"
        response, content = self.http.request(path, 'POST', headers=headers)
        self.assertEqual(409, response.status)

    def test_delete_not_existing(self):
        """
        We test the following:

        0. GET /images/1
        - Verify 404
        1. DELETE /images/1
        - Verify 404
        """

        # 0. GET /images
        # Verify no public images
        path = "/v1/images"
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        self.assertEqual('{"images": []}', content)

        # 1. DELETE /images/1
        # Verify 404 returned
        path = "/v1/images/1"
        response, content = self.http.request(path, 'DELETE')
        self.assertEqual(404, response.status)

    def _do_test_post_image_content_bad_format(self, format):
        """
        We test that missing container/disk format fails with 400 "Bad Request"

        :see https://bugs.launchpad.net/glance/+bug/933702
        """

        # Verify no public images
        path = "/v1/images"
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        images = jsonutils.loads(content)['images']
        self.assertEqual(0, len(images))

        path = "/v1/images"

        # POST /images without given format being specified
        headers = minimal_headers('Image1')
        headers['X-Image-Meta-' + format] = 'bad_value'
        with tempfile.NamedTemporaryFile() as test_data_file:
            test_data_file.write("XXX")
            test_data_file.flush()
        response, content = self.http.request(path, 'POST',
                                              headers=headers,
                                              body=test_data_file.name)
        self.assertEqual(400, response.status)
        type = format.replace('_format', '')
        expected = "Invalid %s format 'bad_value' for image" % type
        self.assertIn(expected, content,
                      "Could not find '%s' in '%s'" % (expected, content))

        # make sure the image was not created
        # Verify no public images
        path = "/v1/images"
        response, content = self.http.request(path, 'GET')
        self.assertEqual(200, response.status)
        images = jsonutils.loads(content)['images']
        self.assertEqual(0, len(images))

    def test_post_image_content_bad_container_format(self):
        self._do_test_post_image_content_bad_format('container_format')

    def test_post_image_content_bad_disk_format(self):
        self._do_test_post_image_content_bad_format('disk_format')

    def _do_test_put_image_content_missing_format(self, format):
        """
        We test that missing container/disk format only fails with
        400 "Bad Request" when the image content is PUT (i.e. not
        on the original POST of a queued image).

        :see https://bugs.launchpad.net/glance/+bug/937216
        """

        # POST queued image
        path = "/v1/images"
        headers = {
            'X-Image-Meta-Name': 'Image1',
            'X-Image-Meta-Is-Public': 'True',
        }
        response, content = self.http.request(path, 'POST', headers=headers)
        self.assertEqual(201, response.status)
        data = jsonutils.loads(content)
        image_id = data['image']['id']
        self.addDetail('image_data', testtools.content.json_content(data))

        # PUT image content images without given format being specified
        path = "/v1/images/%s" % (image_id)
        headers = minimal_headers('Image1')
        del headers['X-Image-Meta-' + format]
        with tempfile.NamedTemporaryFile() as test_data_file:
            test_data_file.write("XXX")
            test_data_file.flush()
        response, content = self.http.request(path, 'PUT',
                                              headers=headers,
                                              body=test_data_file.name)
        self.assertEqual(400, response.status)
        type = format.replace('_format', '').capitalize()
        expected = "%s format is not specified" % type
        self.assertIn(expected, content,
                      "Could not find '%s' in '%s'" % (expected, content))

    def test_put_image_content_bad_container_format(self):
        self._do_test_put_image_content_missing_format('container_format')

    def test_put_image_content_bad_disk_format(self):
        self._do_test_put_image_content_missing_format('disk_format')

    def _do_test_mismatched_attribute(self, attribute, value):
        """
        Test mismatched attribute.
        """

        image_data = "*" * FIVE_KB
        headers = minimal_headers('Image1')
        headers[attribute] = value
        path = "/v1/images"
        response, content = self.http.request(path, 'POST', headers=headers,
                                              body=image_data)
        self.assertEqual(400, response.status)

        images_dir = os.path.join(self.test_dir, 'images')
        image_count = len([name for name in os.listdir(images_dir)
                           if os.path.isfile(os.path.join(images_dir, name))])
        self.assertEqual(0, image_count)

    def test_mismatched_size(self):
        """
        Test mismatched size.
        """
        self._do_test_mismatched_attribute('x-image-meta-size',
                                           str(FIVE_KB + 1))

    def test_mismatched_checksum(self):
        """
        Test mismatched checksum.
        """
        self._do_test_mismatched_attribute('x-image-meta-checksum',
                                           'foobar')


class TestApiWithFakeAuth(base.ApiTest):
    def __init__(self, *args, **kwargs):
        super(TestApiWithFakeAuth, self).__init__(*args, **kwargs)
        self.api_flavor = 'fakeauth'
        self.registry_flavor = 'fakeauth'

    def test_ownership(self):
        # Add an image with admin privileges and ensure the owner
        # can be set to something other than what was used to authenticate
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:admin',
        }

        create_headers = {
            'X-Image-Meta-Name': 'MyImage',
            'X-Image-Meta-disk_format': 'raw',
            'X-Image-Meta-container_format': 'ovf',
            'X-Image-Meta-Is-Public': 'True',
            'X-Image-Meta-Owner': 'tenant2',
        }
        create_headers.update(auth_headers)

        path = "/v1/images"
        response, content = self.http.request(path, 'POST',
                                              headers=create_headers)
        self.assertEqual(201, response.status)
        data = jsonutils.loads(content)
        image_id = data['image']['id']

        path = "/v1/images/%s" % (image_id)
        response, content = self.http.request(path, 'HEAD',
                                              headers=auth_headers)
        self.assertEqual(200, response.status)
        self.assertEqual('tenant2', response['x-image-meta-owner'])

        # Now add an image without admin privileges and ensure the owner
        # cannot be set to something other than what was used to authenticate
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:role1',
        }
        create_headers.update(auth_headers)

        path = "/v1/images"
        response, content = self.http.request(path, 'POST',
                                              headers=create_headers)
        self.assertEqual(201, response.status)
        data = jsonutils.loads(content)
        image_id = data['image']['id']

        # We have to be admin to see the owner
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:admin',
        }
        create_headers.update(auth_headers)

        path = "/v1/images/%s" % (image_id)
        response, content = self.http.request(path, 'HEAD',
                                              headers=auth_headers)
        self.assertEqual(200, response.status)
        self.assertEqual('tenant1', response['x-image-meta-owner'])

        # Make sure the non-privileged user can't update their owner either
        update_headers = {
            'X-Image-Meta-Name': 'MyImage2',
            'X-Image-Meta-Owner': 'tenant2',
            'X-Auth-Token': 'user1:tenant1:role1',
        }

        path = "/v1/images/%s" % (image_id)
        response, content = self.http.request(path, 'PUT',
                                              headers=update_headers)
        self.assertEqual(200, response.status)

        # We have to be admin to see the owner
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:admin',
        }

        path = "/v1/images/%s" % (image_id)
        response, content = self.http.request(path, 'HEAD',
                                              headers=auth_headers)
        self.assertEqual(200, response.status)
        self.assertEqual('tenant1', response['x-image-meta-owner'])

        # An admin user should be able to update the owner
        auth_headers = {
            'X-Auth-Token': 'user1:tenant3:admin',
        }

        update_headers = {
            'X-Image-Meta-Name': 'MyImage2',
            'X-Image-Meta-Owner': 'tenant2',
        }
        update_headers.update(auth_headers)

        path = "/v1/images/%s" % (image_id)
        response, content = self.http.request(path, 'PUT',
                                              headers=update_headers)
        self.assertEqual(200, response.status)

        path = "/v1/images/%s" % (image_id)
        response, content = self.http.request(path, 'HEAD',
                                              headers=auth_headers)
        self.assertEqual(200, response.status)
        self.assertEqual('tenant2', response['x-image-meta-owner'])

    def test_image_visibility_to_different_users(self):
        owners = ['admin', 'tenant1', 'tenant2', 'none']
        visibilities = {'public': 'True', 'private': 'False'}
        image_ids = {}

        for owner in owners:
            for visibility, is_public in visibilities.items():
                name = '%s-%s' % (owner, visibility)
                headers = {
                    'Content-Type': 'application/octet-stream',
                    'X-Image-Meta-Name': name,
                    'X-Image-Meta-Status': 'active',
                    'X-Image-Meta-Is-Public': is_public,
                    'X-Image-Meta-Owner': owner,
                    'X-Auth-Token': 'createuser:createtenant:admin',
                }
                path = "/v1/images"
                response, content = self.http.request(path, 'POST',
                                                      headers=headers)
                self.assertEqual(201, response.status)
                data = jsonutils.loads(content)
                image_ids[name] = data['image']['id']

        def list_images(tenant, role='', is_public=None):
            auth_token = 'user:%s:%s' % (tenant, role)
            headers = {'X-Auth-Token': auth_token}
            path = "/v1/images/detail"
            if is_public is not None:
                path += '?is_public=%s' % is_public
            response, content = self.http.request(path, 'GET', headers=headers)
            self.assertEqual(200, response.status)
            return jsonutils.loads(content)['images']

        # 1. Known user sees public and their own images
        images = list_images('tenant1')
        self.assertEqual(5, len(images))
        for image in images:
            self.assertTrue(image['is_public'] or image['owner'] == 'tenant1')

        # 2. Unknown user sees only public images
        images = list_images('none')
        self.assertEqual(4, len(images))
        for image in images:
            self.assertTrue(image['is_public'])

        # 3. Unknown admin sees only public images
        images = list_images('none', role='admin')
        self.assertEqual(4, len(images))
        for image in images:
            self.assertTrue(image['is_public'])

        # 4. Unknown admin, is_public=none, shows all images
        images = list_images('none', role='admin', is_public='none')
        self.assertEqual(8, len(images))

        # 5. Unknown admin, is_public=true, shows only public images
        images = list_images('none', role='admin', is_public='true')
        self.assertEqual(4, len(images))
        for image in images:
            self.assertTrue(image['is_public'])

        # 6. Unknown admin, is_public=false, sees only private images
        images = list_images('none', role='admin', is_public='false')
        self.assertEqual(4, len(images))
        for image in images:
            self.assertFalse(image['is_public'])

        # 7. Known admin sees public and their own images
        images = list_images('admin', role='admin')
        self.assertEqual(5, len(images))
        for image in images:
            self.assertTrue(image['is_public'] or image['owner'] == 'admin')

        # 8. Known admin, is_public=none, shows all images
        images = list_images('admin', role='admin', is_public='none')
        self.assertEqual(8, len(images))

        # 9. Known admin, is_public=true, sees all public and their images
        images = list_images('admin', role='admin', is_public='true')
        self.assertEqual(5, len(images))
        for image in images:
            self.assertTrue(image['is_public'] or image['owner'] == 'admin')

        # 10. Known admin, is_public=false, sees all private images
        images = list_images('admin', role='admin', is_public='false')
        self.assertEqual(4, len(images))
        for image in images:
            self.assertFalse(image['is_public'])

    def test_property_protections(self):
        # Enable property protection
        self.config(property_protection_file=self.property_file)
        self.init()

        CREATE_HEADERS = {
            'X-Image-Meta-Name': 'MyImage',
            'X-Image-Meta-disk_format': 'raw',
            'X-Image-Meta-container_format': 'ovf',
            'X-Image-Meta-Is-Public': 'True',
            'X-Image-Meta-Owner': 'tenant2',
        }

        # Create an image for role member with extra properties
        # Raises 403 since user is not allowed to create 'foo'
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:member',
        }
        custom_props = {
            'x-image-meta-property-foo': 'bar'
        }
        auth_headers.update(custom_props)
        auth_headers.update(CREATE_HEADERS)
        path = "/v1/images"
        response, content = self.http.request(path, 'POST',
                                              headers=auth_headers)
        self.assertEqual(403, response.status)

        # Create an image for role member without 'foo'
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:member',
        }
        custom_props = {
            'x-image-meta-property-x_owner_foo': 'o_s_bar',
        }
        auth_headers.update(custom_props)
        auth_headers.update(CREATE_HEADERS)
        path = "/v1/images"
        response, content = self.http.request(path, 'POST',
                                              headers=auth_headers)
        self.assertEqual(201, response.status)

        # Returned image entity should have 'x_owner_foo'
        data = jsonutils.loads(content)
        self.assertEqual('o_s_bar',
                         data['image']['properties']['x_owner_foo'])

        # Create an image for role spl_role with extra properties
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:spl_role',
        }
        custom_props = {
            'X-Image-Meta-Property-spl_create_prop': 'create_bar',
            'X-Image-Meta-Property-spl_read_prop': 'read_bar',
            'X-Image-Meta-Property-spl_update_prop': 'update_bar',
            'X-Image-Meta-Property-spl_delete_prop': 'delete_bar'
        }
        auth_headers.update(custom_props)
        auth_headers.update(CREATE_HEADERS)
        path = "/v1/images"
        response, content = self.http.request(path, 'POST',
                                              headers=auth_headers)
        self.assertEqual(201, response.status)
        data = jsonutils.loads(content)
        image_id = data['image']['id']

        # Attempt to update two properties, one protected(spl_read_prop), the
        # other not(spl_update_prop).  Request should be forbidden.
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:spl_role',
        }
        custom_props = {
            'X-Image-Meta-Property-spl_read_prop': 'r',
            'X-Image-Meta-Property-spl_update_prop': 'u',
            'X-Glance-Registry-Purge-Props': 'False'
        }
        auth_headers.update(auth_headers)
        auth_headers.update(custom_props)
        path = "/v1/images/%s" % image_id
        response, content = self.http.request(path, 'PUT',
                                              headers=auth_headers)
        self.assertEqual(403, response.status)

        # Attempt to create properties which are forbidden
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:spl_role',
        }
        custom_props = {
            'X-Image-Meta-Property-spl_new_prop': 'new',
            'X-Glance-Registry-Purge-Props': 'True'
        }
        auth_headers.update(auth_headers)
        auth_headers.update(custom_props)
        path = "/v1/images/%s" % image_id
        response, content = self.http.request(path, 'PUT',
                                              headers=auth_headers)
        self.assertEqual(403, response.status)

        # Attempt to update, create and delete properties
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:spl_role',
        }
        custom_props = {
            'X-Image-Meta-Property-spl_create_prop': 'create_bar',
            'X-Image-Meta-Property-spl_read_prop': 'read_bar',
            'X-Image-Meta-Property-spl_update_prop': 'u',
            'X-Glance-Registry-Purge-Props': 'True'
        }
        auth_headers.update(auth_headers)
        auth_headers.update(custom_props)
        path = "/v1/images/%s" % image_id
        response, content = self.http.request(path, 'PUT',
                                              headers=auth_headers)
        self.assertEqual(200, response.status)

        # Returned image entity should reflect the changes
        image = jsonutils.loads(content)

        # 'spl_update_prop' has update permission for spl_role
        # hence the value has changed
        self.assertEqual('u', image['image']['properties']['spl_update_prop'])

        # 'spl_delete_prop' has delete permission for spl_role
        # hence the property has been deleted
        self.assertNotIn('spl_delete_prop', image['image']['properties'])

        # 'spl_create_prop' has create permission for spl_role
        # hence the property has been created
        self.assertEqual('create_bar',
                         image['image']['properties']['spl_create_prop'])

        # Image Deletion should work
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:spl_role',
        }
        path = "/v1/images/%s" % image_id
        response, content = self.http.request(path, 'DELETE',
                                              headers=auth_headers)
        self.assertEqual(200, response.status)

        # This image should be no longer be directly accessible
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:spl_role',
        }
        path = "/v1/images/%s" % image_id
        response, content = self.http.request(path, 'HEAD',
                                              headers=auth_headers)
        self.assertEqual(404, response.status)

    def test_property_protections_special_chars(self):
        # Enable property protection
        self.config(property_protection_file=self.property_file)
        self.init()

        CREATE_HEADERS = {
            'X-Image-Meta-Name': 'MyImage',
            'X-Image-Meta-disk_format': 'raw',
            'X-Image-Meta-container_format': 'ovf',
            'X-Image-Meta-Is-Public': 'True',
            'X-Image-Meta-Owner': 'tenant2',
            'X-Image-Meta-Size': '0',
        }

        # Create an image
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:member',
        }
        auth_headers.update(CREATE_HEADERS)
        path = "/v1/images"
        response, content = self.http.request(path, 'POST',
                                              headers=auth_headers)
        self.assertEqual(201, response.status)
        data = jsonutils.loads(content)
        image_id = data['image']['id']

        # Verify both admin and unknown role can create properties marked with
        # '@'
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:admin',
        }
        custom_props = {
            'X-Image-Meta-Property-x_all_permitted_admin': '1'
        }
        auth_headers.update(custom_props)
        path = "/v1/images/%s" % image_id
        response, content = self.http.request(path, 'PUT',
                                              headers=auth_headers)
        self.assertEqual(200, response.status)
        image = jsonutils.loads(content)
        self.assertEqual('1',
                         image['image']['properties']['x_all_permitted_admin'])
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:joe_soap',
        }
        custom_props = {
            'X-Image-Meta-Property-x_all_permitted_joe_soap': '1',
            'X-Glance-Registry-Purge-Props': 'False'
        }
        auth_headers.update(custom_props)
        path = "/v1/images/%s" % image_id
        response, content = self.http.request(path, 'PUT',
                                              headers=auth_headers)
        self.assertEqual(200, response.status)
        image = jsonutils.loads(content)
        self.assertEqual(
            '1', image['image']['properties']['x_all_permitted_joe_soap'])

        # Verify both admin and unknown role can read properties marked with
        # '@'
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:admin',
        }
        path = "/v1/images/%s" % image_id
        response, content = self.http.request(path, 'HEAD',
                                              headers=auth_headers)
        self.assertEqual(200, response.status)
        self.assertEqual('1', response.get(
            'x-image-meta-property-x_all_permitted_admin'))
        self.assertEqual('1', response.get(
            'x-image-meta-property-x_all_permitted_joe_soap'))
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:joe_soap',
        }
        path = "/v1/images/%s" % image_id
        response, content = self.http.request(path, 'HEAD',
                                              headers=auth_headers)
        self.assertEqual(200, response.status)
        self.assertEqual('1', response.get(
            'x-image-meta-property-x_all_permitted_admin'))
        self.assertEqual('1', response.get(
            'x-image-meta-property-x_all_permitted_joe_soap'))

        # Verify both admin and unknown role can update properties marked with
        # '@'
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:admin',
        }
        custom_props = {
            'X-Image-Meta-Property-x_all_permitted_admin': '2',
            'X-Glance-Registry-Purge-Props': 'False'
        }
        auth_headers.update(custom_props)
        path = "/v1/images/%s" % image_id
        response, content = self.http.request(path, 'PUT',
                                              headers=auth_headers)
        self.assertEqual(200, response.status)
        image = jsonutils.loads(content)
        self.assertEqual('2',
                         image['image']['properties']['x_all_permitted_admin'])
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:joe_soap',
        }
        custom_props = {
            'X-Image-Meta-Property-x_all_permitted_joe_soap': '2',
            'X-Glance-Registry-Purge-Props': 'False'
        }
        auth_headers.update(custom_props)
        path = "/v1/images/%s" % image_id
        response, content = self.http.request(path, 'PUT',
                                              headers=auth_headers)
        self.assertEqual(200, response.status)
        image = jsonutils.loads(content)
        self.assertEqual(
            '2', image['image']['properties']['x_all_permitted_joe_soap'])

        # Verify both admin and unknown role can delete properties marked with
        # '@'
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:admin',
        }
        custom_props = {
            'X-Image-Meta-Property-x_all_permitted_joe_soap': '2',
            'X-Glance-Registry-Purge-Props': 'True'
        }
        auth_headers.update(custom_props)
        path = "/v1/images/%s" % image_id
        response, content = self.http.request(path, 'PUT',
                                              headers=auth_headers)
        self.assertEqual(200, response.status)
        image = jsonutils.loads(content)
        self.assertNotIn('x_all_permitted_admin', image['image']['properties'])
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:joe_soap',
        }
        custom_props = {
            'X-Glance-Registry-Purge-Props': 'True'
        }
        auth_headers.update(custom_props)
        path = "/v1/images/%s" % image_id
        response, content = self.http.request(path, 'PUT',
                                              headers=auth_headers)
        self.assertEqual(200, response.status)
        image = jsonutils.loads(content)
        self.assertNotIn('x_all_permitted_joe_soap',
                         image['image']['properties'])

        # Verify neither admin nor unknown role can create a property protected
        # with '!'
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:admin',
        }
        custom_props = {
            'X-Image-Meta-Property-x_none_permitted_admin': '1'
        }
        auth_headers.update(custom_props)
        path = "/v1/images/%s" % image_id
        response, content = self.http.request(path, 'PUT',
                                              headers=auth_headers)
        self.assertEqual(403, response.status)
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:joe_soap',
        }
        custom_props = {
            'X-Image-Meta-Property-x_none_permitted_joe_soap': '1'
        }
        auth_headers.update(custom_props)
        path = "/v1/images/%s" % image_id
        response, content = self.http.request(path, 'PUT',
                                              headers=auth_headers)
        self.assertEqual(403, response.status)

        # Verify neither admin nor unknown role can read properties marked with
        # '!'
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:admin',
        }
        custom_props = {
            'X-Image-Meta-Property-x_none_read': '1'
        }
        auth_headers.update(custom_props)
        auth_headers.update(CREATE_HEADERS)
        path = "/v1/images"
        response, content = self.http.request(path, 'POST',
                                              headers=auth_headers)
        self.assertEqual(201, response.status)
        data = jsonutils.loads(content)
        image_id = data['image']['id']
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:admin',
        }
        path = "/v1/images/%s" % image_id
        response, content = self.http.request(path, 'HEAD',
                                              headers=auth_headers)
        self.assertEqual(200, response.status)
        self.assertRaises(KeyError,
                          response.get, 'X-Image-Meta-Property-x_none_read')
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:joe_soap',
        }
        path = "/v1/images/%s" % image_id
        response, content = self.http.request(path, 'HEAD',
                                              headers=auth_headers)
        self.assertEqual(200, response.status)
        self.assertRaises(KeyError,
                          response.get, 'X-Image-Meta-Property-x_none_read')

        # Verify neither admin nor unknown role can update properties marked
        # with '!'
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:admin',
        }
        custom_props = {
            'X-Image-Meta-Property-x_none_update': '1'
        }
        auth_headers.update(custom_props)
        auth_headers.update(CREATE_HEADERS)
        path = "/v1/images"
        response, content = self.http.request(path, 'POST',
                                              headers=auth_headers)
        self.assertEqual(201, response.status)
        data = jsonutils.loads(content)
        image_id = data['image']['id']
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:admin',
        }
        custom_props = {
            'X-Image-Meta-Property-x_none_update': '2'
        }
        auth_headers.update(custom_props)
        path = "/v1/images/%s" % image_id
        response, content = self.http.request(path, 'PUT',
                                              headers=auth_headers)
        self.assertEqual(403, response.status)
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:joe_soap',
        }
        custom_props = {
            'X-Image-Meta-Property-x_none_update': '2'
        }
        auth_headers.update(custom_props)
        path = "/v1/images/%s" % image_id
        response, content = self.http.request(path, 'PUT',
                                              headers=auth_headers)
        self.assertEqual(403, response.status)

        # Verify neither admin nor unknown role can delete properties marked
        # with '!'
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:admin',
        }
        custom_props = {
            'X-Image-Meta-Property-x_none_delete': '1'
        }
        auth_headers.update(custom_props)
        auth_headers.update(CREATE_HEADERS)
        path = "/v1/images"
        response, content = self.http.request(path, 'POST',
                                              headers=auth_headers)
        self.assertEqual(201, response.status)
        data = jsonutils.loads(content)
        image_id = data['image']['id']
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:admin',
        }
        custom_props = {
            'X-Glance-Registry-Purge-Props': 'True'
        }
        auth_headers.update(custom_props)
        path = "/v1/images/%s" % image_id
        response, content = self.http.request(path, 'PUT',
                                              headers=auth_headers)
        self.assertEqual(403, response.status)
        auth_headers = {
            'X-Auth-Token': 'user1:tenant1:joe_soap',
        }
        custom_props = {
            'X-Glance-Registry-Purge-Props': 'True'
        }
        auth_headers.update(custom_props)
        path = "/v1/images/%s" % image_id
        response, content = self.http.request(path, 'PUT',
                                              headers=auth_headers)
        self.assertEqual(403, response.status)
