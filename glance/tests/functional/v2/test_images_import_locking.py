# Copyright 2020 Red Hat, Inc.
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

import datetime
import os
from testtools import content as ttc
import textwrap
import time
from unittest import mock
import uuid

from oslo_config import cfg
from oslo_log import log as logging
from oslo_serialization import jsonutils
from oslo_utils import fixture as time_fixture
import webob

from glance.common import config
from glance.common import wsgi
import glance.db.sqlalchemy.api
from glance.tests import utils as test_utils
import glance_store

LOG = logging.getLogger(__name__)
TENANT1 = str(uuid.uuid4())
CONF = cfg.CONF


class SynchronousAPIBase(test_utils.BaseTestCase):
    """A test base class that provides synchronous calling into the API
    without starting a separate server, and with a simple paste
    pipeline. Configured with multi-store and a real database.
    """

    @mock.patch('oslo_db.sqlalchemy.enginefacade.writer.get_engine')
    def setup_database(self, mock_get_engine):
        db_file = 'sqlite:///%s/test-%s.db' % (self.test_dir,
                                               uuid.uuid4())
        self.config(connection=db_file, group='database')

        # NOTE(danms): Make sure that we clear the current global
        # database configuration, provision a temporary database file,
        # and run migrations with our configuration to define the
        # schema there.
        glance.db.sqlalchemy.api.clear_db_env()
        engine = glance.db.sqlalchemy.api.get_engine()
        mock_get_engine.return_value = engine
        with mock.patch('logging.config'):
            # NOTE(danms): The alembic config in the env module will break our
            # BaseTestCase logging setup. So mock that out to prevent it while
            # we db_sync.
            test_utils.db_sync(engine=engine)

    def setup_simple_paste(self):
        self.paste_config = os.path.join(self.test_dir, 'glance-api-paste.ini')
        with open(self.paste_config, 'w') as f:
            f.write(textwrap.dedent("""
            [filter:context]
            paste.filter_factory = glance.api.middleware.context:\
                ContextMiddleware.factory
            [filter:fakeauth]
            paste.filter_factory = glance.tests.utils:\
                FakeAuthMiddleware.factory
            [pipeline:glance-api]
            pipeline = context rootapp
            [composite:rootapp]
            paste.composite_factory = glance.api:root_app_factory
            /v2: apiv2app
            [app:apiv2app]
            paste.app_factory = glance.api.v2.router:API.factory
            """))

    def _store_dir(self, store):
        return os.path.join(self.test_dir, store)

    def setup_stores(self):
        self.config(enabled_backends={'store1': 'file', 'store2': 'file'})
        glance_store.register_store_opts(CONF,
                                         reserved_stores=wsgi.RESERVED_STORES)
        self.config(default_backend='store1',
                    group='glance_store')
        self.config(filesystem_store_datadir=self._store_dir('store1'),
                    group='store1')
        self.config(filesystem_store_datadir=self._store_dir('store2'),
                    group='store2')
        self.config(filesystem_store_datadir=self._store_dir('staging'),
                    group='os_glance_staging_store')

        glance_store.create_multi_stores(CONF,
                                         reserved_stores=wsgi.RESERVED_STORES)
        glance_store.verify_store()

    def setUp(self):
        super(SynchronousAPIBase, self).setUp()

        self.setup_database()
        self.setup_simple_paste()
        self.setup_stores()

    def start_server(self):
        config.set_config_defaults()
        self.api = config.load_paste_app('glance-api',
                                         conf_file=self.paste_config)

    def _headers(self, custom_headers=None):
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': TENANT1,
            'Content-Type': 'application/json',
            'X-Roles': 'admin',
        }
        base_headers.update(custom_headers or {})
        return base_headers

    def api_get(self, url, headers=None):
        headers = self._headers(headers)
        req = webob.Request.blank(url, method='GET',
                                  headers=headers)
        return self.api(req)

    def api_post(self, url, data=None, json=None, headers=None):
        headers = self._headers(headers)
        req = webob.Request.blank(url, method='POST',
                                  headers=headers)
        if json and not data:
            data = jsonutils.dumps(json).encode()
            headers['Content-Type'] = 'application/json'
        if data:
            req.body = data
        LOG.debug(req.as_bytes())
        return self.api(req)

    def api_put(self, url, data=None, json=None, headers=None):
        headers = self._headers(headers)
        req = webob.Request.blank(url, method='PUT',
                                  headers=headers)
        if json and not data:
            data = jsonutils.dumps(json).encode()
        if data:
            req.body = data
        return self.api(req)


