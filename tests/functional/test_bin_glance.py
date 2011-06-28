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

import os
import tempfile
import unittest

from tests import functional
from tests.utils import execute


class TestBinGlance(functional.FunctionalTest):

    """Functional tests for the bin/glance CLI tool"""

    def test_add_list_delete_list(self):
        """
        We test the following:

            0. Verify no public images in index
            1. Add a public image with a location attr
               and no image data
            2. Check that image exists in index
            3. Delete the image
            4. Verify no longer in index
        """
        self.cleanup()
        self.start_servers()

        api_port = self.api_port
        registry_port = self.registry_port

        # 0. Verify no public images
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('No public images found.', out.strip())

        # 1. Add public image
        cmd = "bin/glance --port=%d add is_public=True name=MyImage" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('Added new image with ID: 1', out.strip())

        # 2. Verify image added as public image
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        lines = out.split("\n")
        first_line = lines[0]
        image_data_line = lines[3]
        self.assertEqual('Found 1 public images...', first_line)
        self.assertTrue('MyImage' in image_data_line)

        # 3. Delete the image
        cmd = "bin/glance --port=%d --force delete 1" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('Deleted image 1', out.strip())

        # 4. Verify no public images
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('No public images found.', out.strip())

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
        self.start_servers()

        api_port = self.api_port
        registry_port = self.registry_port

        # 0. Verify no public images
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('No public images found.', out.strip())

        # 1. Add public image
        cmd = "bin/glance --port=%d add name=MyImage" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('Added new image with ID: 1', out.strip())

        # 2. Verify image does not appear as a public image
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('No public images found.', out.strip())

        # 3. Update the image to make it public
        cmd = "bin/glance --port=%d update 1 is_public=True" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('Updated image 1', out.strip())

        # 4. Verify image 1 in list of public images
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        lines = out.split("\n")
        first_line = lines[0]
        self.assertEqual('Found 1 public images...', first_line)

        image_data_line = lines[3]
        self.assertTrue('MyImage' in image_data_line)

        # 5. Update the image's Name attribute
        updated_image_name = "Updated image name"
        cmd = "bin/glance --port=%d update 1 is_public=True name=\"%s\"" \
                % (api_port, updated_image_name)

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('Updated image 1', out.strip())

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
            3. Verify the status of the image is displayed in the show output
               and is in status 'killed'
        """
        self.cleanup()

        # Start servers with a Swift backend and a bad auth URL
        options = {'default_store': 'swift',
                   'swift_store_auth_address': 'badurl'}
        self.start_servers(**options)

        api_port = self.api_port
        registry_port = self.registry_port

        # 0. Verify no public images
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('No public images found.', out.strip())

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
        self.assertEqual('No public images found.', out.strip())

        # 3. Verify image status in show is 'killed'
        cmd = "bin/glance --port=%d show 1" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertTrue('Status: killed' in out)

        self.stop_servers()

    @functional.runs_sql
    def test_add_clear(self):
        """
        We test the following:

            1. Add a couple images with metadata
            2. Clear the images
            3. Verify no public images found
            4. Run SQL against DB to verify no undeleted properties
        """
        self.cleanup()
        self.start_servers()

        api_port = self.api_port
        registry_port = self.registry_port

        # 1. Add some images
        for i in range(1, 5):
            cmd = "bin/glance --port=%d add is_public=True name=MyName " \
                  " foo=bar" % api_port
            exitcode, out, err = execute(cmd)

            self.assertEqual(0, exitcode)
            self.assertEqual('Added new image with ID: %i' % i, out.strip())

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
        self.assertEqual('No public images found.', first_line)

        # 4. Lastly we manually verify with SQL that image properties are
        # also getting marked as deleted.
        sql = "SELECT COUNT(*) FROM image_properties WHERE deleted = 0"
        recs = self.run_sql_cmd(sql)
        for rec in recs:
            self.assertEqual(0, rec[0])

        self.stop_servers()
