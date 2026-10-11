# Copyright 2010-2011 OpenStack Foundation
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

from glance.common import utils
from glance.tests import utils as test_utils


class UtilsTestCase(test_utils.BaseTestCase):

    def test_empty_metadata_headers(self):
        """Ensure unset metadata is not encoded in HTTP headers"""

        metadata = {
            'foo': 'bar',
            'snafu': None,
            'bells': 'whistles',
            'unset': None,
            'empty': '',
            'properties': {
                'distro': '',
                'arch': None,
                'user': 'nobody',
            },
        }

        headers = utils.image_meta_to_http_headers(metadata)

        self.assertNotIn('x-image-meta-snafu', headers)
        self.assertNotIn('x-image-meta-uset', headers)
        self.assertNotIn('x-image-meta-snafu', headers)
        self.assertNotIn('x-image-meta-property-arch', headers)

        self.assertEqual('bar', headers.get('x-image-meta-foo'))
        self.assertEqual('whistles', headers.get('x-image-meta-bells'))
        self.assertEqual('', headers.get('x-image-meta-empty'))
        self.assertEqual('', headers.get('x-image-meta-property-distro'))
        self.assertEqual('nobody', headers.get('x-image-meta-property-user'))
