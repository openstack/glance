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

"""
Tests a Glance API server which uses an Swift backend by default

This test requires that a real Swift account is available. It looks
in a file GLANCE_TEST_SWIFT_CONF environ variable for the credentials to
use.

Note that this test clears the entire container from the Swift account
for use by the test case, so make sure you supply credentials for
test accounts only.

If a connection cannot be established, all the test cases are
skipped.
"""

import ConfigParser
import json
import os
import tempfile
import unittest

from glance.tests.functional import test_api
from glance.tests.utils import execute, skip_if_disabled


class TestSwift(test_api.TestApi):

    """Functional tests for the Swift backend"""

    # Test machines can set the GLANCE_TEST_SWIFT_CONF variable
    # to override the location of the config file for migration testing
    CONFIG_FILE_PATH = os.environ.get('GLANCE_TEST_SWIFT_CONF')

    def setUp(self):
        """
        Test a connection to an Swift store using the credentials
        found in the environs or /tests/functional/test_swift.conf, if found.
        If the connection fails, mark all tests to skip.
        """
        self.inited = False
        self.disabled = True

        if self.inited:
            return

        if not self.CONFIG_FILE_PATH:
            self.disabled_message = "GLANCE_TEST_SWIFT_CONF environ not set."
            self.inited = True
            return

        if os.path.exists(TestSwift.CONFIG_FILE_PATH):
            cp = ConfigParser.RawConfigParser()
            try:
                cp.read(TestSwift.CONFIG_FILE_PATH)
                defaults = cp.defaults()
                for key, value in defaults.items():
                    self.__dict__[key] = value
            except ConfigParser.ParsingError, e:
                self.disabled_message = ("Failed to read test_swift.conf "
                                         "file. Got error: %s" % e)
                self.inited = True
                return

        from swift.common import client as swift_client

        try:
            swift_host = self.swift_store_auth_address
            if not swift_host.startswith('http'):
                swift_host = 'https://' + swift_host
            user = self.swift_store_user
            key = self.swift_store_key
            container_name = self.swift_store_container
        except AttributeError, e:
            self.disabled_message = ("Failed to find required configuration "
                                     "options for Swift store. "
                                     "Got error: %s" % e)
            self.inited = True
            return

        self.swift_conn = swift_conn = swift_client.Connection(
            authurl=swift_host, user=user, key=key, snet=False, retries=1)

        try:
            _resp_headers, containers = swift_conn.get_account()
        except Exception, e:
            self.disabled_message = ("Failed to get_account from Swift "
                                     "Got error: %s" % e)
            self.inited = True
            return

        try:
            for container in containers:
                if container == container_name:
                    swift_conn.delete_container(container)
        except swift_client.ClientException, e:
            self.disabled_message = ("Failed to delete container from Swift "
                                     "Got error: %s" % e)
            self.inited = True
            return

        self.swift_conn = swift_conn

        try:
            swift_conn.put_container(container_name)
        except swift_client.ClientException, e:
            self.disabled_message = ("Failed to create container. "
                                     "Got error: %s" % e)
            self.inited = True
            return

        self.disabled = False
        self.inited = True
        self.default_store = 'swift'

        super(TestSwift, self).setUp()

    def tearDown(self):
        if not self.disabled:
            self.clear_container()
        super(TestSwift, self).tearDown()

    def clear_container(self):
        self.swift_conn.delete_container(self.swift_store_container)
        self.swift_conn.put_container(self.swift_store_container)
