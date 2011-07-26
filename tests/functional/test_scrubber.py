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

from sqlalchemy import create_engine

from tests import functional
from tests.utils import execute

from glance import client


TEST_IMAGE_DATA = '*' * 5 * 1024
TEST_IMAGE_META = {'name': 'test_image',
                  'is_public': False,
                  'disk_format': 'raw',
                  'container_format': 'ovf'}


class TestScrubber(functional.FunctionalTest):

    """Test that delayed_delete works and the scrubber deletes"""

    def _get_client(self):
        return client.Client("localhost", self.api_port)

    @functional.runs_sql
    def test_immediate_delete(self):
        """
        test that images get deleted immediately by default
        """

        self.cleanup()
        self.start_servers()

        client = self._get_client()
        meta = client.add_image(TEST_IMAGE_META, TEST_IMAGE_DATA)
        id = meta['id']

        sql = "SELECT * FROM images WHERE status = 'pending_delete'"
        recs = list(self.run_sql_cmd(sql))
        self.assertFalse(recs)

        client.delete_image(id)
        recs = list(self.run_sql_cmd(sql))
        self.assertFalse(recs)

        sql = "SELECT * FROM images WHERE id = '%s'" % id
        recs = list(self.run_sql_cmd(sql))
        self.assertTrue(recs)
        for rec in recs:
            self.assertEqual(rec['status'], 'deleted')

        self.stop_servers()

    @functional.runs_sql
    def test_delayed_delete(self):
        """
        test that images don't get deleted immediatly and that the scrubber
        scrubs them
        """

        self.cleanup()
        registry_db = self.registry_server.sql_connection
        self.start_servers(delayed_delete=True, sql_connection=registry_db,
                           daemon=True)

        client = self._get_client()
        meta = client.add_image(TEST_IMAGE_META, TEST_IMAGE_DATA)
        id = meta['id']

        sql = "SELECT * FROM images WHERE status = 'pending_delete'"
        recs = list(self.run_sql_cmd(sql))
        self.assertFalse(recs)

        client.delete_image(id)
        recs = self.run_sql_cmd(sql)
        self.assertTrue(recs)

        sql = "SELECT * FROM images WHERE id = '%s'" % id
        recs = list(self.run_sql_cmd(sql))
        self.assertTrue(recs)
        for rec in recs:
            self.assertEqual(rec['status'], 'pending_delete')

        # Wait 15 seconds for the scrubber to scrub
        time.sleep(15)

        recs = list(self.run_sql_cmd(sql))
        self.assertTrue(recs)
        for rec in recs:
            self.assertEqual(rec['status'], 'deleted')

        self.stop_servers()
