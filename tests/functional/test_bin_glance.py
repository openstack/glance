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
        api_port, reg_port, conf_file = self.start_servers()

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
        cmd = "bin/glance --port=%d delete 1" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('Deleted image 1', out.strip())

        # 4. Verify no public images
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('No public images found.', out.strip())

        self.stop_servers()
