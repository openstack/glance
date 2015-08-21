# Copyright 2013 Rackspace Hosting
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

import atexit
import os.path
import tempfile

import fixtures
import glance_store
from oslo_config import cfg
from oslo_db import options

import glance.common.client
from glance.common import config
from glance.db import migration
import glance.db.sqlalchemy.api
import glance.registry.client.v1.client
from glance import tests as glance_tests
from glance.tests import utils as test_utils


TESTING_API_PASTE_CONF = """
[pipeline:glance-api]
pipeline = versionnegotiation gzip unauthenticated-context rootapp

[pipeline:glance-api-caching]
pipeline = versionnegotiation gzip unauthenticated-context cache rootapp

[pipeline:glance-api-cachemanagement]
pipeline =
    versionnegotiation
    gzip
    unauthenticated-context
    cache
    cache_manage
    rootapp

[pipeline:glance-api-fakeauth]
pipeline = versionnegotiation gzip fakeauth context rootapp

[pipeline:glance-api-noauth]
pipeline = versionnegotiation gzip context rootapp

[composite:rootapp]
paste.composite_factory = glance.api:root_app_factory
/: apiversions
/v1: apiv1app
/v2: apiv2app
/v3: apiv3app

[app:apiversions]
paste.app_factory = glance.api.versions:create_resource

[app:apiv1app]
paste.app_factory = glance.api.v1.router:API.factory

[app:apiv2app]
paste.app_factory = glance.api.v2.router:API.factory

[app:apiv3app]
paste.app_factory = glance.api.v3.router:API.factory

[filter:versionnegotiation]
paste.filter_factory =
 glance.api.middleware.version_negotiation:VersionNegotiationFilter.factory

[filter:gzip]
paste.filter_factory = glance.api.middleware.gzip:GzipMiddleware.factory

[filter:cache]
paste.filter_factory = glance.api.middleware.cache:CacheFilter.factory

[filter:cache_manage]
paste.filter_factory =
 glance.api.middleware.cache_manage:CacheManageFilter.factory

[filter:context]
paste.filter_factory = glance.api.middleware.context:ContextMiddleware.factory

[filter:unauthenticated-context]
paste.filter_factory =
 glance.api.middleware.context:UnauthenticatedContextMiddleware.factory

[filter:fakeauth]
paste.filter_factory = glance.tests.utils:FakeAuthMiddleware.factory
"""

TESTING_REGISTRY_PASTE_CONF = """
[pipeline:glance-registry]
pipeline = unauthenticated-context registryapp

[pipeline:glance-registry-fakeauth]
pipeline = fakeauth context registryapp

[app:registryapp]
paste.app_factory = glance.registry.api.v1:API.factory

[filter:context]
paste.filter_factory = glance.api.middleware.context:ContextMiddleware.factory

[filter:unauthenticated-context]
paste.filter_factory =
 glance.api.middleware.context:UnauthenticatedContextMiddleware.factory

[filter:fakeauth]
paste.filter_factory = glance.tests.utils:FakeAuthMiddleware.factory
"""

CONF = cfg.CONF


class ApiTest(test_utils.BaseTestCase):
    def setUp(self):
        super(ApiTest, self).setUp()
        self.test_dir = self.useFixture(fixtures.TempDir()).path
        self._configure_logging()
        self._setup_database()
        self._setup_stores()
        self._setup_property_protection()
        self.glance_registry_app = self._load_paste_app(
            'glance-registry',
            flavor=getattr(self, 'registry_flavor', ''),
            conf=getattr(self, 'registry_paste_conf',
                         TESTING_REGISTRY_PASTE_CONF),
        )
        self._connect_registry_client()
        self.glance_api_app = self._load_paste_app(
            'glance-api',
            flavor=getattr(self, 'api_flavor', ''),
            conf=getattr(self, 'api_paste_conf', TESTING_API_PASTE_CONF),
        )
        self.http = test_utils.Httplib2WsgiAdapter(self.glance_api_app)

    def _setup_property_protection(self):
        self._copy_data_file('property-protections.conf', self.test_dir)
        self.property_file = os.path.join(self.test_dir,
                                          'property-protections.conf')

    def _configure_logging(self):
        self.config(default_log_levels=[
            'amqplib=WARN',
            'sqlalchemy=WARN',
            'boto=WARN',
            'suds=INFO',
            'keystone=INFO',
            'eventlet.wsgi.server=DEBUG'
        ])

    def _setup_database(self):
        sql_connection = 'sqlite:////%s/tests.sqlite' % self.test_dir
        options.set_defaults(CONF, connection=sql_connection,
                             sqlite_db='glance.sqlite')
        glance.db.sqlalchemy.api.clear_db_env()
        glance_db_env = 'GLANCE_DB_TEST_SQLITE_FILE'
        if glance_db_env in os.environ:
            # use the empty db created and cached as a tempfile
            # instead of spending the time creating a new one
            db_location = os.environ[glance_db_env]
            test_utils.execute('cp %s %s/tests.sqlite'
                               % (db_location, self.test_dir))
        else:
            migration.db_sync()

            # copy the clean db to a temp location so that it
            # can be reused for future tests
            (osf, db_location) = tempfile.mkstemp()
            os.close(osf)
            test_utils.execute('cp %s/tests.sqlite %s'
                               % (self.test_dir, db_location))
            os.environ[glance_db_env] = db_location

            # cleanup the temp file when the test suite is
            # complete
            def _delete_cached_db():
                try:
                    os.remove(os.environ[glance_db_env])
                except Exception:
                    glance_tests.logger.exception(
                        "Error cleaning up the file %s" %
                        os.environ[glance_db_env])
            atexit.register(_delete_cached_db)

    def _setup_stores(self):
        glance_store.register_opts(CONF)

        image_dir = os.path.join(self.test_dir, "images")
        self.config(group='glance_store',
                    filesystem_store_datadir=image_dir)

        glance_store.create_stores()

    def _load_paste_app(self, name, flavor, conf):
        conf_file_path = os.path.join(self.test_dir, '%s-paste.ini' % name)
        with open(conf_file_path, 'wb') as conf_file:
            conf_file.write(conf)
            conf_file.flush()
        return config.load_paste_app(name, flavor=flavor,
                                     conf_file=conf_file_path)

    def _connect_registry_client(self):
        def get_connection_type(self2):
            def wrapped(*args, **kwargs):
                return test_utils.HttplibWsgiAdapter(self.glance_registry_app)
            return wrapped

        self.stubs.Set(glance.common.client.BaseClient,
                       'get_connection_type', get_connection_type)

    def tearDown(self):
        glance.db.sqlalchemy.api.clear_db_env()
        super(ApiTest, self).tearDown()
