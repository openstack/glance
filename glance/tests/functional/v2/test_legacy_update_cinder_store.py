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

from testtools import content as ttc
import time
from unittest import mock
import uuid

from cinderclient.v3 import client as cinderclient
import glance_store
from glance_store._drivers import cinder
from oslo_config import cfg
from oslo_log import log as logging
from oslo_serialization import jsonutils

from glance.common import wsgi
from glance.tests import functional

LOG = logging.getLogger(__name__)

CONF = cfg.CONF


class FakeObject(object):
    def __init__(self, **kwargs):
        for name, value in kwargs.items():
            setattr(self, name, value)


class TestLegacyUpdateCinderStore(functional.SynchronousAPIBase):

    def setUp(self):
        super(TestLegacyUpdateCinderStore, self).setUp()
        self.vol_id = uuid.uuid4()
        self.cinder_store_mock = FakeObject(
            client=mock.MagicMock(), volumes=FakeObject(
                get=lambda v_id: FakeObject(volume_type='fast'),
                detach=mock.MagicMock(),
                create=lambda size_gb, name, metadata, volume_type:
                FakeObject(
                    id=self.vol_id, manager=FakeObject(
                        get=lambda vol_id: FakeObject(
                            manager=FakeObject(
                                get=lambda vol_id: FakeObject(
                                    status='in-use',
                                    begin_detaching=mock.MagicMock(),
                                    terminate_connection=mock.MagicMock())),
                            id=vol_id,
                            status='available',
                            size=1,
                            reserve=mock.MagicMock(),
                            initialize_connection=mock.MagicMock(),
                            encrypted=False,
                            unreserve=mock.MagicMock(),
                            delete=mock.MagicMock(),
                            attach=mock.MagicMock(),
                            update_all_metadata=mock.MagicMock(),
                            update_readonly_flag=mock.MagicMock())))))

    def setup_stores(self):
        pass

    def setup_single_store(self):
        glance_store.register_opts(CONF)
        self.config(show_multiple_locations=True)
        self.config(show_image_direct_url=True)
        self.config(default_store='cinder', group='glance_store')
        self.config(stores=['http', 'swift', 'cinder'], group='glance_store')
        self.config(cinder_volume_type='fast', group='glance_store')
        self.config(cinder_store_user_name='fake_user', group='glance_store')
        self.config(cinder_store_password='fake_pass', group='glance_store')
        self.config(cinder_store_project_name='fake_project',
                    group='glance_store')
        self.config(cinder_store_auth_address='http://auth_addr',
                    group='glance_store')
        glance_store.create_stores(CONF)

    def unset_single_store(self):
        glance_store.register_opts(CONF)
        self.config(show_multiple_locations=True)
        self.config(show_image_direct_url=True)
        self.config(stores=[], group='glance_store')
        self.config(cinder_volume_type='', group='glance_store')
        self.config(cinder_store_user_name='', group='glance_store')
        self.config(cinder_store_password='', group='glance_store')
        self.config(cinder_store_project_name='', group='glance_store')
        self.config(cinder_store_auth_address='', group='glance_store')
        glance_store.create_stores(CONF)

    @mock.patch.object(cinderclient, 'Client')
    def setup_multiple_stores(self, mock_client):
        """Configures multiple backend stores.

        This configures the API with two cinder stores (store1 and
        store2) as well as a os_glance_staging_store for
        imports.

        """
        self.config(show_multiple_locations=True)
        self.config(show_image_direct_url=True)
        self.config(enabled_backends={'store1': 'cinder', 'store2': 'cinder'})
        glance_store.register_store_opts(CONF,
                                         reserved_stores=wsgi.RESERVED_STORES)
        self.config(default_backend='store1',
                    group='glance_store')
        self.config(cinder_volume_type='fast', group='store1')
        self.config(cinder_store_user_name='fake_user', group='store1')
        self.config(cinder_store_password='fake_pass', group='store1')
        self.config(cinder_store_project_name='fake_project', group='store1')
        self.config(cinder_store_auth_address='http://auth_addr',
                    group='store1')
        self.config(cinder_volume_type='reliable', group='store2')
        self.config(cinder_store_user_name='fake_user', group='store2')
        self.config(cinder_store_password='fake_pass', group='store2')
        self.config(cinder_store_project_name='fake_project', group='store2')
        self.config(cinder_store_auth_address='http://auth_addr',
                    group='store2')
        self.config(filesystem_store_datadir=self._store_dir('staging'),
                    group='os_glance_staging_store')
        glance_store.create_multi_stores(CONF,
                                         reserved_stores=wsgi.RESERVED_STORES)
        glance_store.verify_store()

    def _create_and_stage(self, data_iter=None):
        resp = self.api_post('/v2/images',
                             json={'name': 'foo',
                                   'container_format': 'bare',
                                   'disk_format': 'raw'})
        image = jsonutils.loads(resp.text)

        if data_iter:
            resp = self.api_put(
                '/v2/images/%s/stage' % image['id'],
                headers={'Content-Type': 'application/octet-stream'},
                body_file=data_iter)
        else:
            resp = self.api_put(
                '/v2/images/%s/stage' % image['id'],
                headers={'Content-Type': 'application/octet-stream'},
                data=b'IMAGEDATA')
        self.assertEqual(204, resp.status_code)

        return image['id']

    def _import_direct(self, image_id, stores):
        """Do an import of image_id to the given stores."""
        body = {'method': {'name': 'glance-direct'},
                'stores': stores,
                'all_stores': False}

        return self.api_post(
            '/v2/images/%s/import' % image_id,
            json=body)

    def _create_and_import(self, stores=[], data_iter=None):
        """Create an image, stage data, and import into the given stores.

        :returns: image_id
        """
        image_id = self._create_and_stage(data_iter=data_iter)

        resp = self._import_direct(image_id, stores)
        self.assertEqual(202, resp.status_code)

        # Make sure it goes active
        for i in range(0, 10):
            image = self.api_get('/v2/images/%s' % image_id).json
            if not image.get('os_glance_import_task'):
                break
            self.addDetail('Create-Import task id',
                           ttc.text_content(image['os_glance_import_task']))
            time.sleep(1)

        self.assertEqual('active', image['status'])

        return image_id

    @mock.patch.object(cinderclient, 'Client')
    @mock.patch.object(cinder.Store, 'temporary_chown')
    @mock.patch.object(cinder, 'connector')
    @mock.patch.object(cinder, 'open')
    def test_create_image(self, mock_open, mock_connector,
                          mock_chown, mocked_cc):
        # setup multiple cinder stores
        self.setup_multiple_stores()
        self.start_server()

        mocked_cc.return_value = self.cinder_store_mock
        # create an image
        image_id = self._create_and_import(stores=['store1'])
        image = self.api_get('/v2/images/%s' % image_id).json
        # verify image is created with new location url
        self.assertEqual('cinder://store1/%s' % self.vol_id,
                         image['locations'][0]['url'])
        self.assertEqual('store1', image['locations'][0]['metadata']['store'])
        # NOTE(whoami-rajat): These are internals called by glance_store, so
        # we want to make sure they got hit, but not be too strict about how.
        mocked_cc.assert_called()
        mock_open.assert_called()
        mock_chown.assert_called()
        mock_connector.get_connector_properties.assert_called()

    @mock.patch.object(cinderclient, 'Client')
    @mock.patch.object(cinder.Store, 'temporary_chown')
    @mock.patch.object(cinder, 'connector')
    @mock.patch.object(cinder, 'open')
    def test_migrate_image_after_upgrade(self, mock_open, mock_connector,
                                         mock_chown, mocked_cc):
        """Test to check if an image is successfully migrated when we

        upgrade from a single cinder store to multiple cinder stores.
        """
        # setup single cinder store
        self.setup_single_store()
        self.start_server()
        mocked_cc.return_value = self.cinder_store_mock

        # create image in single store
        image_id = self._create_and_import(stores=['store1'])
        image = self.api_get('/v2/images/%s' % image_id).json
        # check the location url is in old format
        self.assertEqual('cinder://%s' % self.vol_id,
                         image['locations'][0]['url'])
        self.unset_single_store()
        # setup multiple cinder stores
        self.setup_multiple_stores()
        cinder.keystone_sc = mock.MagicMock()
        # get the image to run lazy loading
        image = self.api_get('/v2/images/%s' % image_id).json
        # verify the image is updated to new format
        self.assertEqual('cinder://store1/%s' % self.vol_id,
                         image['locations'][0]['url'])
        self.assertEqual('store1', image['locations'][0]['metadata']['store'])
        image = self.api_get('/v2/images/%s' % image_id).json
        # verify the image location url is consistent
        self.assertEqual('cinder://store1/%s' % self.vol_id,
                         image['locations'][0]['url'])
        # NOTE(whoami-rajat): These are internals called by glance_store, so
        # we want to make sure they got hit, but not be too strict about how.
        mocked_cc.assert_called()
        mock_open.assert_called()
        mock_chown.assert_called()
        mock_connector.get_connector_properties.assert_called()
