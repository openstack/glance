# Copyright 2015 Intel Corporation
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

import os.path
import shutil
import tarfile
import tempfile
from unittest import mock

try:
    from defusedxml.cElementTree import ParseError
except ImportError:
    from defusedxml.ElementTree import ParseError

from glance.async_.flows import ovf_process
import glance.tests.utils as test_utils
from oslo_config import cfg


class TestOvfProcessTask(test_utils.BaseTestCase):

    def setUp(self):
        super(TestOvfProcessTask, self).setUp()
        # The glance/tests/var dir containing sample ova packages used
        # by the tests in this class
        self.test_ova_dir = os.path.abspath(os.path.join(
                                            os.path.dirname(__file__),
                                            '../../../', 'var'))
        self.tempdir = tempfile.mkdtemp()
        self.config(work_dir=self.tempdir, group="task")

        # These are the properties that we will extract from the ovf
        # file contained in a ova package
        interested_properties = (
            '{\n'
            '   "cim_pasd":  [\n'
            '      "InstructionSetExtensionName",\n'
            '      "ProcessorArchitecture"]\n'
            '}\n')
        self.config_file_name = os.path.join(self.tempdir, 'ovf-metadata.json')
        with open(self.config_file_name, 'w') as config_file:
            config_file.write(interested_properties)

        self.image = mock.Mock()
        self.image.container_format = 'ova'
        self.image.context.is_admin = True

        self.img_repo = mock.Mock()
        self.img_repo.get.return_value = self.image

    def tearDown(self):
        if os.path.exists(self.tempdir):
            shutil.rmtree(self.tempdir)

        super(TestOvfProcessTask, self).tearDown()

    def _copy_ova_to_tmpdir(self, ova_name):
        # Copies an ova package to the tempdir from which
        # it will be read by the system-under-test
        shutil.copy(os.path.join(self.test_ova_dir, ova_name), self.tempdir)
        return os.path.join(self.tempdir, ova_name)

    @mock.patch.object(cfg.ConfigOpts, 'find_file')
    def test_ovf_process_success(self, mock_find_file):
        mock_find_file.return_value = self.config_file_name

        ova_file_path = self._copy_ova_to_tmpdir('testserver.ova')
        ova_uri = 'file://' + ova_file_path

        oprocess = ovf_process._OVF_Process('task_id', 'ovf_proc',
                                            self.img_repo)
        self.assertEqual(ova_uri, oprocess.execute('test_image_id', ova_uri))

        # Note that the extracted disk image is overwritten onto the input ova
        # file
        with open(ova_file_path, 'rb') as disk_image_file:
            content = disk_image_file.read()
        # b'ABCD' is the exact contents of the disk image file
        # testserver-disk1.vmdk contained in the testserver.ova package used
        # by this test
        self.assertEqual(b'ABCD', content)
        # 'DMTF:x86:VT-d' is the value in the testerver.ovf file in the
        # testserver.ova package
        self.image.extra_properties.update.assert_called_once_with(
            {'cim_pasd_InstructionSetExtensionName': 'DMTF:x86:VT-d'})
        self.assertEqual('bare', self.image.container_format)

    @mock.patch.object(cfg.ConfigOpts, 'find_file')
    def test_ovf_process_no_config_file(self, mock_find_file):
        # Mimics a Glance deployment without the ovf-metadata.json file
        mock_find_file.return_value = None

        ova_file_path = self._copy_ova_to_tmpdir('testserver.ova')
        ova_uri = 'file://' + ova_file_path

        oprocess = ovf_process._OVF_Process('task_id', 'ovf_proc',
                                            self.img_repo)
        self.assertEqual(ova_uri, oprocess.execute('test_image_id', ova_uri))

        # Note that the extracted disk image is overwritten onto the input
        # ova file.
        with open(ova_file_path, 'rb') as disk_image_file:
            content = disk_image_file.read()
        # b'ABCD' is the exact contents of the disk image file
        # testserver-disk1.vmdk contained in the testserver.ova package used
        # by this test
        self.assertEqual(b'ABCD', content)
        # No properties must be selected from the ovf file
        self.image.extra_properties.update.assert_called_once_with({})
        self.assertEqual('bare', self.image.container_format)

    @mock.patch.object(cfg.ConfigOpts, 'find_file')
    def test_ovf_process_not_admin(self, mock_find_file):
        mock_find_file.return_value = self.config_file_name

        ova_file_path = self._copy_ova_to_tmpdir('testserver.ova')
        ova_uri = 'file://' + ova_file_path

        self.image.context.is_admin = False

        oprocess = ovf_process._OVF_Process('task_id', 'ovf_proc',
                                            self.img_repo)
        self.assertRaises(RuntimeError, oprocess.execute, 'test_image_id',
                          ova_uri)

    def test_extract_ova_not_tar(self):
        # testserver-not-tar.ova package is not in tar format
        ova_file_path = os.path.join(self.test_ova_dir,
                                     'testserver-not-tar.ova')
        iextractor = ovf_process.OVAImageExtractor()
        with open(ova_file_path, 'rb') as ova_file:
            self.assertRaises(tarfile.ReadError, iextractor.extract, ova_file)

    def test_extract_ova_no_disk(self):
        # testserver-no-disk.ova package contains no disk image file
        ova_file_path = os.path.join(self.test_ova_dir,
                                     'testserver-no-disk.ova')
        iextractor = ovf_process.OVAImageExtractor()
        with open(ova_file_path, 'rb') as ova_file:
            self.assertRaises(KeyError, iextractor.extract, ova_file)

    def test_extract_ova_no_ovf(self):
        # testserver-no-ovf.ova package contains no ovf file
        ova_file_path = os.path.join(self.test_ova_dir,
                                     'testserver-no-ovf.ova')
        iextractor = ovf_process.OVAImageExtractor()
        with open(ova_file_path, 'rb') as ova_file:
            self.assertRaises(RuntimeError, iextractor.extract, ova_file)

    def test_extract_ova_bad_ovf(self):
        # testserver-bad-ovf.ova package has an ovf file that contains
        # invalid xml
        ova_file_path = os.path.join(self.test_ova_dir,
                                     'testserver-bad-ovf.ova')
        iextractor = ovf_process.OVAImageExtractor()
        with open(ova_file_path, 'rb') as ova_file:
            self.assertRaises(ParseError, iextractor._parse_OVF, ova_file)
