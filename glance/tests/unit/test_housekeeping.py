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

import os
from unittest import mock

import glance_store
from oslo_config import cfg
from oslo_utils.fixture import uuidsentinel as uuids

from glance.common import exception
from glance import context
from glance import housekeeping
import glance.tests.unit.utils as unit_test_utils
import glance.tests.utils as test_utils

CONF = cfg.CONF


class TestStagingStoreHousekeeping(test_utils.BaseTestCase):
    def _store_dir(self, store):
        return os.path.join(self.test_dir, store)

    def setUp(self):
        super(TestStagingStoreHousekeeping, self).setUp()

        self.config(enabled_backends={'store1': 'file'})
        glance_store.register_store_opts(
            CONF,
            reserved_stores={'os_glance_staging_store': 'file'})

        self.config(default_backend='store1',
                    group='glance_store')
        self.config(filesystem_store_datadir=self._store_dir('store1'),
                    group='store1')
        self.config(filesystem_store_datadir=self._store_dir('staging'),
                    group='os_glance_staging_store')

        glance_store.create_multi_stores(
            CONF,
            reserved_stores={'os_glance_staging_store': 'file'})

        self.db = unit_test_utils.FakeDB(initialize=False)
        self.cleaner = housekeeping.StagingStoreCleaner(self.db)
        self.context = context.get_admin_context()

    def test_get_staging_path(self):
        expected = os.path.join(self.test_dir, 'staging')
        self.assertEqual(expected, housekeeping.staging_store_path())

    def test_get_staging_path_single_store(self):
        self.config(enabled_backends={})
        expected = '/tmp/staging/'
        self.assertEqual(expected, housekeeping.staging_store_path())

    @mock.patch('glance.common.store_utils.get_dir_separator')
    def test_assert_staging_scheme(self, mock_get_dir_separator):
        # NOTE(danms): This cannot happen now, but since we need to be
        # opinionated about the fact that the URL is a file path, better
        # to check for it, in case it changes in the future.
        mock_get_dir_separator.return_value = ('/', 'http://foo')
        self.assertRaises(exception.GlanceException,
                          lambda: housekeeping.staging_store_path())

    def test_assert_staging_scheme_on_init(self):
        # NOTE(danms): Make this a single-store scenario, which will cover
        # our assertion about node_staging_uri while we test for the
        # assert-on-init behavior.
        self.config(enabled_backends={},
                    node_staging_uri='http://good.luck')
        self.assertRaises(exception.GlanceException,
                          housekeeping.staging_store_path)

    def test_get_image_id(self):
        self.assertEqual(uuids.some_random_uuid,
                         self.cleaner.get_image_id(uuids.some_random_uuid))
        self.assertEqual(uuids.some_random_uuid,
                         self.cleaner.get_image_id(
                             '%s.qcow2' % uuids.some_random_uuid))
        self.assertEqual(uuids.some_random_uuid,
                         self.cleaner.get_image_id(
                             '%s.uc' % uuids.some_random_uuid))
        self.assertEqual(uuids.some_random_uuid,
                         self.cleaner.get_image_id(
                             '%s.blah' % uuids.some_random_uuid))

        self.assertIsNone(self.cleaner.get_image_id('foo'))
        self.assertIsNone(self.cleaner.get_image_id('foo.bar'))

    def test_is_valid_image(self):
        image = self.db.image_create(self.context, {'status': 'queued'})
        self.assertTrue(self.cleaner.is_valid_image(image['id']))
        self.assertFalse(self.cleaner.is_valid_image('foo'))

    def test_is_valid_image_deleted(self):
        image = self.db.image_create(self.context, {'status': 'queued'})
        self.db.image_destroy(self.context, image['id'])
        self.assertFalse(self.cleaner.is_valid_image(image['id']))

    @mock.patch('os.remove')
    def test_delete_file(self, mock_remove):
        self.assertTrue(self.cleaner.delete_file('foo'))
        os.remove.assert_called_once_with('foo')

    @mock.patch('os.remove')
    @mock.patch.object(housekeeping, 'LOG')
    def test_delete_file_not_found(self, mock_LOG, mock_remove):
        os.remove.side_effect = FileNotFoundError('foo is gone')
        # We should ignore a file-not-found error
        self.assertTrue(self.cleaner.delete_file('foo'))
        os.remove.assert_called_once_with('foo')
        mock_LOG.error.assert_not_called()

    @mock.patch('os.remove')
    @mock.patch.object(housekeeping, 'LOG')
    def test_delete_file_failed(self, mock_LOG, mock_remove):
        # Any other error should report failure and log
        os.remove.side_effect = Exception('insufficient plutonium')
        self.assertFalse(self.cleaner.delete_file('foo'))
        os.remove.assert_called_once_with('foo')
        mock_LOG.error.assert_called_once_with(
            'Failed to delete stale staging path %(path)r: %(err)s',
            {'path': 'foo', 'err': 'insufficient plutonium'})

    @mock.patch('os.listdir')
    @mock.patch('os.remove')
    @mock.patch.object(housekeeping, 'LOG')
    def test_clean_orphaned_staging_residue_empty(self, mock_LOG, mock_remove,
                                                  mock_listdir):
        mock_listdir.return_value = []
        self.cleaner.clean_orphaned_staging_residue()
        mock_listdir.assert_called_once_with(housekeeping.staging_store_path())
        mock_remove.assert_not_called()
        mock_LOG.assert_not_called()

    @mock.patch('os.remove')
    @mock.patch('os.listdir')
    @mock.patch.object(housekeeping, 'LOG')
    def test_clean_orphaned_staging_residue(self, mock_LOG, mock_listdir,
                                            mock_remove):
        staging = housekeeping.staging_store_path()

        image = self.db.image_create(self.context, {'status': 'queued'})

        mock_listdir.return_value = ['notanimageid', image['id'], uuids.stale,
                                     uuids.midconvert,
                                     '%s.qcow2' % uuids.midconvert]
        self.cleaner.clean_orphaned_staging_residue()

        # NOTE(danms): We should have deleted the stale image file
        expected_stale = os.path.join(staging, uuids.stale)

        # NOTE(danms): We should have deleted the mid-convert base image and
        # the target file
        expected_mc = os.path.join(staging, uuids.midconvert)
        expected_mc_target = os.path.join(staging,
                                          '%s.qcow2' % uuids.midconvert)

        mock_remove.assert_has_calls([
            mock.call(expected_stale),
            mock.call(expected_mc),
            mock.call(expected_mc_target),
        ])

        # NOTE(danms): We should have cleaned the one (which we os.remove()'d)
        # above, and ignore the invalid and active ones. No errors this time.
        mock_LOG.debug.assert_has_calls([
            mock.call('Found %i files in staging directory for potential '
                      'cleanup', 5),
            mock.call('Staging directory contains unexpected non-image file '
                      '%r; ignoring',
                      'notanimageid'),
            mock.call('Stale staging residue found for image %(uuid)s: '
                      '%(file)r; deleting now.',
                      {'uuid': uuids.stale, 'file': expected_stale}),
            mock.call('Stale staging residue found for image %(uuid)s: '
                      '%(file)r; deleting now.',
                      {'uuid': uuids.midconvert, 'file': expected_mc}),
            mock.call('Stale staging residue found for image %(uuid)s: '
                      '%(file)r; deleting now.',
                      {'uuid': uuids.midconvert, 'file': expected_mc_target}),
            mock.call('Cleaned %(cleaned)i stale staging files, '
                      '%(ignored)i ignored (%(error)i errors)',
                      {'cleaned': 3, 'ignored': 2, 'error': 0}),
        ])

    @mock.patch('os.listdir')
    @mock.patch('os.remove')
    @mock.patch.object(housekeeping, 'LOG')
    def test_clean_orphaned_staging_residue_handles_errors(self, mock_LOG,
                                                           mock_remove,
                                                           mock_listdir):
        staging = housekeeping.staging_store_path()

        mock_listdir.return_value = [uuids.gone, uuids.error]
        mock_remove.side_effect = [FileNotFoundError('gone'),
                                   PermissionError('not yours')]
        self.cleaner.clean_orphaned_staging_residue()

        # NOTE(danms): We should only have logged an error for the
        # permission failure
        mock_LOG.error.assert_called_once_with(
            'Failed to delete stale staging path %(path)r: %(err)s',
            {'path': os.path.join(staging, uuids.error),
             'err': 'not yours'})

        # NOTE(danms): We should report the permission failure as an error,
        # but not the already-gone or invalid ones.
        mock_LOG.debug.assert_has_calls([
            mock.call('Found %i files in staging directory for potential '
                      'cleanup', 2),
            mock.call('Stale staging residue found for image %(uuid)s: '
                      '%(file)r; deleting now.',
                      {'uuid': uuids.gone,
                       'file': os.path.join(staging, uuids.gone)}),
            mock.call('Stale staging residue found for image %(uuid)s: '
                      '%(file)r; deleting now.',
                      {'uuid': uuids.error,
                       'file': os.path.join(staging, uuids.error)}),
            mock.call('Cleaned %(cleaned)i stale staging files, '
                      '%(ignored)i ignored (%(error)i errors)',
                      {'cleaned': 1, 'ignored': 0, 'error': 1}),
        ])
