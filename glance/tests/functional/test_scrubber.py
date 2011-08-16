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

import os
import time
import unittest

from glance.tests import functional
from glance.tests.utils import execute

from glance import client
from glance.registry import client as registry_client


TEST_IMAGE_DATA = '*' * 5 * 1024
TEST_IMAGE_META = {'name': 'test_image',
                  'is_public': False,
                  'disk_format': 'raw',
                  'container_format': 'ovf'}


class TestScrubber(functional.FunctionalTest):

    """Test that delayed_delete works and the scrubber deletes"""

    def _get_client(self):
        return client.Client("localhost", self.api_port)

    def _get_registry_client(self):
        return registry_client.RegistryClient('localhost',
                                              self.registry_port)

    def test_immediate_delete(self):
        """
        test that images get deleted immediately by default
        """

        self.cleanup()
        self.start_servers()

        client = self._get_client()
        registry = self._get_registry_client()
        meta = client.add_image(TEST_IMAGE_META, TEST_IMAGE_DATA)
        id = meta['id']

        filters = {'deleted': True, 'is_public': 'none',
                   'status': 'pending_delete'}
        recs = registry.get_images_detailed(filters=filters)
        self.assertFalse(recs)

        client.delete_image(id)
        recs = registry.get_images_detailed(filters=filters)
        self.assertFalse(recs)

        filters = {'deleted': True, 'is_public': 'none', 'status': 'deleted'}
        recs = registry.get_images_detailed(filters=filters)
        self.assertTrue(recs)
        for rec in recs:
            self.assertEqual(rec['status'], 'deleted')

        self.stop_servers()

    def test_delayed_delete(self):
        """
        test that images don't get deleted immediatly and that the scrubber
        scrubs them
        """

        self.cleanup()
        self.start_servers(delayed_delete=True, daemon=True)

        client = self._get_client()
        registry = self._get_registry_client()
        meta = client.add_image(TEST_IMAGE_META, TEST_IMAGE_DATA)
        id = meta['id']

        filters = {'deleted': True, 'is_public': 'none',
                   'status': 'pending_delete'}
        recs = registry.get_images_detailed(filters=filters)
        self.assertFalse(recs)

        client.delete_image(id)
        recs = registry.get_images_detailed(filters=filters)
        self.assertTrue(recs)

        filters = {'deleted': True, 'is_public': 'none'}
        recs = registry.get_images_detailed(filters=filters)
        self.assertTrue(recs)
        for rec in recs:
            self.assertEqual(rec['status'], 'pending_delete')

        # NOTE(jkoelker) The build servers sometimes take longer than
        #                15 seconds to scrub. Give it up to 5 min, checking
        #                checking every 15 seconds. When/if it flips to
        #                deleted, bail immediatly.
        deleted = set()
        recs = []
        for _ in xrange(3):
            time.sleep(5)

            recs = registry.get_images_detailed(filters=filters)
            self.assertTrue(recs)

            # NOTE(jkoelker) Reset the deleted set for this loop
            deleted = set()
            for rec in recs:
                deleted.add(rec['status'] == 'deleted')

            if False not in deleted:
                break

        self.assertTrue(recs)
        for rec in recs:
            self.assertEqual(rec['status'], 'deleted')

        self.stop_servers()
