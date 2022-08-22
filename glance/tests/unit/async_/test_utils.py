# Copyright 2022 OVHcloud
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


from unittest import mock

from glance.async_ import utils
import glance.common.exception
from glance.tests.unit import base


class TestGetGlanceEndpoint(base.IsolatedUnitTest):

    def setUp(self):
        super(TestGetGlanceEndpoint, self).setUp()

        self.service_catalog = [
            {
                'endpoints': [
                    {
                        'adminURL': 'http://localhost:8080/',
                        'region': 'RegionOne',
                        'internalURL': 'http://internalURL/',
                        'publicURL': 'http://publicURL/',
                    },
                ],
                'type': 'object-store',
            },
            {
                'endpoints': [
                    {
                        'adminURL': 'http://localhost:8080/',
                        'region': 'RegionOne',
                        'internalURL': 'http://RegionOneInternal/',
                        'publicURL': 'http://RegionOnePublic/',
                    },
                ],
                'type': 'image',
            },
            {
                'endpoints': [
                    {
                        'adminURL': 'http://localhost:8080/',
                        'region': 'RegionTwo',
                        'internalURL': 'http://RegionTwoInternal/',
                        'publicURL': 'http://RegionTwoPublic/',
                    },
                ],
                'type': 'image',
            }
        ]

        self.context = mock.MagicMock(service_catalog=self.service_catalog)

    def test_return_matching_glance_endpoint(self):
        self.assertEqual(utils.get_glance_endpoint(self.context,
                                                   'RegionOne',
                                                   'public'),
                         'http://RegionOnePublic/')
        self.assertEqual(utils.get_glance_endpoint(self.context,
                                                   'RegionTwo',
                                                   'internal'),
                         'http://RegionTwoInternal/')

    def test_glance_endpoint_not_found(self):
        self.assertRaises(glance.common.exception.GlanceEndpointNotFound,
                          utils.get_glance_endpoint, self.context,
                          'RegionThree', 'public')
