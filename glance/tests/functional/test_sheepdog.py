# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 Nebula, Inc
# All Rights Reserved.

"""
Tests a Glance API server which uses a Sheepdog backend by default

This test has requires a Sheepdog cluster.
"""

import ConfigParser
import os

from glance.tests.functional import test_api


class TestSheepdog(test_api.TestApi):

    """Functional tests for the Sheepdog backend"""

    TEST_SHEEPDOG = os.environ.get('GLANCE_TEST_SHEEPDOG')

    def __init__(self, *args, **kwargs):
        super(TestSheepdog, self).__init__(*args, **kwargs)

        self.disabled = True
        if not self.TEST_SHEEPDOG:
            self.disabled_message = "GLANCE_TEST_SHEEPDOG environ not set."
            return

        self.default_store = 'sheepdog'
        self.disabled = False

    def setUp(self):
        if self.disabled:
            return
        super(TestSheepdog, self).setUp()

    def tearDown(self):
        if self.disabled:
            return
        super(TestSheepdog, self).tearDown()
