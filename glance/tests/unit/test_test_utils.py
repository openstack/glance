# Copyright 2020 Red Hat, Inc
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

from glance.tests import utils as test_utils


class TestFakeData(test_utils.BaseTestCase):
    def test_via_read(self):
        fd = test_utils.FakeData(1024)
        data = []
        for i in range(0, 1025, 256):
            chunk = fd.read(256)
            data.append(chunk)
            if not chunk:
                break

        self.assertEqual(5, len(data))
        # Make sure we got a zero-length final read
        self.assertEqual(b'', data[-1])
        # Make sure we only got 1024 bytes
        self.assertEqual(1024, len(b''.join(data)))

    def test_via_iter(self):
        data = b''.join(list(test_utils.FakeData(1024)))
        self.assertEqual(1024, len(data))
