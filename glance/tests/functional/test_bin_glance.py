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

from glance.tests import functional
from glance.tests.utils import execute


class TestBinGlance(functional.FunctionalTest):
    """Functional tests for the bin/glance CLI tool"""

    def setUp(self):
        super(TestBinGlance, self).setUp()

        # NOTE(sirp): This is needed in case we are running the tests under an
        # environment in which OS_AUTH_STRATEGY=keystone. The test server we
        # spin up won't have keystone support, so we need to switch to the
        # NoAuth strategy.
        os.environ['OS_AUTH_STRATEGY'] = 'noauth'

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
        self.start_servers()

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
            cmd = "bin/glance --port=%d add is_public=True"\
                  " name=MyImage < %s" % (api_port, image_file_name)

            exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('Added new image with ID: 1', out.strip())

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

        self.assertEqual('3', size,
                         "Expected image to be 3 bytes in size, but got %s. "
                         "Make sure you're running the correct version "
                         "of webob." % size)

        # 3. Delete the image
        cmd = "bin/glance --port=%d --force delete 1" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('Deleted image 1', out.strip())

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
        self.start_servers()

        api_port = self.api_port
        registry_port = self.registry_port

        # 0. Verify no public images
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('', out.strip())

        # 1. Add public image
        cmd = "bin/glance --port=%d add name=MyImage" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('Added new image with ID: 1', out.strip())

        # 2. Verify image does not appear as a public image
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('', out.strip())

        # 3. Update the image to make it public
        cmd = "bin/glance --port=%d update 1 is_public=True" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('Updated image 1', out.strip())

        # 4. Verify image 1 in list of public images
        cmd = "bin/glance --port=%d index" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        lines = out.split("\n")[2:-1]
        self.assertEqual(len(lines), 1)
        self.assertTrue('MyImage' in lines[0])

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
        self.start_servers()

        api_port = self.api_port
        registry_port = self.registry_port

        # 1. Add some images
        _add_cmd = "bin/glance --port=%d add is_public=True" % api_port
        _add_args = [
            "name=Name1 disk_format=vhd container_format=ovf foo=bar",
            "name=Name2 disk_format=ami container_format=ami foo=bar",
            "name=Name3 disk_format=vhd container_format=ovf foo=baz",
        ]

        for i, args in enumerate(_add_args):
            cmd = "%s %s" % (_add_cmd, args)
            exitcode, out, err = execute(cmd)
            self.assertEqual(0, exitcode)
            expected_out = 'Added new image with ID: %d' % (i + 1,)
            self.assertEqual(expected_out, out.strip())

        _base_cmd = "bin/glance --port=%d" % api_port
        _index_cmd = "%s index -f" % (_base_cmd,)

        # 2. Check name filter
        cmd = "name=Name2"
        exitcode, out, err = execute("%s %s" % (_index_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(1, len(image_lines))
        self.assertTrue(image_lines[0].startswith('2'))

        # 3. Check disk_format filter
        cmd = "disk_format=vhd"
        exitcode, out, err = execute("%s %s" % (_index_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(2, len(image_lines))
        self.assertTrue(image_lines[0].startswith('3'))
        self.assertTrue(image_lines[1].startswith('1'))

        # 4. Check container_format filter
        cmd = "container_format=ami"
        exitcode, out, err = execute("%s %s" % (_index_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(1, len(image_lines))
        self.assertTrue(image_lines[0].startswith('2'))

        # 5. Check container_format filter
        cmd = "container_format=ami"
        exitcode, out, err = execute("%s %s" % (_index_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(1, len(image_lines))
        self.assertTrue(image_lines[0].startswith('2'))

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
        self.assertTrue(image_lines[0].startswith('2'))
        self.assertTrue(image_lines[1].startswith('1'))

        # 8. Check multiple filters
        cmd = "name=Name2 foo=bar"
        exitcode, out, err = execute("%s %s" % (_index_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(1, len(image_lines))
        self.assertTrue(image_lines[0].startswith('2'))

        # 9. Ensure details call also respects filters
        _details_cmd = "%s details" % (_base_cmd,)
        cmd = "foo=bar"
        exitcode, out, err = execute("%s %s" % (_details_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[1:-1]
        self.assertEqual(20, len(image_lines))
        self.assertTrue(image_lines[1].startswith('Id: 2'))
        self.assertTrue(image_lines[11].startswith('Id: 1'))

        self.stop_servers()

    def test_results_pagination(self):
        self.cleanup()
        self.start_servers()

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

        for i, args in enumerate(_add_args):
            cmd = "%s %s" % (_add_cmd, args)
            exitcode, out, err = execute(cmd)
            self.assertEqual(0, exitcode)
            expected_out = 'Added new image with ID: %d' % (i + 1,)
            self.assertEqual(expected_out, out.strip())

        # 2. Limit less than total
        cmd = "--limit=3"
        exitcode, out, err = execute("%s %s" % (index_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(5, len(image_lines))
        self.assertTrue(image_lines[0].startswith('5'))
        self.assertTrue(image_lines[1].startswith('4'))
        self.assertTrue(image_lines[2].startswith('3'))
        self.assertTrue(image_lines[3].startswith('2'))
        self.assertTrue(image_lines[4].startswith('1'))

        # 3. With a marker
        cmd = "--marker=4"
        exitcode, out, err = execute("%s %s" % (index_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(3, len(image_lines))
        self.assertTrue(image_lines[0].startswith('3'))
        self.assertTrue(image_lines[1].startswith('2'))
        self.assertTrue(image_lines[2].startswith('1'))

        # 3. With a marker and limit
        cmd = "--marker=3 --limit=1"
        exitcode, out, err = execute("%s %s" % (index_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(2, len(image_lines))
        self.assertTrue(image_lines[0].startswith('2'))
        self.assertTrue(image_lines[1].startswith('1'))

        # 4. Pagination params with filtered results
        cmd = "--marker=4 --limit=1 container_format=ami"
        exitcode, out, err = execute("%s %s" % (index_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(2, len(image_lines))
        self.assertTrue(image_lines[0].startswith('3'))
        self.assertTrue(image_lines[1].startswith('1'))

        # 5. Pagination params with filtered results in a details call
        cmd = "--marker=4 --limit=1 container_format=ami"
        exitcode, out, err = execute("%s %s" % (details_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[1:-1]
        self.assertEqual(18, len(image_lines))
        self.assertTrue(image_lines[1].startswith('Id: 3'))
        self.assertTrue(image_lines[10].startswith('Id: 1'))

    def test_results_sorting(self):
        self.cleanup()
        self.start_servers()

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

        for i, args in enumerate(_add_args):
            cmd = "%s %s" % (_add_cmd, args)
            exitcode, out, err = execute(cmd)
            self.assertEqual(0, exitcode)
            expected_out = 'Added new image with ID: %d' % (i + 1,)
            self.assertEqual(expected_out, out.strip())

        # 2. Sort by name asc
        cmd = "--sort_key=name --sort_dir=asc"
        exitcode, out, err = execute("%s %s" % (index_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(5, len(image_lines))
        self.assertTrue(image_lines[0].startswith('1'))
        self.assertTrue(image_lines[1].startswith('4'))
        self.assertTrue(image_lines[2].startswith('3'))
        self.assertTrue(image_lines[3].startswith('2'))
        self.assertTrue(image_lines[4].startswith('5'))

        # 3. Sort by name asc with a marker
        cmd = "--sort_key=name --sort_dir=asc --marker=4"
        exitcode, out, err = execute("%s %s" % (index_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(3, len(image_lines))
        self.assertTrue(image_lines[0].startswith('3'))
        self.assertTrue(image_lines[1].startswith('2'))
        self.assertTrue(image_lines[2].startswith('5'))

        # 4. Sort by container_format desc
        cmd = "--sort_key=container_format --sort_dir=desc"
        exitcode, out, err = execute("%s %s" % (index_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[2:-1]
        self.assertEqual(5, len(image_lines))
        self.assertTrue(image_lines[0].startswith('5'))
        self.assertTrue(image_lines[1].startswith('2'))
        self.assertTrue(image_lines[2].startswith('4'))
        self.assertTrue(image_lines[3].startswith('3'))
        self.assertTrue(image_lines[4].startswith('1'))

        # 5. Sort by name asc with a marker (details)
        cmd = "--sort_key=name --sort_dir=asc --marker=4"
        exitcode, out, err = execute("%s %s" % (details_cmd, cmd))

        self.assertEqual(0, exitcode)
        image_lines = out.split("\n")[1:-1]
        self.assertEqual(27, len(image_lines))
        self.assertTrue(image_lines[1].startswith('Id: 3'))
        self.assertTrue(image_lines[10].startswith('Id: 2'))
        self.assertTrue(image_lines[19].startswith('Id: 5'))
