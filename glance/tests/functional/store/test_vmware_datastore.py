# Copyright 2014 OpenStack Foundation
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
Functional tests for the VMware Datastore store interface

Set the GLANCE_TEST_VMWARE_CONF environment variable to the location
of a Glance config that defines how to connect to a functional
VMware Datastore backend
"""

import ConfigParser
import httplib
import logging
import os

import oslo.config.cfg
from oslo.vmware import api
import six.moves.urllib.parse as urlparse
import testtools

import glance.store.vmware_datastore as vm_store
import glance.tests.functional.store as store_tests


logging.getLogger('suds').setLevel(logging.INFO)


def read_config(path):
    cp = ConfigParser.RawConfigParser()
    cp.read(path)
    return cp


def parse_config(config):
    out = {}
    options = [
        'vmware_server_host',
        'vmware_server_username',
        'vmware_server_password',
        'vmware_api_retry_count',
        'vmware_task_poll_interval',
        'vmware_store_image_dir',
        'vmware_datacenter_path',
        'vmware_datastore_name',
        'vmware_api_insecure',
    ]
    for option in options:
        out[option] = config.defaults()[option]

    return out


class VMwareDatastoreStoreError(RuntimeError):
    pass


def vsphere_connect(server_ip, server_username, server_password,
                    api_retry_count, task_poll_interval,
                    scheme='https', create_session=True, wsdl_loc=None):
    try:
        return api.VMwareAPISession(server_ip,
                                    server_username,
                                    server_password,
                                    api_retry_count,
                                    task_poll_interval,
                                    scheme=scheme,
                                    create_session=create_session,
                                    wsdl_loc=wsdl_loc)
    except AttributeError:
        raise VMwareDatastoreStoreError(
            'Could not find VMware datastore module')


class TestVMwareDatastoreStore(store_tests.BaseTestCase, testtools.TestCase):

    store_cls_path = 'glance.store.vmware_datastore.Store'
    store_cls = vm_store.Store
    store_name = 'vmware_datastore'

    def _build_vim_cookie_header(self, vim_cookies):
        """Build ESX host session cookie header."""
        if len(list(vim_cookies)) > 0:
            cookie = list(vim_cookies)[0]
            return cookie.name + '=' + cookie.value

    def setUp(self):
        config_path = os.environ.get('GLANCE_TEST_VMWARE_CONF')
        if not config_path:
            msg = 'GLANCE_TEST_VMWARE_CONF environ not set.'
            self.skipTest(msg)

        oslo.config.cfg.CONF(args=[], default_config_files=[config_path])

        raw_config = read_config(config_path)
        config = parse_config(raw_config)
        scheme = 'http' if config['vmware_api_insecure'] == 'True' else 'https'
        self.vsphere = vsphere_connect(config['vmware_server_host'],
                                       config['vmware_server_username'],
                                       config['vmware_server_password'],
                                       config['vmware_api_retry_count'],
                                       config['vmware_task_poll_interval'],
                                       scheme=scheme)

        self.vmware_config = config
        super(TestVMwareDatastoreStore, self).setUp()

    def get_store(self, **kwargs):
        store = vm_store.Store(
            context=kwargs.get('context'))
        store.configure()
        store.configure_add()
        return store

    def stash_image(self, image_id, image_data):
        server_ip = self.vmware_config['vmware_server_host']
        path = os.path.join(
            vm_store.DS_URL_PREFIX,
            self.vmware_config['vmware_store_image_dir'].strip('/'), image_id)
        dc_path = self.vmware_config.get('vmware_datacenter_path',
                                         'ha-datacenter')
        param_list = {'dcPath': dc_path,
                      'dsName': self.vmware_config['vmware_datastore_name']}
        query = urlparse.urlencode(param_list)
        conn = (httplib.HTTPConnection(server_ip)
                if self.vmware_config['vmware_api_insecure'] == 'True'
                else httplib.HTTPSConnection(server_ip))
        cookie = self._build_vim_cookie_header(
            self.vsphere.vim.client.options.transport.cookiejar)
        headers = {'Cookie': cookie, 'Content-Length': len(image_data)}
        url = urlparse.quote('%s?%s' % (path, query))
        conn.request('PUT', url, image_data, headers)
        conn.getresponse()

        return '%s://%s%s?%s' % (vm_store.STORE_SCHEME, server_ip, path, query)
