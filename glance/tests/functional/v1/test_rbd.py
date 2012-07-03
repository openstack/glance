# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 Josh Durgin
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
Tests a Glance API server which uses an RBD backend by default

This test has requires a Ceph cluster, optionally with
authentication. It looks in a file specified in the
GLANCE_TEST_RBD_CONF environment variable for RBD store settings.
For more details, see doc/source/configuring.rst.

For Ceph installation instructions, see:
http://ceph.newdream.net/docs/latest/ops/install/
or, if you want to compile a development version:
http://ceph.newdream.net/wiki/Simple_test_setup

Note this test creates and deletes the pool specified in the
configuration file, so it should not exist prior to running the test.

If a connection cannot be established, or the rados library is not
found, or creating the pool fails, all the test cases are skipped.
"""

import ConfigParser
import os

from glance.store.rbd import DEFAULT_POOL, DEFAULT_CONFFILE, DEFAULT_USER
from glance.tests.functional.v1 import test_api


class TestRBD(test_api.TestApi):

    """Functional tests for the RBD backend"""

    CONFIG_FILE_PATH = os.environ.get('GLANCE_TEST_RBD_CONF')

    def __init__(self, *args, **kwargs):
        super(TestRBD, self).__init__(*args, **kwargs)
        self.disabled = True
        if not self.CONFIG_FILE_PATH:
            self.disabled_message = "GLANCE_TEST_RBD_CONF environ not set."
            return

        # use the default configuration if none is specified
        self.rbd_store_ceph_conf = DEFAULT_CONFFILE
        self.rbd_store_user = DEFAULT_USER
        self.rbd_store_pool = DEFAULT_POOL

        if os.path.exists(TestRBD.CONFIG_FILE_PATH):
            cp = ConfigParser.RawConfigParser()
            try:
                cp.read(TestRBD.CONFIG_FILE_PATH)
                defaults = cp.defaults()
                for key, value in defaults.items():
                    self.__dict__[key] = value
            except ConfigParser.ParsingError, e:
                self.disabled_message = ("Failed to read test_rbd config "
                                         "file. Got error: %s" % e)
                return
        try:
            import rados
        except ImportError:
            self.disabled_message = "rados python library not found"
            return

        cluster = rados.Rados(conffile=self.rbd_store_ceph_conf,
                              rados_id=self.rbd_store_user)
        try:
            cluster.connect()
        except rados.Error, e:
            self.disabled_message = ("Failed to connect to RADOS: %s" % e)
            return
        cluster.shutdown()

        self.default_store = 'rbd'
        self.disabled = False

    def setUp(self):
        if self.disabled:
            return
        super(TestRBD, self).setUp()
        import rados
        try:
            self.create_pool()
        except rados.Error, e:
            self.disabled_message = ("Failed to create pool: %s" % e)
            self.disabled = True
            return

    def tearDown(self):
        if self.disabled:
            return
        self.delete_pool()
        super(TestRBD, self).tearDown()

    def create_pool(self):
        from rados import Rados
        with Rados(conffile=self.rbd_store_ceph_conf,
                   rados_id=self.rbd_store_user) as cluster:
            cluster.create_pool(self.rbd_store_pool)

    def delete_pool(self):
        from rados import Rados
        with Rados(conffile=self.rbd_store_ceph_conf,
                   rados_id=self.rbd_store_user) as cluster:
            cluster.delete_pool(self.rbd_store_pool)
