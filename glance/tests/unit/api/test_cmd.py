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


import StringIO
import sys

import glance.cmd.api
import glance.common.config
from glance.common import exception as exc
import glance.common.wsgi
from glance.tests import utils as test_utils


class TestGlanceApiCmd(test_utils.BaseTestCase):
    def _do_nothing(self, *args, **kwargs):
        pass

    def _raise(self, exc):
        def fake(*args, **kwargs):
            raise exc
        return fake

    def setUp(self):
        super(TestGlanceApiCmd, self).setUp()
        sys.argv = ['glance-api']
        self.stderr = StringIO.StringIO()
        sys.stderr = self.stderr

        self.stubs.Set(glance.common.config, 'load_paste_app',
                       self._do_nothing)
        self.stubs.Set(glance.common.wsgi.Server, 'start',
                       self._do_nothing)
        self.stubs.Set(glance.common.wsgi.Server, 'wait',
                       self._do_nothing)

    def tearDown(self):
        sys.stderr = sys.__stderr__
        super(TestGlanceApiCmd, self).tearDown()

    def test_supported_default_store(self):
        self.config(default_store='file')
        glance.cmd.api.main()

    def test_unsupported_default_store(self):
        self.config(default_store='shouldnotexist')
        exit = self.assertRaises(SystemExit, glance.cmd.api.main)
        self.assertEquals(exit.code, 1)

    def test_worker_creation_failure(self):
        failure = exc.WorkerCreationFailure(reason='test')
        self.stubs.Set(glance.common.wsgi.Server, 'start',
                       self._raise(failure))
        exit = self.assertRaises(SystemExit, glance.cmd.api.main)
        self.assertEquals(exit.code, 2)
