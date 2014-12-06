# Copyright 2010-2014 OpenStack Foundation
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

import subprocess

from glance.tests import utils as test_utils


script = """
import os
import sys
# Spoof module installed
sys.modules['%s'] = object
%s
os.environ['EVENTLET_NO_GREENDNS'] = '%s'
if 'eventlet' %s in sys.modules:
    sys.exit(2)
try:
    import glance.cmd
except ImportError:
    sys.exit(%d)
else:
    sys.exit(%d)
"""

eventlet_no_dns = script % ('fake', 'import eventlet', 'foo', 'not', 1, 0)

no_eventlet_no_dns = script % ('fake', '', 'foo', '', 1, 0)

no_eventlet_no_greendns = script % ('dns', '', 'yes', '', 1, 0)

eventlet_no_greendns = script % ('dns', 'import eventlet', 'yes', 'not', 1, 0)

no_eventlet_greendns = script % ('dns', '', 'no', '', 1, 0)

eventlet_greendns = script % ('dns', 'import eventlet', 'no', 'not', 0, 1)


class IPv6ServerTest(test_utils.BaseTestCase):

    def test_no_evnetlet_no_dnspython(self):
        """Test eventlet not imported and dnspython not installed"""
        rc = subprocess.call(['python', '-c', no_eventlet_no_dns])
        self.assertEqual(0, rc)

    def test_evnetlet_no_dnspython(self):
        """Test eventlet pre-imported but dnspython not installed"""
        rc = subprocess.call(['python', '-c', eventlet_no_dns])
        self.assertEqual(0, rc)

    def test_no_eventlet_no_greendns(self):
        """Test eventlet not imported with EVENTLET_NO_GREENDNS='yes'"""
        rc = subprocess.call(['python', '-c', no_eventlet_no_greendns])
        self.assertEqual(0, rc)

    def test_eventlet_no_greendns(self):
        """Test eventlet pre-imported with EVENTLET_NO_GREENDNS='yes'"""
        rc = subprocess.call(['python', '-c', eventlet_no_greendns])
        self.assertEqual(0, rc)

    def test_no_eventlet_w_greendns(self):
        """Test eventlet not imported with EVENTLET_NO_GREENDNS='no'"""
        rc = subprocess.call(['python', '-c', no_eventlet_greendns])
        self.assertEqual(0, rc)

    def test_eventlet_w_greendns(self):
        """Test eventlet pre-imported with EVENTLET_NO_GREENDNS='no'"""
        rc = subprocess.call(['python', '-c', eventlet_greendns])
        self.assertEqual(0, rc)
