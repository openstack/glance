# Copyright 2026 Red Hat, Inc
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

import os
import subprocess
import sys
import tempfile

import glance.tests.utils as test_utils


class TestFormatInspectorTool(test_utils.BaseTestCase):

    def test_raw_file(self):
        tool_path = os.path.join(
            os.path.dirname(__file__), '..', '..', '..', '..',
            'tools', 'test_format_inspector.py')

        with tempfile.NamedTemporaryFile() as image:
            image.write(b'0' * 1024)
            image.flush()
            result = subprocess.run(
                [sys.executable, os.path.abspath(tool_path),
                 '-f', 'raw', '-i', image.name],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        self.assertEqual(0, result.returncode)

    def test_format_mismatch(self):
        tool_path = os.path.join(
            os.path.dirname(__file__), '..', '..', '..', '..',
            'tools', 'test_format_inspector.py')

        with tempfile.NamedTemporaryFile() as image:
            image.write(b'0' * 1024)
            image.flush()
            result = subprocess.run([
                sys.executable, os.path.abspath(tool_path),
                '-f', 'qcow2', '-i', image.name
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        self.assertIn(
            b'*** Format inspector did not detect file as qcow2',
            result.stdout)
