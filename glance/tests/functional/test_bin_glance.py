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

"""Functional test case that utilizes the bin/glance CLI tool"""

import BaseHTTPServer
import datetime
import httplib2
import json
import os
import tempfile
import thread
import time

from glance.openstack.common import timeutils
from glance.tests import functional
from glance.tests.functional.store_utils import (setup_http,
                                                 teardown_http,
                                                 get_http_uri)
from glance.tests.utils import execute, requires, minimal_add_command


class TestBinGlance(functional.FunctionalTest):
    """Functional tests for the bin/glance CLI tool"""

    def setUp(self):
        super(TestBinGlance, self).setUp()

        # NOTE(sirp): This is needed in case we are running the tests under an
        # environment in which OS_AUTH_STRATEGY=keystone. The test server we
        # spin up won't have keystone support, so we need to switch to the
        # NoAuth strategy.
        os.environ['OS_AUTH_STRATEGY'] = 'noauth'
        os.environ['OS_AUTH_URL'] = ''

    def _assertStartsWith(self, str, prefix):
        msg = 'expected "%s" to start with "%s"' % (str, prefix)
        self.assertTrue(str.startswith(prefix), msg)

    def _assertNotIn(self, key, bag):
        msg = 'Expected not to find substring "%s" in "%s"' % (key, bag)
        self.assertFalse(key in bag, msg)

    def test_index_with_https(self):
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        cmd = ("bin/glance -N https://auth/ --port=%d index") % self.api_port
        exitcode, out, err = execute(cmd, raise_error=False)

        self.assertNotEqual(0, exitcode)
        self._assertNotIn('SSL23_GET_SERVER_HELLO', out)

        self.stop_servers()

    def test_add_with_location_and_id(self):
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        api_port = self.api_port
        registry_port = self.registry_port

        # 0. Verify no public images
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('', out.strip())

        image_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

        # 1a. Add public image
        cmd = minimal_add_command(api_port,
                                  'MyImage',
                                  'id=%s' % image_id,
                                  'location=http://example.com')
        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        expected = 'Added new image with ID: %s' % image_id
        self.assertTrue(expected in out)

        # 1b. Add public image with non-uuid id
        cmd = minimal_add_command(api_port,
                                  'MyImage',
                                  'id=12345',
                                  'location=http://example.com')
        exitcode, out, err = execute(cmd, expected_exitcode=1)

        self.assertEqual(1, exitcode)
        self.assertTrue('Invalid image id format' in out)

        # 2. Verify image added as public image
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        lines = out.split("\n")[2:-1]
        self.assertEqual(1, len(lines))

        line = lines[0]

        image_id, name, disk_format, container_format, size = \
            [c.strip() for c in line.split()]
        self.assertEqual('MyImage', name)

        self.assertEqual('0', size, "Expected image to be 0 bytes in size, "
                                    "but got %s. " % size)

        self.stop_servers()

    def test_add_with_location(self):
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        api_port = self.api_port
        registry_port = self.registry_port

        # 0. Verify no public images
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('', out.strip())

        # 1. Add public image
        cmd = minimal_add_command(api_port,
                                  'MyImage',
                                  'location=http://localhost:0')
        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertTrue(out.strip().startswith('Added new image with ID:'))

        # 2. Verify image added as public image
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        lines = out.split("\n")[2:-1]
        self.assertEqual(1, len(lines))

        line = lines[0]

        img_info = [c.strip() for c in line.split()]
        image_id, name, disk_format, container_format, size = img_info
        self.assertEqual('MyImage', name)

        self.assertEqual('0', size, "Expected image to be 0 bytes in size, "
                                    "but got %s. " % size)

        self.stop_servers()

    def test_add_no_name(self):
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        api_port = self.api_port
        registry_port = self.registry_port

        # 0. Verify no public images
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('', out.strip())

        # 1. Add public image
        # Can't use minimal_add_command since that uses
        # name...
        cmd = ("bin/glance --port=%d add is_public=True"
               " disk_format=raw container_format=ovf"
               " %s" % (api_port, 'location=http://localhost:0'))
        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertTrue(out.strip().startswith('Added new image with ID:'))

        # 2. Verify image added as public image
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        lines = out.split("\n")[2:-1]
        self.assertEqual(1, len(lines))

        line = lines[0]

        image_id, name, disk_format, container_format, size = \
            [c.strip() for c in line.split()]
        self.assertEqual('None', name)

        self.stop_servers()

    @requires(teardown=teardown_http)
    def test_add_copying_from(self):
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        setup_http(self)

        api_port = self.api_port
        registry_port = self.registry_port

        # 0. Verify no public images
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('', out.strip())

        # 1. Add public image
        suffix = 'copy_from=%s' % get_http_uri(self, 'foobar')
        cmd = minimal_add_command(api_port, 'MyImage', suffix)
        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertTrue(out.strip().startswith('Added new image with ID:'))

        # 2. Verify image added as public image
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        lines = out.split("\n")[2:-1]
        self.assertEqual(1, len(lines))

        line = lines[0]

        image_id, name, disk_format, container_format, size = \
            [c.strip() for c in line.split()]
        self.assertEqual('MyImage', name)

        self.assertEqual('5120', size, "Expected image to be 5120 bytes "
                                       " in size, but got %s. " % size)

        self.stop_servers()

    def _do_test_update_external_source(self, source):
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        setup_http(self)

        api_port = self.api_port
        registry_port = self.registry_port

        # 1. Add public image with no image content
        headers = {'X-Image-Meta-Name': 'MyImage',
                   'X-Image-Meta-disk_format': 'raw',
                   'X-Image-Meta-container_format': 'ovf',
                   'X-Image-Meta-Is-Public': 'True'}
        path = "http://%s:%d/v1/images" % ("0.0.0.0", api_port)
        http = httplib2.Http()
        response, content = http.request(path, 'POST', headers=headers)
        self.assertEqual(response.status, 201)
        data = json.loads(content)
        self.assertEqual(data['image']['name'], 'MyImage')
        image_id = data['image']['id']

        # 2. Update image with external source
        source = '%s=%s' % (source, get_http_uri(self, 'foobar'))
        cmd = "bin/glance update %s %s -p %d" % (image_id, source, api_port)
        exitcode, out, err = execute(cmd, raise_error=False)

        self.assertEqual(0, exitcode)
        self.assertTrue(out.strip().endswith('Updated image %s' % image_id))

        # 3. Verify image is now active and of the correct size
        cmd = "bin/glance --port=%d show %s" % (api_port, image_id)

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)

        expected_lines = [
            'URI: http://0.0.0.0:%s/v1/images/%s' % (api_port, image_id),
            'Id: %s' % image_id,
            'Public: Yes',
            'Name: MyImage',
            'Status: active',
            'Size: 5120',
            'Disk format: raw',
            'Container format: ovf',
            'Minimum Ram Required (MB): 0',
            'Minimum Disk Required (GB): 0',
        ]
        lines = out.split("\n")
        self.assertTrue(set(lines) >= set(expected_lines))

        self.stop_servers()

    @requires(teardown=teardown_http)
    def test_update_copying_from(self):
        """
        Tests creating an queued image then subsequently updating
        with a copy-from source
        """
        self._do_test_update_external_source('copy_from')

    @requires(teardown=teardown_http)
    def test_update_location(self):
        """
        Tests creating an queued image then subsequently updating
        with a location source
        """
        self._do_test_update_external_source('location')

    def test_add_with_location_and_stdin(self):
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        api_port = self.api_port
        registry_port = self.registry_port

        # 0. Verify no public images
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('', out.strip())

        # 1. Add public image
        with tempfile.NamedTemporaryFile() as image_file:
            image_file.write("XXX")
            image_file.flush()
            file_name = image_file.name
            cmd = minimal_add_command(api_port,
                                     'MyImage',
                                     'location=http://localhost:0 < %s' %
                                     file_name)
            exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertTrue(out.strip().startswith('Added new image with ID:'))

        # 2. Verify image added as public image
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        lines = out.split("\n")[2:-1]
        self.assertEqual(1, len(lines))

        line = lines[0]

        img_info = [c.strip() for c in line.split()]
        image_id, name, disk_format, container_format, size = img_info
        self.assertEqual('MyImage', name)

        self.assertEqual('0', size, "Expected image to be 0 bytes in size, "
                                    "but got %s. " % size)

        self.stop_servers()

    def test_add_list_delete_list(self):
        """
        We test the following:

            0. Verify no public images in index
            1. Add a public image
            2. Check that image exists in index
            3. Delete the image
            4. Verify no longer in index
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        api_port = self.api_port
        registry_port = self.registry_port

        # 0. Verify no public images
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('', out.strip())

        # 1. Add public image
        with tempfile.NamedTemporaryFile() as image_file:
            image_file.write("XXX")
            image_file.flush()
            image_file_name = image_file.name
            suffix = '--silent-upload < %s' % image_file_name
            cmd = minimal_add_command(api_port, 'MyImage', suffix)

            exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        msg = out.split("\n")

        self._assertStartsWith(msg[0], 'Added new image with ID:')

        # 2. Verify image added as public image
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        lines = out.split("\n")[2:-1]
        self.assertEqual(1, len(lines))

        line = lines[0]

        img_info = [c.strip() for c in line.split()]
        image_id, name, disk_format, container_format, size = img_info
        self.assertEqual('MyImage', name)

        self.assertEqual('3', size,
                         "Expected image to be 3 bytes in size, but got %s. "
                         "Make sure you're running the correct version "
                         "of webob." % size)

        # 3. Delete the image
        cmd = "bin/glance --port=%d --force delete %s" % (api_port, image_id)

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('Deleted image %s' % image_id, out.strip())

        # 4. Verify no public images
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('', out.strip())

        self.stop_servers()

    def test_add_list_update_list(self):
        """
        Test for LP Bugs #736295, #767203
        We test the following:

            0. Verify no public images in index
            1. Add a NON-public image
            2. Check that image does not appear in index
            3. Update the image to be public
            4. Check that image now appears in index
            5. Update the image's Name attribute
            6. Verify the updated name is shown
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        api_port = self.api_port
        registry_port = self.registry_port

        # 0. Verify no public images
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('', out.strip())

        # 1. Add public image
        cmd = minimal_add_command(api_port,
                                  'MyImage',
                                  'location=http://localhost:0',
                                  public=False)

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        msg = out.split('\n')
        self.assertTrue(msg[0].startswith('Added new image with ID:'))

        image_id = out.strip().split(':')[1].strip()

        # 2. Verify image does not appear as a public image
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('', out.strip())

        # 3. Update the image to make it public
        cmd = "bin/glance --port=%d update %s is_public=True" % (
            api_port, image_id)

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('Updated image %s' % image_id, out.strip())

        # 4. Verify image 1 in list of public images
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        lines = out.split("\n")[2:-1]
        self.assertEqual(len(lines), 1)
        self.assertTrue('MyImage' in lines[0])

        # 5. Update the image's Name attribute
        updated_image_name = "Updated image name"
        cmd = ("bin/glance --port=%d update %s is_public=True name=\"%s\"" %
               (api_port, image_id, updated_image_name))

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('Updated image %s' % image_id, out.strip())

        # 6. Verify updated name shown
        cmd = "bin/glance --port=%d index" % api_port
        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertTrue(updated_image_name in out,
                        "%s not found in %s" % (updated_image_name, out))

        self.stop_servers()

    def test_killed_image_not_in_index(self):
        """
        We test conditions that produced LP Bug #768969, where an image
        in the 'killed' status is displayed in the output of glance index,
        and the status column is not displayed in the output of
        glance show <ID>.

            Start servers with Swift backend and a bad auth URL, and then:
            0. Verify no public images in index
            1. Attempt to add an image
            2. Verify the image does NOT appear in the index output
        """
        self.cleanup()

        # Start servers with a Swift backend and a bad auth URL
        override_options = {
            'default_store': 'swift',
            'swift_store_auth_address': 'badurl',
        }
        options = self.__dict__.copy()
        options.update(override_options)
        self.start_servers(**options)

        api_port = self.api_port
        registry_port = self.registry_port

        # 0. Verify no public images
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('', out.strip())

        # 1. Attempt to add an image
        with tempfile.NamedTemporaryFile() as image_file:
            image_file.write("XXX")
            image_file.flush()
            image_file_name = image_file.name
            cmd = ("bin/glance --port=%d add name=Jonas is_public=True "
                   "disk_format=qcow2 container_format=bare < %s"
                   % (api_port, image_file_name))

            exitcode, out, err = execute(cmd, raise_error=False)

            self.assertNotEqual(0, exitcode)
            self.assertTrue('Failed to add image.' in out)

        # 2. Verify image does not appear as public image
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('', out.strip())

        self.stop_servers()

    def test_add_location_with_checksum(self):
        """
        We test the following:

            1. Add an image with location and checksum
            2. Run SQL against DB to verify checksum was entered correctly
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        api_port = self.api_port
        registry_port = self.registry_port

        # 1. Add public image
        cmd = minimal_add_command(api_port,
                                 'MyImage',
                                 'location=http://localhost:0 checksum=1')
        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertTrue(out.strip().startswith('Added new image with ID:'))

        image_id = out.split(":")[1].strip()

        sql = 'SELECT checksum FROM images WHERE id = "%s"' % image_id
        recs = self.run_sql_cmd(sql)

        self.assertEqual('1', recs.first()[0])

        self.stop_servers()

    def test_add_location_without_checksum(self):
        """
        We test the following:

            1. Add an image with location and no checksum
            2. Run SQL against DB to verify checksum is NULL
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        api_port = self.api_port
        registry_port = self.registry_port

        # 1. Add public image
        cmd = minimal_add_command(api_port,
                                 'MyImage',
                                 'location=http://localhost:0')
        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertTrue(out.strip().startswith('Added new image with ID:'))

        image_id = out.split(":")[1].strip()

        sql = 'SELECT checksum FROM images WHERE id = "%s"' % image_id
        recs = self.run_sql_cmd(sql)

        self.assertEqual(None, recs.first()[0])

        self.stop_servers()

    def test_add_clear(self):
        """
        We test the following:

            1. Add a couple images with metadata
            2. Clear the images
            3. Verify no public images found
            4. Run SQL against DB to verify no undeleted properties
        """
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        api_port = self.api_port
        registry_port = self.registry_port

        # 1. Add some images
        for i in range(1, 5):
            cmd = minimal_add_command(api_port,
                                      'MyImage',
                                      'foo=bar')
            exitcode, out, err = execute(cmd)

            self.assertEqual(0, exitcode)
            self.assertTrue(out.strip().find('Added new image with ID:') > -1)

        # 2. Clear all images
        cmd = "bin/glance --port=%d --force clear" % api_port
        exitcode, out, err = execute(cmd)
        self.assertEqual(0, exitcode)

        # 3. Verify no public images are found
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        lines = out.split("\n")
        first_line = lines[0]
        self.assertEqual('', first_line)

        # 4. Lastly we manually verify with SQL that image properties are
        # also getting marked as deleted.
        sql = "SELECT COUNT(*) FROM image_properties WHERE deleted = 0"
        recs = self.run_sql_cmd(sql)
        for rec in recs:
            self.assertEqual(0, rec[0])

        self.stop_servers()

    def test_results_filtering(self):
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        api_port = self.api_port
        registry_port = self.registry_port

        # 1. Add some images
        _add_cmd = "bin/glance --port=%d add is_public=True" % api_port
        _add_args = [
            "name=Name1 disk_format=vhd container_format=ovf foo=bar",
            "name=Name2 disk_format=ami container_format=ami foo=bar",
            "name=Name3 disk_format=vhd container_format=ovf foo=baz "
            "min_disk=7 min_ram=256",
        ]

        image_ids = []
        for i, args in enumerate(_add_args):
            cmd = "%s %s" % (_add_cmd, args)
            exitcode, out, err = execute(cmd)
            self.assertEqual(0, exitcode)
            self.assertTrue(out.strip().find('Added new image with ID:') > -1)
            image_ids.append(out.strip().split(':')[1].strip())

        _base_cmd = "bin/glance --port=%d" % api_port
        _index_cmd = "%s index -f" % (_base_cmd,)

        # 2. Check name filter
        cmd = "name=Name2"
        exitcode, out, err = execute("%s %s" % (_index_cmd, cmd))
        image_lines = out.split("\n")[2:-1]

        self.assertEqual(0, exitcode)
        self.assertEqual(1, len(image_lines))
        self.assertEqual(image_lines[0].split()[0], image_ids[1])

        # 3. Check disk_format filter
        cmd = "disk_format=vhd"
        exitcode, out, err = execute("%s %s" % (_index_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(2, len(image_lines))
        self.assertEqual(image_lines[0].split()[0], image_ids[2])
        self.assertEqual(image_lines[1].split()[0], image_ids[0])

        # 4. Check container_format filter
        cmd = "container_format=ami"
        exitcode, out, err = execute("%s %s" % (_index_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(1, len(image_lines))
        self.assertEqual(image_lines[0].split()[0], image_ids[1])

        # 5. Check container_format filter
        cmd = "container_format=ami"
        exitcode, out, err = execute("%s %s" % (_index_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(1, len(image_lines))
        self.assertEqual(image_lines[0].split()[0], image_ids[1])

        # 6. Check status filter
        cmd = "status=killed"
        exitcode, out, err = execute("%s %s" % (_index_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(0, len(image_lines))

        # 7. Check property filter
        cmd = "foo=bar"
        exitcode, out, err = execute("%s %s" % (_index_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(2, len(image_lines))
        self.assertEqual(image_lines[0].split()[0], image_ids[1])
        self.assertEqual(image_lines[1].split()[0], image_ids[0])

        # 8. Check multiple filters
        cmd = "name=Name2 foo=bar"
        exitcode, out, err = execute("%s %s" % (_index_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(1, len(image_lines))
        self.assertEqual(image_lines[0].split()[0], image_ids[1])

        # 9. Check past changes-since
        dt1 = timeutils.utcnow() - datetime.timedelta(1)
        iso1 = timeutils.isotime(dt1)
        cmd = "changes-since=%s" % iso1
        exitcode, out, err = execute("%s %s" % (_index_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(3, len(image_lines))
        self.assertEqual(image_lines[0].split()[0], image_ids[2])
        self.assertEqual(image_lines[1].split()[0], image_ids[1])
        self.assertEqual(image_lines[2].split()[0], image_ids[0])

        # 10. Check future changes-since
        dt2 = timeutils.utcnow() + datetime.timedelta(1)
        iso2 = timeutils.isotime(dt2)
        cmd = "changes-since=%s" % iso2
        exitcode, out, err = execute("%s %s" % (_index_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(0, len(image_lines))

        # 11. Ensure details call also respects filters
        _details_cmd = "%s details" % (_base_cmd,)
        cmd = "foo=bar"
        exitcode, out, err = execute("%s %s" % (_details_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[1:-1]
        self.assertEqual(30, len(image_lines))
        self.assertEqual(image_lines[1].split()[1], image_ids[1])
        self.assertEqual(image_lines[16].split()[1], image_ids[0])

        # 12. Check min_ram filter
        cmd = "min_ram=256"
        exitcode, out, err = execute("%s %s" % (_details_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(14, len(image_lines))
        self.assertEqual(image_lines[0].split()[1], image_ids[2])

        # 13. Check min_disk filter
        cmd = "min_disk=7"
        exitcode, out, err = execute("%s %s" % (_details_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(14, len(image_lines))
        self.assertEqual(image_lines[0].split()[1], image_ids[2])

        self.stop_servers()

    def test_results_pagination(self):
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        _base_cmd = "bin/glance --port=%d" % self.api_port
        index_cmd = "%s index -f" % _base_cmd
        details_cmd = "%s details -f" % _base_cmd

        # 1. Add some images
        _add_cmd = "bin/glance --port=%d add is_public=True" % self.api_port
        _add_args = [
            "name=Name1 disk_format=ami container_format=ami",
            "name=Name2 disk_format=vhd container_format=ovf",
            "name=Name3 disk_format=ami container_format=ami",
            "name=Name4 disk_format=ami container_format=ami",
            "name=Name5 disk_format=vhd container_format=ovf",
        ]

        image_ids = []

        for i, args in enumerate(_add_args):
            cmd = "%s %s" % (_add_cmd, args)
            exitcode, out, err = execute(cmd)
            self.assertEqual(0, exitcode)
            expected_out = 'Added new image with ID: %d' % (i + 1,)
            self.assertTrue(out.strip().find('Added new image with ID:') > -1)
            image_ids.append(out.strip().split(':')[1].strip())

        # 2. Limit less than total
        cmd = "--limit=3"
        exitcode, out, err = execute("%s %s" % (index_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(5, len(image_lines))
        self.assertTrue(image_lines[0].split()[0], image_ids[0])
        self.assertTrue(image_lines[1].split()[0], image_ids[1])
        self.assertTrue(image_lines[2].split()[0], image_ids[2])
        self.assertTrue(image_lines[3].split()[0], image_ids[3])
        self.assertTrue(image_lines[4].split()[0], image_ids[4])

        # 3. With a marker
        cmd = "--marker=%s" % image_ids[3]
        exitcode, out, err = execute("%s %s" % (index_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(3, len(image_lines))
        self.assertTrue(image_lines[0].split()[0], image_ids[1])
        self.assertTrue(image_lines[1].split()[0], image_ids[2])
        self.assertTrue(image_lines[2].split()[0], image_ids[3])

        # 3. With a marker and limit
        cmd = "--marker=%s --limit=1" % image_ids[2]
        exitcode, out, err = execute("%s %s" % (index_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(2, len(image_lines))
        self.assertTrue(image_lines[0].split()[0], image_ids[1])
        self.assertTrue(image_lines[1].split()[0], image_ids[2])

        # 4. Pagination params with filtered results
        cmd = "--marker=%s --limit=1 container_format=ami" % image_ids[3]
        exitcode, out, err = execute("%s %s" % (index_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(2, len(image_lines))
        self.assertTrue(image_lines[0].split()[0], image_ids[2])
        self.assertTrue(image_lines[1].split()[0], image_ids[1])

        # 5. Pagination params with filtered results in a details call
        cmd = "--marker=%s --limit=1 container_format=ami" % image_ids[3]
        exitcode, out, err = execute("%s %s" % (details_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[1:-1]
        self.assertEqual(28, len(image_lines))
        self.assertTrue(image_lines[1].split()[1], image_ids[2])
        self.assertTrue(image_lines[15].split()[1], image_ids[1])

        self.stop_servers()

    def test_results_sorting(self):
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        _base_cmd = "bin/glance --port=%d" % self.api_port
        index_cmd = "%s index -f" % _base_cmd
        details_cmd = "%s details -f" % _base_cmd

        # 1. Add some images
        _add_cmd = "bin/glance --port=%d add is_public=True" % self.api_port
        _add_args = [
            "name=Name1 disk_format=ami container_format=ami",
            "name=Name4 disk_format=vhd container_format=ovf",
            "name=Name3 disk_format=ami container_format=ami",
            "name=Name2 disk_format=ami container_format=ami",
            "name=Name5 disk_format=vhd container_format=ovf",
        ]

        image_ids = []
        for i, args in enumerate(_add_args):
            cmd = "%s %s" % (_add_cmd, args)
            exitcode, out, err = execute(cmd)
            self.assertEqual(0, exitcode)
            expected_out = 'Added new image with ID: %d' % (i + 1,)
            self.assertTrue(out.strip().find('Added new image with ID:') > -1)
            image_ids.append(out.strip().split(':')[1].strip())

        # 2. Sort by name asc
        cmd = "--sort_key=name --sort_dir=asc"
        exitcode, out, err = execute("%s %s" % (index_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(5, len(image_lines))
        self.assertTrue(image_lines[0].split()[0], image_ids[0])
        self.assertTrue(image_lines[1].split()[0], image_ids[1])
        self.assertTrue(image_lines[2].split()[0], image_ids[2])
        self.assertTrue(image_lines[3].split()[0], image_ids[3])
        self.assertTrue(image_lines[4].split()[0], image_ids[4])

        # 3. Sort by name asc with a marker
        cmd = "--sort_key=name --sort_dir=asc --marker=%s" % image_ids[3]
        exitcode, out, err = execute("%s %s" % (index_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(3, len(image_lines))
        self.assertTrue(image_lines[0].split()[0], image_ids[2])
        self.assertTrue(image_lines[1].split()[0], image_ids[1])
        self.assertTrue(image_lines[2].split()[0], image_ids[4])

        # 4. Sort by container_format desc
        cmd = "--sort_key=container_format --sort_dir=desc --limit=10"
        exitcode, out, err = execute("%s %s" % (index_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(5, len(image_lines))
        self.assertTrue(image_lines[0].split()[0], image_ids[4])
        self.assertTrue(image_lines[1].split()[0], image_ids[1])
        self.assertTrue(image_lines[2].split()[0], image_ids[3])
        self.assertTrue(image_lines[3].split()[0], image_ids[2])
        self.assertTrue(image_lines[4].split()[0], image_ids[0])

        # 5. Sort by name asc with a marker (details)
        cmd = "--sort_key=name --sort_dir=asc --marker=%s" % image_ids[3]
        exitcode, out, err = execute("%s %s" % (details_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[1:-1]
        self.assertEqual(42, len(image_lines))
        self.assertTrue(image_lines[1].split()[1], image_ids[2])
        self.assertTrue(image_lines[15].split()[1], image_ids[1])
        self.assertTrue(image_lines[29].split()[1], image_ids[4])

        self.stop_servers()

    def test_show_image_format(self):
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        api_port = self.api_port
        registry_port = self.registry_port

        # 1. Add public image
        with tempfile.NamedTemporaryFile() as image_file:
            image_file.write("XXX")
            image_file.flush()
            image_file_name = image_file.name
            suffix = ' --silent-upload < %s' % image_file_name
            cmd = minimal_add_command(api_port, 'MyImage', suffix)

            exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        image_id = out.strip().rsplit(' ', 1)[1]

        # 2. Verify image added as public image
        cmd = "bin/glance --port=%d show %s" % (api_port, image_id)

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        lines = out.split("\n")[:-1]

        expected_lines = [
            'URI: http://0.0.0.0:%s/v1/images/%s' % (api_port, image_id),
            'Id: %s' % image_id,
            'Public: Yes',
            'Name: MyImage',
            'Status: active',
            'Size: 3',
            'Disk format: raw',
            'Container format: ovf',
            'Minimum Ram Required (MB): 0',
            'Minimum Disk Required (GB): 0',
        ]

        self.assertTrue(set(lines) >= set(expected_lines))

        # 3. Delete the image
        cmd = "bin/glance --port=%d --force delete %s" % (api_port, image_id)

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('Deleted image %s' % image_id, out.strip())

        self.stop_servers()

    def test_protected_image(self):
        """
        We test the following:

            0. Verify no public images in index
            1. Add a public image with a location attr
               protected and no image data
            2. Check that image exists in index
            3. Attempt to delete the image
            4. Remove protection from image
            5. Delete the image
            6. Verify no longer in index
        """
        self.cleanup()
        self.start_servers()

        api_port = self.api_port
        registry_port = self.registry_port

        # 0. Verify no public images
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('', out.strip())

        # 1. Add public image
        cmd = ("echo testdata | " +
               minimal_add_command(api_port,
                                   'MyImage',
                                   'protected=True'))

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        msg = out.split("\n")
        self.assertTrue(msg[3].startswith('Added new image with ID:'))

        # 2. Verify image added as public image
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        lines = out.split("\n")[2:-1]
        self.assertEqual(1, len(lines))

        line = lines[0]

        img_info = [c.strip() for c in line.split()]
        image_id, name, disk_format, container_format, size = img_info
        self.assertEqual('MyImage', name)

        # 3. Delete the image
        cmd = "bin/glance --port=%d --force delete %s" % (api_port, image_id)

        exitcode, out, err = execute(cmd, raise_error=False)

        self.assertNotEqual(0, exitcode)
        self.assertTrue(out.startswith('You do not have permission'))

        # 4. Remove image protection
        cmd = ("bin/glance --port=%d --force update %s "
               "protected=False" % (api_port, image_id))

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertTrue(out.strip().startswith('Updated image'))

        # 5. Delete the image
        cmd = "bin/glance --port=%d --force delete %s" % (api_port, image_id)

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertTrue(out.strip().startswith('Deleted image'))

        # 6. Verify no public images
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('', out.strip())

        self.stop_servers()

    def test_timeout(self):
        self.cleanup()

        keep_sleeping = True

        #start a simple HTTP server in a thread that hangs for a bit
        class RemoteImageHandler(BaseHTTPServer.BaseHTTPRequestHandler):
            def do_GET(self):
                cnt = 1
                while (keep_sleeping):
                    cnt += 1
                    time.sleep(0.1)
                    if cnt > 100:
                        break

        server_class = BaseHTTPServer.HTTPServer
        local_server = server_class(('127.0.0.1', 0), RemoteImageHandler)
        local_ip, local_port = local_server.server_address

        def serve_requests(httpd):
            httpd.serve_forever()

        thread.start_new_thread(serve_requests, (local_server,))

        cmd = ("bin/glance --port=%d index --timeout=1") % local_port
        exitcode, out, err = execute(cmd, raise_error=False)

        keep_sleeping = False
        local_server.shutdown()
        self.assertNotEqual(0, exitcode)
        self.assertTrue("timed out" in out)

    def test_add_member(self):
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        api_port = self.api_port
        registry_port = self.registry_port

        image_id = "11111111-1111-1111-1111-111111111111"
        member_id = "21111111-2111-2111-2111-211111111111"
        member2_id = "31111111-3111-3111-3111-311111111111"

        # 0. Add an image
        cmd = minimal_add_command(api_port,
                                  'MyImage',
                                  'id=%s' % image_id,
                                  'location=http://example.com')
        exitcode, out, err = execute(cmd)

        # 1. Add an image member
        cmd = "bin/glance --port=%d member-add %s %s" % (api_port, image_id,
                                                         member_id)
        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('', out.strip())

        # 2. Verify image-members
        cmd = "bin/glance --port=%d image-members %s " % (api_port, image_id)
        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertTrue(member_id in out)

        # 3. Verify member-images
        cmd = "bin/glance --port=%d member-images %s " % (api_port, member_id)
        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertTrue(image_id in out)

        # 4. Replace image members
        cmd = "bin/glance --port=%d members-replace %s %s" % (api_port,
                                                              image_id,
                                                              member2_id)
        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('', out.strip())

        # 5. Verify member-images again for member2
        cmd = "bin/glance --port=%d member-images %s " % (api_port, member2_id)
        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertTrue(image_id in out)

        # 6. Verify member-images again for member1 (should not be present)
        cmd = "bin/glance --port=%d member-images %s " % (api_port, member_id)
        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertTrue(image_id not in out)

        # 7. Delete the member
        cmd = "bin/glance --port=%d member-delete %s %s" % (api_port, image_id,
                                                            member2_id)
        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('', out.strip())

        # 8. Verify image-members is empty
        cmd = "bin/glance --port=%d image-members %s " % (api_port, image_id)
        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('', out.strip())

        self.stop_servers()
