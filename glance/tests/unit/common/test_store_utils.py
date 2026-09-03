# Copyright 2026 Red Hat, Inc.
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

from glance.common import store_utils
from glance.tests.unit import base as unit_base


class TestValidateExternalLocation(unit_base.StoreClearingUnitTest):

    def test_http_restricted_hosts_rejected(self):
        self.assertFalse(
            store_utils.validate_external_location('http://127.0.0.1/x'))
        self.assertFalse(
            store_utils.validate_external_location(
                'http://169.254.169.254/latest/meta-data/'))

    def test_http_restricted_hosts_allowed_when_whitelisted(self):
        self.config(allowed_hosts=['127.0.0.1'],
                    group='import_filtering_opts')
        self.config(allowed_ports=[80], group='import_filtering_opts')
        self.assertTrue(
            store_utils.validate_external_location('http://127.0.0.1:80/x'))

    def test_file_scheme_still_rejected(self):
        self.assertFalse(
            store_utils.validate_external_location('file:///etc/passwd'))
