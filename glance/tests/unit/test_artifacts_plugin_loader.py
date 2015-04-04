# Copyright (c) 2015 Mirantis, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import os

import mock
import pkg_resources

from glance.common.artifacts import loader
from glance.common import exception
from glance.contrib.plugins.artifacts_sample.v1 import artifact as art1
from glance.contrib.plugins.artifacts_sample.v2 import artifact as art2
from glance.tests import utils


class MyArtifactDuplicate(art1.MyArtifact):
    __type_version__ = '1.0.1'
    __type_name__ = 'MyArtifact'


class MyArtifactOk(art1.MyArtifact):
    __type_version__ = '1.0.2'
    __type_name__ = 'MyArtifact'


class TestArtifactsLoader(utils.BaseTestCase):
    def setUp(self):
        self.path = 'glance.contrib.plugins.artifacts_sample'
        self._setup_loader(['MyArtifact=%s.v1.artifact:MyArtifact' %
                            self.path])
        super(TestArtifactsLoader, self).setUp()

    def _setup_loader(self, artifacts):
        self.loader = None
        mock_this = 'stevedore.extension.ExtensionManager._find_entry_points'
        with mock.patch(mock_this) as fep:
            fep.return_value = [
                pkg_resources.EntryPoint.parse(art) for art in artifacts]
            self.loader = loader.ArtifactsPluginLoader(
                'glance.artifacts.types')

    def test_load(self):
        """
        Plugins can be loaded as entrypoint=sigle plugin and
        entrypoint=[a, list, of, plugins]
        """
        # single version
        self.assertEqual(1, len(self.loader.mgr.extensions))
        self.assertEqual(art1.MyArtifact,
                         self.loader.get_class_by_endpoint('myartifact'))
        # entrypoint = [a, list]
        path = os.path.splitext(__file__)[0][__file__.rfind(
            'glance'):].replace('/', '.')
        self._setup_loader([
            'MyArtifact=%s:MyArtifactOk' % path,
            'MyArtifact=%s.v2.artifact:MyArtifact' % self.path,
            'MyArtifact=%s.v1.artifact:MyArtifact' % self.path]),
        self.assertEqual(3, len(self.loader.mgr.extensions))
        # returns the plugin with the latest version
        self.assertEqual(art2.MyArtifact,
                         self.loader.get_class_by_endpoint('myartifact'))
        self.assertEqual(art1.MyArtifact,
                         self.loader.get_class_by_endpoint('myartifact',
                                                           '1.0.1'))

    def test_basic_loader_func(self):
        """Test public methods of PluginLoader class here"""
        # type_version 2 == 2.0 == 2.0.0
        self._setup_loader(
            ['MyArtifact=%s.v2.artifact:MyArtifact' % self.path])
        self.assertEqual(art2.MyArtifact,
                         self.loader.get_class_by_endpoint('myartifact'))
        self.assertEqual(art2.MyArtifact,
                         self.loader.get_class_by_endpoint('myartifact',
                                                           '2.0'))
        self.assertEqual(art2.MyArtifact,
                         self.loader.get_class_by_endpoint('myartifact',
                                                           '2.0.0'))
        self.assertEqual(art2.MyArtifact,
                         self.loader.get_class_by_endpoint('myartifact',
                                                           '2'))
        # now make sure that get_class_by_typename works as well
        self.assertEqual(art2.MyArtifact,
                         self.loader.get_class_by_typename('MyArtifact'))
        self.assertEqual(art2.MyArtifact,
                         self.loader.get_class_by_typename('MyArtifact', '2'))

    def test_config_validation(self):
        """
        Plugins can be loaded on certain conditions:
            * entry point name == type_name
            * no plugin with the same type_name and version has been already
              loaded
        """
        path = 'glance.contrib.plugins.artifacts_sample'
        # here artifacts specific validation is checked
        self.assertRaises(exception.ArtifactNonMatchingTypeName,
                          self._setup_loader,
                          ['non_matching_name=%s.v1.artifact:MyArtifact' %
                           path])
        # make sure this call is ok
        self._setup_loader(['MyArtifact=%s.v1.artifact:MyArtifact' % path])
        art_type = self.loader.get_class_by_endpoint('myartifact')
        self.assertEqual('MyArtifact', art_type.metadata.type_name)
        self.assertEqual('1.0.1', art_type.metadata.type_version)
        # now try to add duplicate artifact with the same type_name and
        # type_version as already exists
        bad_art_path = os.path.splitext(__file__)[0][__file__.rfind(
            'glance'):].replace('/', '.')
        self.assertEqual(art_type.metadata.type_version,
                         MyArtifactDuplicate.metadata.type_version)
        self.assertEqual(art_type.metadata.type_name,
                         MyArtifactDuplicate.metadata.type_name)
        # should raise an exception as (name, version) is not unique
        self.assertRaises(
            exception.ArtifactDuplicateNameTypeVersion, self._setup_loader,
            ['MyArtifact=%s.v1.artifact:MyArtifact' % path,
             'MyArtifact=%s:MyArtifactDuplicate' % bad_art_path])
        # two artifacts with the same name but different versions coexist fine
        self.assertEqual('MyArtifact', MyArtifactOk.metadata.type_name)
        self.assertNotEqual(art_type.metadata.type_version,
                            MyArtifactOk.metadata.type_version)
        self._setup_loader(['MyArtifact=%s.v1.artifact:MyArtifact' % path,
                            'MyArtifact=%s:MyArtifactOk' % bad_art_path])

    def test_check_function(self):
        """
        A test to show that plugin-load specific options in artifacts.conf
        are correctly processed:
            * no plugins can be loaded if load_enabled = False
            * if available_plugins list is given only plugins specified can be
              be loaded
        """
        self.config(load_enabled=False)
        self.assertRaises(exception.ArtifactLoadError,
                          self._setup_loader,
                          ['MyArtifact=%s.v1.artifact:MyArtifact' % self.path])
        self.config(load_enabled=True, available_plugins=['MyArtifact-1.0.2'])
        self.assertRaises(exception.ArtifactLoadError,
                          self._setup_loader,
                          ['MyArtifact=%s.v1.artifact:MyArtifact' % self.path])
        path = os.path.splitext(__file__)[0][__file__.rfind(
            'glance'):].replace('/', '.')
        self._setup_loader(['MyArtifact=%s:MyArtifactOk' % path])
        # make sure that plugin_map has the expected plugin
        self.assertEqual(MyArtifactOk,
                         self.loader.get_class_by_endpoint('myartifact',
                                                           '1.0.2'))
