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

"""Fixtures for Glance unit tests."""
# NOTE(mriedem): This is needed for importing from fixtures.

import logging as std_logging
import os
from unittest import mock
import warnings

import fixtures as pyfixtures
from openstack.identity.v3 import endpoint
from openstack.identity.v3 import limit as klimit
from oslo_db import warning as oslo_db_warning
from oslo_limit import limit
from sqlalchemy import exc as sqla_exc

_TRUE_VALUES = ('True', 'true', '1', 'yes')


class NullHandler(std_logging.Handler):
    """custom default NullHandler to attempt to format the record.

    Used in conjunction with
    log_fixture.get_logging_handle_error_fixture to detect formatting errors in
    debug level logs without saving the logs.
    """
    def handle(self, record):
        self.format(record)

    def emit(self, record):
        pass

    def createLock(self):
        self.lock = None


class StandardLogging(pyfixtures.Fixture):
    """Setup Logging redirection for tests.

    There are a number of things we want to handle with logging in tests:

    * Redirect the logging to somewhere that we can test or dump it later.

    * Ensure that as many DEBUG messages as possible are actually
       executed, to ensure they are actually syntactically valid (they
       often have not been).

    * Ensure that we create useful output for tests that doesn't
      overwhelm the testing system (which means we can't capture the
      100 MB of debug logging on every run).

    To do this we create a logger fixture at the root level, which
    defaults to INFO and create a Null Logger at DEBUG which lets
    us execute log messages at DEBUG but not keep the output.

    To support local debugging OS_DEBUG=True can be set in the
    environment, which will print out the full debug logging.

    There are also a set of overrides for particularly verbose
    modules to be even less than INFO.

    """

    def setUp(self):
        super(StandardLogging, self).setUp()

        # set root logger to debug
        root = std_logging.getLogger()
        root.setLevel(std_logging.DEBUG)

        # supports collecting debug level for local runs
        if os.environ.get('OS_DEBUG') in _TRUE_VALUES:
            level = std_logging.DEBUG
        else:
            level = std_logging.INFO

        # Collect logs
        fs = '%(asctime)s %(levelname)s [%(name)s] %(message)s'
        self.logger = self.useFixture(
            pyfixtures.FakeLogger(format=fs, level=None))
        # TODO(sdague): why can't we send level through the fake
        # logger? Tests prove that it breaks, but it's worth getting
        # to the bottom of.
        root.handlers[0].setLevel(level)

        if level > std_logging.DEBUG:
            # Just attempt to format debug level logs, but don't save them
            handler = NullHandler()
            self.useFixture(
                pyfixtures.LogHandler(handler, nuke_handlers=False))
            handler.setLevel(std_logging.DEBUG)

        # Don't log every single DB migration step
        std_logging.getLogger(
            'alembic.runtime.migration').setLevel(std_logging.WARNING)

        # At times we end up calling back into main() functions in
        # testing. This has the possibility of calling logging.setup
        # again, which completely unwinds the logging capture we've
        # created here. Once we've setup the logging in the way we want,
        # disable the ability for the test to change this.
        def fake_logging_setup(*args):
            pass

        self.useFixture(
            pyfixtures.MonkeyPatch('oslo_log.log.setup', fake_logging_setup))


class WarningsFixture(pyfixtures.Fixture):
    """Filters out warnings during test runs."""

    def setUp(self):
        super(WarningsFixture, self).setUp()

        self._original_warning_filters = warnings.filters[:]

        # NOTE(sdague): Make deprecation warnings only happen once. Otherwise
        # this gets kind of crazy given the way that upstream python libs use
        # this.
        warnings.simplefilter('once', DeprecationWarning)

        # NOTE(sdague): this remains an unresolved item around the way
        # forward on is_admin, the deprecation is definitely really premature.
        warnings.filterwarnings(
            'ignore',
            message='Policy enforcement is depending on the value of is_admin.'
                    ' This key is deprecated. Please update your policy '
                    'file to use the standard policy values.')

        # NOTE(mriedem): user/tenant is deprecated in oslo.context so don't
        # let anything new use it
        warnings.filterwarnings(
            'error', message="Property '.*' has moved to '.*'")

        # Don't warn for our own deprecation warnings

        warnings.filterwarnings(
            'ignore',
            module='glance',
            category=DeprecationWarning,
        )

        # Disable deprecation warning for oslo.db's EngineFacade. We *really*
        # need to get off this but it's not happening while sqlalchemy 2.0
        # stuff is ongoing

        warnings.filterwarnings(
            'ignore',
            category=oslo_db_warning.OsloDBDeprecationWarning,
            message='EngineFacade is deprecated',
        )

        # Enable deprecation warnings for glance itself to capture upcoming
        # SQLAlchemy changes

        warnings.filterwarnings(
            'ignore',
            category=sqla_exc.SADeprecationWarning,
        )

        warnings.filterwarnings(
            'error',
            module='glance',
            category=sqla_exc.SADeprecationWarning,
        )

        # Enable general SQLAlchemy warnings also to ensure we're not doing
        # silly stuff. It's possible that we'll need to filter things out here
        # with future SQLAlchemy versions, but that's a good thing

        warnings.filterwarnings(
            'error',
            module='glance',
            category=sqla_exc.SAWarning,
        )

        self.addCleanup(self._reset_warning_filters)

    def _reset_warning_filters(self):
        warnings.filters[:] = self._original_warning_filters


class KeystoneQuotaFixture(pyfixtures.Fixture):
    def __init__(self, **defaults):
        self.defaults = defaults

    def setUp(self):
        super(KeystoneQuotaFixture, self).setUp()

        self.mock_conn = mock.MagicMock()
        limit._SDK_CONNECTION = self.mock_conn

        mock_gem = self.useFixture(
            pyfixtures.MockPatch('oslo_limit.limit.Enforcer.'
                                 '_get_enforcement_model')).mock
        mock_gem.return_value = 'flat'

        fake_endpoint = endpoint.Endpoint()
        fake_endpoint.service_id = "service_id"
        fake_endpoint.region_id = "region_id"
        self.mock_conn.get_endpoint.return_value = fake_endpoint

        def fake_limits(service_id, region_id, resource_name, project_id):
            this_limit = klimit.Limit()
            this_limit.resource_name = resource_name
            this_limit.resource_limit = self.defaults[resource_name]
            return iter([this_limit])

        self.mock_conn.limits.side_effect = fake_limits
