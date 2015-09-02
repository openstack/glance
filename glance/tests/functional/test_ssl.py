# Copyright 2015 OpenStack Foundation
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

import httplib2

from glance.tests import functional

TEST_VAR_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                            '..', 'var'))


class TestSSL(functional.FunctionalTest):

    """Functional tests verifying SSL communication"""

    def setUp(self):
        super(TestSSL, self).setUp()

        if getattr(self, 'inited', False):
            return

        self.inited = False
        self.disabled = True

        # NOTE (stevelle): Test key/cert/CA file created as per:
        #   http://nrocco.github.io/2013/01/25/
        #       self-signed-ssl-certificate-chains.html
        # For these tests certificate.crt must be created with 'Common Name'
        # set to 127.0.0.1

        self.key_file = os.path.join(TEST_VAR_DIR, 'privatekey.key')
        if not os.path.exists(self.key_file):
            self.disabled_message = ("Could not find private key file %s" %
                                     self.key_file)
            self.inited = True
            return

        self.cert_file = os.path.join(TEST_VAR_DIR, 'certificate.crt')
        if not os.path.exists(self.cert_file):
            self.disabled_message = ("Could not find certificate file %s" %
                                     self.cert_file)
            self.inited = True
            return

        self.ca_file = os.path.join(TEST_VAR_DIR, 'ca.crt')
        if not os.path.exists(self.ca_file):
            self.disabled_message = ("Could not find CA file %s" %
                                     self.ca_file)
            self.inited = True
            return

        self.inited = True
        self.disabled = False

    def tearDown(self):
        super(TestSSL, self).tearDown()
        if getattr(self, 'inited', False):
            return

    def test_ssl_ok(self):
        """Make sure the public API works with HTTPS."""
        self.cleanup()
        self.start_servers(**self.__dict__.copy())

        path = "https://%s:%d/versions" % ("127.0.0.1", self.api_port)
        https = httplib2.Http(ca_certs=self.ca_file)
        response, content = https.request(path, 'GET')
        self.assertEqual(200, response.status)
