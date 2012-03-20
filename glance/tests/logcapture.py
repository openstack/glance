# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 Red Hat, Inc
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
Custom nose plugin to capture the entire glance service logs for failed tests.
"""

from glance.tests import functional

from nose.plugins.base import Plugin
from nose.util import ln, safe_str


class GlanceLogCapture(Plugin):
    enabled = False
    env_opt = 'NOSE_GLANCELOGCAPTURE'
    name = 'glance-logcapture'

    def options(self, parser, env):
        parser.add_option(
            "--glance-logcapture",
            action="store_true",
            default=env.get(self.env_opt),
            dest="glance_logcapture",
            help="Enable glance log capture plugin [NOSE_GLANCELOGCAPTURE]")

    def configure(self, options, conf):
        self.enabled = options.glance_logcapture

    def formatFailure(self, test, err):
        return self.formatError(test, err)

    def formatError(self, test, err):
        if self.enabled:
            ec, ev, tb = err
            err = (ec, self._dump_logs(ev, test), tb)
        return err

    def _dump_logs(self, ev, test):
        ret = ev
        if isinstance(test.test, functional.FunctionalTest):
            dump = test.test.dump_logs()
            if dump:
                ret = '\n'.join([safe_str(ev),
                                ln('>> begin captured glance logging <<')] +
                                [dump] +
                                [ln('>> end captured glance logging <<')])
        return ret