class TestImageImportLocking(SynchronousAPIBase):
    def _import_copy(self, image_id, stores):
        """Do an import of image_id to the given stores."""
        body = {'method': {'name': 'copy-image'},
                'stores': stores,
                'all_stores': False}

        return self.api_post(
            '/v2/images/%s/import' % image_id,
            json=body)

    def _create_and_import(self, stores=[]):
        """Create an image, stage data, and import into the given stores.

        :returns: image_id
        """
        resp = self.api_post('/v2/images',
                             json={'name': 'foo',
                                   'container_format': 'bare',
                                   'disk_format': 'raw'})
        image = jsonutils.loads(resp.text)

        resp = self.api_put(
            '/v2/images/%s/stage' % image['id'],
            headers={'Content-Type': 'application/octet-stream'},
            data=b'IMAGEDATA')
        self.assertEqual(204, resp.status_code)

        body = {'method': {'name': 'glance-direct'}}
        if stores:
            body['stores'] = stores

        resp = self.api_post(
            '/v2/images/%s/import' % image['id'],
            json=body)

        self.assertEqual(202, resp.status_code)

        # Make sure it goes active
        for i in range(0, 10):
            image = self.api_get('/v2/images/%s' % image['id']).json
            if not image.get('os_glance_import_task'):
                break
            self.addDetail('Create-Import task id',
                           ttc.text_content(image['os_glance_import_task']))
            time.sleep(1)

        self.assertEqual('active', image['status'])

        return image['id']

    def _test_import_copy(self, warp_time=False):
        self.start_server()
        state = {}

        # Create and import an image with no pipeline stall
        image_id = self._create_and_import(stores=['store1'])

        # Set up a fake data pipeline that will stall until we are ready
        # to unblock it
        def slow_fake_set_data(data_iter, backend=None, set_active=True):
            while True:
                state['running'] = True
                time.sleep(0.1)

        # Constrain oslo timeutils time so we can manipulate it
        tf = time_fixture.TimeFixture()
        self.useFixture(tf)

        # Turn on the delayed data pipeline and start a copy-image
        # import which will hang out for a while
        with mock.patch('glance.domain.proxy.Image.set_data') as mock_sd:
            mock_sd.side_effect = slow_fake_set_data

            resp = self._import_copy(image_id, ['store2'])
            self.addDetail('First import response',
                           ttc.text_content(str(resp)))
            self.assertEqual(202, resp.status_code)

            # Wait to make sure the data stream gets started
            for i in range(0, 10):
                if state:
                    break
                time.sleep(0.1)

        # Make sure the first import got to the point where the
        # hanging loop will hold it in processing state
        self.assertTrue(state.get('running', False),
                        'slow_fake_set_data() never ran')

        # If we're warping time, then advance the clock by two hours
        if warp_time:
            tf.advance_time_delta(datetime.timedelta(hours=2))

        # Try a second copy-image import. If we are warping time,
        # expect the lock to be busted. If not, then we should get
        # a 409 Conflict.
        resp = self._import_copy(image_id, ['store2'])

        self.addDetail('Second import response',
                       ttc.text_content(str(resp)))
        if warp_time:
            self.assertEqual(202, resp.status_code)
        else:
            self.assertEqual(409, resp.status_code)

    def test_import_copy_locked(self):
        self._test_import_copy(warp_time=False)

    def test_import_copy_bust_lock(self):
        self._test_import_copy(warp_time=True)
