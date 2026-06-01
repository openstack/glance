# Copyright 2011 OpenStack Foundation
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
Base test classes for running non-stubbed tests (functional tests)

This module provides SynchronousAPIBase, the base class for functional testing.
"""

import os
import shutil
import sys
from testtools import content as ttc
import textwrap
import threading
import time
from unittest import mock
import uuid

import glance_store
from oslo_config import cfg
from oslo_serialization import jsonutils
import webob

from glance.common import config
from glance.common import utils
from glance.common import wsgi
from glance.db.sqlalchemy import api as db_api
from glance import housekeeping
from glance.tests import utils as test_utils

execute = test_utils.execute

SQLITE_CONN_TEMPLATE = 'sqlite:////%s/tests.sqlite'
CONF = cfg.CONF


class SynchronousAPIBase(test_utils.BaseTestCase):
    """A base class that provides synchronous calling into the API.

    This provides a way to directly call into the API WSGI stack
    without starting a separate server, and with a simple paste
    pipeline. Configured with multi-store and a real database.

    This differs from other functional test approaches in that it calls
    directly into the WSGI stack rather than starting a separate server
    process. This test base is appropriate for situations where you
    need to be able to mock the state of the world (i.e. warp time, or
    inject errors) but should not be used for happy-path testing where
    a separate server process provides more isolation.

    To use this, inherit and run start_server() before you are ready
    to make API calls (either in your setUp() or per-test if you need
    to change config or mocking).

    Once started, use the api_get(), api_put(), api_post(), and
    api_delete() methods to make calls to the API.

    """

    TENANT = str(uuid.uuid4())

    @mock.patch('oslo_db.sqlalchemy.enginefacade.writer.get_engine')
    def setup_database(self, mock_get_engine):
        """Configure and prepare a fresh sqlite database."""
        db_file = 'sqlite:///%s/test.db' % self.test_dir
        self.config(connection=db_file, group='database')

        # NOTE(danms): Make sure that we clear the current global
        # database configuration, provision a temporary database file,
        # and run migrations with our configuration to define the
        # schema there.
        db_api.clear_db_env()
        engine = db_api.get_engine()
        mock_get_engine.return_value = engine
        with mock.patch('logging.config'):
            # NOTE(danms): The alembic config in the env module will break our
            # BaseTestCase logging setup. So mock that out to prevent it while
            # we db_sync.
            test_utils.db_sync(engine=engine)

    def setup_scrubber_conf(self, daemon=False, wakeup_time=300,
                            scrub_pool_size=12):
        self.scrubber_conf = os.path.join(
            self.test_dir, 'glance-scrubber.conf')
        db_file = 'sqlite:///%s/test.db' % self.test_dir
        with open(self.scrubber_conf, 'w') as f:
            f.write(textwrap.dedent("""
            [DEFAULT]
            enabled_backends=store1:file,store2:file,store3:file
            daemon=%(daemon)s
            wakeup_time=%(wakeup_time)s
            scrub_pool_size=%(scrub_pool_size)s
            [database]
            connection=%(connection)s
            [store1]
            filesystem_store_datadir=%(store1)s
            [store2]
            filesystem_store_datadir=%(store2)s
            [store3]
            filesystem_store_datadir=%(store3)s
            [os_glance_staging_dir]
            filesystem_store_datadir=%(staging)s
            [glance_store]
            default_backend=store1
            """) % {
                "daemon": daemon,
                "wakeup_time": wakeup_time,
                "scrub_pool_size": scrub_pool_size,
                "connection": db_file,
                "store1": self._store_dir('store1'),
                "store2": self._store_dir('store2'),
                "store3": self._store_dir('store3'),
                "staging": self._store_dir('staging'),
            })

    def setup_simple_paste(self):
        """Setup a very simple no-auth paste pipeline.

        This configures the API to be very direct, including only the
        middleware absolutely required for consistent API calls.
        """
        self.paste_config = os.path.join(self.test_dir, 'glance-api-paste.ini')
        with open(self.paste_config, 'w') as f:
            f.write(textwrap.dedent("""
            [filter:context]
            paste.filter_factory = glance.api.middleware.context:\
                ContextMiddleware.factory
            [filter:unauthenticated-context]
            paste.filter_factory = glance.api.middleware.context:\
                UnauthenticatedContextMiddleware.factory
            [filter:versionnegotiation]
            paste.filter_factory = glance.api.middleware.version_negotiation:\
                VersionNegotiationFilter.factory
            [filter:fakeauth]
            paste.filter_factory = glance.tests.utils:\
                FakeAuthMiddleware.factory
            [filter:cors]
            paste.filter_factory = oslo_middleware.cors:filter_factory
            allowed_origin=http://valid.example.com
            [filter:gzip]
            paste.filter_factory = glance.api.middleware.gzip:\
                GzipMiddleware.factory
            [filter:cache]
            paste.filter_factory = glance.api.middleware.cache:\
            CacheFilter.factory
            [filter:cachemanage]
            paste.filter_factory = glance.api.middleware.cache_manage:\
            CacheManageFilter.factory
            [pipeline:glance-api-cachemanagement]
            pipeline = context cache cachemanage gzip rootapp
            [pipeline:glance-api-cors]
            pipeline = cors context gzip rootapp
            [pipeline:glance-api-caching]
            pipeline = context cache gzip rootapp
            [pipeline:glance-api]
            pipeline = context rootapp
            [pipeline:glance-api-versionnegotiation]
            pipeline = versionnegotiation unauthenticated-context cache cachemanage rootapp
            [pipeline:glance-api-fake]
            pipeline = fakeauth context gzip rootapp
            [composite:rootapp]
            paste.composite_factory = glance.api:root_app_factory
            /: apiversions
            /v2: apiv2app
            /healthcheck: healthcheck
            [app:apiversions]
            paste.app_factory = glance.api.versions:create_resource
            [app:apiv2app]
            paste.app_factory = glance.api.v2.router:API.factory
            [app:healthcheck]
            paste.app_factory = oslo_middleware:Healthcheck.app_factory
            backends = disable_by_file
            disable_by_file_path = /tmp/test_path
            """))

    def _store_dir(self, store):
        return os.path.join(self.test_dir, store)

    def setup_single_store(self):
        """Configures single backend.

        This configures the API with one file-backed store
        as well as node_staging_uri for imports.

        """
        glance_store.register_opts(CONF)
        self.config(filesystem_store_datadir=self._store_dir('store1'),
                    group='glance_store')
        node_staging_uri = 'file://%s' % os.path.join(
            self.test_dir, 'staging')
        utils.safe_mkdirs(node_staging_uri[7:])
        self.config(node_staging_uri=node_staging_uri)
        self.config(default_store='file', group='glance_store')
        glance_store.create_stores(CONF)
        glance_store.verify_default_store()

    def setup_property_protection_files(self):
        """Setup property protection configuration files.

        This creates property protection files dynamically for testing,
        similar to how setup_simple_paste() creates paste config files.
        Creates both roles-based and policies-based property protection
        files.
        """
        conf_dir = os.path.join(self.test_dir, 'etc')
        utils.safe_mkdirs(conf_dir)

        # Create roles-based property protection file
        property_file_roles = os.path.join(conf_dir,
                                           'property-protections.conf')
        with open(property_file_roles, 'w') as f:
            f.write(textwrap.dedent("""
            [^x_owner_.*]
            create = admin,member
            read = admin,member
            update = admin,member
            delete = admin,member

            [spl_create_prop]
            create = admin,spl_role
            read = admin,spl_role
            update = admin
            delete = admin

            [spl_read_prop]
            create = admin,spl_role
            read = admin,spl_role
            update = admin
            delete = admin

            [spl_read_only_prop]
            create = admin
            read = admin,spl_role
            update = admin
            delete = admin

            [spl_update_prop]
            create = admin,spl_role
            read = admin,spl_role
            update = admin,spl_role
            delete = admin

            [spl_update_only_prop]
            create = admin
            read = admin
            update = admin,spl_role
            delete = admin

            [spl_delete_prop]
            create = admin,spl_role
            read = admin,spl_role
            update = admin
            delete = admin,spl_role

            [spl_delete_empty_prop]
            create = admin,spl_role
            read = admin,spl_role
            update = admin
            delete = admin,spl_role

            [^x_all_permitted.*]
            create = @
            read = @
            update = @
            delete = @

            [^x_none_permitted.*]
            create = !
            read = !
            update = !
            delete = !

            [x_none_read]
            create = admin,member
            read = !
            update = !
            delete = !

            [x_none_update]
            create = admin,member
            read = admin,member
            update = !
            delete = admin,member

            [x_none_delete]
            create = admin,member
            read = admin,member
            update = admin,member
            delete = !

            [x_case_insensitive]
            create = admin,Member
            read = admin,Member
            update = admin,Member
            delete = admin,Member

            [x_foo_matcher]
            create = admin
            read = admin
            update = admin
            delete = admin

            [x_foo_*]
            create = @
            read = @
            update = @
            delete = @

            [.*]
            create = admin
            read = admin
            update = admin
            delete = admin
            """))

        # Create policies-based property protection file
        property_file_policies = os.path.join(
            conf_dir, 'property-protections-policies.conf')
        with open(property_file_policies, 'w') as f:
            f.write(textwrap.dedent("""
            [spl_creator_policy]
            create = glance_creator
            read = glance_creator
            update = context_is_admin
            delete = context_is_admin

            [spl_default_policy]
            create = context_is_admin
            read = default
            update = context_is_admin
            delete = context_is_admin

            [^x_all_permitted.*]
            create = @
            read = @
            update = @
            delete = @

            [^x_none_permitted.*]
            create = !
            read = !
            update = !
            delete = !

            [x_none_read]
            create = context_is_admin
            read = !
            update = !
            delete = !

            [x_none_update]
            create = context_is_admin
            read = context_is_admin
            update = !
            delete = context_is_admin

            [x_none_delete]
            create = context_is_admin
            read = context_is_admin
            update = context_is_admin
            delete = !

            [x_foo_matcher]
            create = context_is_admin
            read = context_is_admin
            update = context_is_admin
            delete = context_is_admin

            [x_foo_*]
            create = @
            read = @
            update = @
            delete = @

            [.*]
            create = context_is_admin
            read = context_is_admin
            update = context_is_admin
            delete = context_is_admin
            """))

        self.property_file_roles = property_file_roles
        self.property_file_policies = property_file_policies

    def setup_stores(self):
        """Configures multiple backend stores.

        This configures the API with three file-backed stores (store1,
        store2, and store3) as well as a os_glance_staging_store for
        imports.

        """
        self.config(enabled_backends={'store1': 'file', 'store2': 'file',
                                      'store3': 'file'})
        glance_store.register_store_opts(CONF,
                                         reserved_stores=wsgi.RESERVED_STORES)
        self.config(default_backend='store1',
                    group='glance_store')
        self.config(filesystem_store_datadir=self._store_dir('store1'),
                    group='store1')
        self.config(filesystem_store_datadir=self._store_dir('store2'),
                    group='store2')
        self.config(filesystem_store_datadir=self._store_dir('store3'),
                    group='store3')
        self.config(filesystem_store_datadir=self._store_dir('staging'),
                    group='os_glance_staging_store')
        self.config(filesystem_store_datadir=self._store_dir('tasks'),
                    group='os_glance_tasks_store')

        glance_store.create_multi_stores(CONF,
                                         reserved_stores=wsgi.RESERVED_STORES)
        glance_store.verify_store()

    def setUp(self, single_store=False, bypass_headers=False):
        super(SynchronousAPIBase, self).setUp()
        self.bypass_headers = bypass_headers

        self.setup_database()
        self.setup_simple_paste()
        if single_store:
            self.setup_single_store()
        else:
            self.setup_stores()

        conf_dir = os.path.join(self.test_dir, 'etc')
        utils.safe_mkdirs(conf_dir)
        self.copy_data_file('schema-image.json', conf_dir)
        self.setup_property_protection_files()

    def copy_data_file(self, file_name, dst_dir):
        src_file_name = os.path.join('glance/tests/etc', file_name)
        shutil.copy(src_file_name, dst_dir)
        dst_file_name = os.path.join(dst_dir, file_name)
        return dst_file_name

    def start_server(self, enable_cache=True, set_worker_url=True,
                     use_fake_auth=False, run_staging_cleaner=False,
                     enable_cors=False, enable_version_negotiation=False):
        """Builds and "starts" the API server.

        Note that this doesn't actually start a separate server process,
        but instead builds the WSGI application directly. The terminology
        is used here to maintain consistency with other test patterns.
        """
        config.set_config_defaults()
        root_app = 'glance-api'
        if enable_version_negotiation:
            root_app = 'glance-api-versionnegotiation'
            self.config(image_cache_dir=self._store_dir('cache'))
        elif enable_cache:
            root_app = 'glance-api-cachemanagement'
            self.config(image_cache_dir=self._store_dir('cache'))

        if enable_cors:
            root_app = 'glance-api-cors'

        if use_fake_auth:
            root_app = 'glance-api-fake'

        if set_worker_url:
            self.config(worker_self_reference_url='http://workerx')

        if run_staging_cleaner:
            cleaner = housekeeping.StagingStoreCleaner(db_api)
            # NOTE(danms): Start thread as a daemon. It is still a
            # single-shot, but this will not block our shutdown if it is
            # running.
            cleanup_thread = threading.Thread(
                target=cleaner.clean_orphaned_staging_residue,
                daemon=True)
            cleanup_thread.start()

        self.api = config.load_paste_app(root_app,
                                         conf_file=self.paste_config)
        self.config(enforce_new_defaults=True,
                    group='oslo_policy')
        self.config(enforce_scope=True,
                    group='oslo_policy')

    def start_scrubber(self, daemon=False, wakeup_time=300,
                       restore=None, raise_error=True):
        self.setup_scrubber_conf(daemon=daemon, wakeup_time=wakeup_time)
        exe_cmd = f"{sys.executable} -m glance.cmd.scrubber"

        # Modify command based on restore and daemon flags
        if restore:
            exe_cmd += f" --restore {restore}"
        if daemon:
            exe_cmd += " --daemon"

        # Prepare the final command string with the config directory
        cmd = f"{exe_cmd} --config-dir {self.test_dir}"

        # Determine if we need to return the process object
        expect_exit = not daemon
        return_process = daemon

        # Execute the command and return the result
        return execute(cmd, raise_error=raise_error, expect_exit=expect_exit,
                       return_process=return_process)

    def _headers(self, custom_headers=None):
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': '932c5c84-02ac-4fe5-a9ba-620af0e2bb96',
            'X-User-Id': 'f9a41d13-0c13-47e9-bee2-ce4e8bfe958e',
            'X-Tenant-Id': self.TENANT,
            'Content-Type': 'application/json',
            'X-Roles': 'admin',
        }
        base_headers.update(custom_headers or {})
        return base_headers

    def api_request(self, method, url, headers=None, data=None,
                    json=None, body_file=None):
        """Perform a request against the API.

        NOTE: Most code should use api_get(), api_post(), api_put(),
              or api_delete() instead!

        :param method: The HTTP method to use (i.e. GET, POST, etc)
        :param url: The *path* part of the URL to call (i.e. /v2/images)
        :param headers: Optional updates to the default set of headers
        :param data: Optional bytes data payload to send (overrides @json)
        :param json: Optional dict structure to be jsonified and sent as
                     the payload (mutually exclusive with @data)
        :param body_file: Optional io.IOBase to provide as the input data
                          stream for the request (overrides @data)
        :returns: A webob.Response object
        """
        if not self.bypass_headers:
            headers = self._headers(headers)
        else:
            # Ensure headers is at least an empty dict, not None
            if headers is None:
                headers = {}
        # Set a base URL for the request so application_url is available
        # Use host_url to ensure application_url is properly set
        req = webob.Request.blank(url, method=method,
                                  headers=headers)
        if not req.application_url:
            req.environ['wsgi.url_scheme'] = 'http'
            req.environ['HTTP_HOST'] = 'localhost'
            req.environ['SERVER_NAME'] = 'localhost'
            req.environ['SERVER_PORT'] = '80'
        if json and not data:
            data = jsonutils.dumps(json).encode()
        if data and not body_file:
            req.body = data
        elif body_file:
            req.body_file = body_file
        return self._call_api(req)

    def api_get(self, url, headers=None, data=None, json=None):
        """Perform a GET request against the API.

        :param url: The *path* part of the URL to call (i.e. /v2/images)
        :param headers: Optional updates to the default set of headers
        :param data: Optional bytes data payload to send (overrides @json)
        :param json: Optional dict structure to be jsonified and sent as
                     the payload (mutually exclusive with @data)
        :returns: A webob.Response object
        """
        return self.api_request('GET', url, headers=headers,
                                data=data, json=json)

    def api_post(self, url, headers=None, data=None, json=None,
                 body_file=None):
        """Perform a POST request against the API.

        :param url: The *path* part of the URL to call (i.e. /v2/images)
        :param headers: Optional updates to the default set of headers
        :param data: Optional bytes data payload to send (overrides @json)
        :param json: Optional dict structure to be jsonified and sent as
                     the payload (mutually exclusive with @data)
        :param body_file: Optional io.IOBase to provide as the input data
                          stream for the request (overrides @data)
        :returns: A webob.Response object
        """
        return self.api_request('POST', url, headers=headers,
                                data=data, json=json,
                                body_file=body_file)

    def api_put(self, url, headers=None, data=None, json=None, body_file=None):
        """Perform a PUT request against the API.

        :param url: The *path* part of the URL to call (i.e. /v2/images)
        :param headers: Optional updates to the default set of headers
        :param data: Optional bytes data payload to send (overrides @json,
                     mutually exclusive with body_file)
        :param json: Optional dict structure to be jsonified and sent as
                     the payload (mutually exclusive with @data)
        :param body_file: Optional io.IOBase to provide as the input data
                          stream for the request (overrides @data)
        :returns: A webob.Response object
        """
        return self.api_request('PUT', url, headers=headers,
                                data=data, json=json,
                                body_file=body_file)

    def api_delete(self, url, headers=None, data=None, json=None):
        """Perform a DELETE request against the API.

        :param url: The *path* part of the URL to call (i.e. /v2/images)
        :param headers: Optional updates to the default set of headers
        :param data: Optional bytes data payload to send (overrides @json)
        :param json: Optional dict structure to be jsonified and sent as
                     the payload (mutually exclusive with @data)
        :returns: A webob.Response object
        """
        return self.api_request('DELETE', url, headers=headers,
                                data=data, json=json)

    def _call_api(self, req):
        """Call the WSGI application and handle Controller responses.

        This wraps the WSGI application call and handles cases where the
        version negotiation middleware returns a Controller object instead
        of a Response.

        :param req: A webob.Request object
        :returns: A webob.Response object
        """
        response = self.api(req)
        # The version negotiation filter may return a Controller for
        # unknown versions, which needs to be called to get the Response
        if hasattr(response, '__call__') and not hasattr(
                response, 'status_code'):
            response = response(req)
        return response

    def api_patch(self, url, patches, headers=None):
        """Perform a PATCH request against the API.

        :param url: The *path* part of the URL to call (i.e. /v2/images)
        :param patches: One or more patch dicts
        :param headers: Optional updates to the default set of headers
        :returns: A webob.Response object
        """
        json = patches if isinstance(patches, list) else list(patches)

        if not headers:
            headers = {}
        headers['Content-Type'] = \
            'application/openstack-images-v2.1-json-patch'
        return self.api_request('PATCH', url, headers=headers,
                                json=json)

    def _import_copy(self, image_id, stores, headers=None):
        """Do an import of image_id to the given stores."""
        body = {'method': {'name': 'copy-image'},
                'stores': stores,
                'all_stores': False}

        return self.api_post(
            '/v2/images/%s/import' % image_id,
            headers=headers,
            json=body)

    def _import_direct(self, image_id, stores, headers=None):
        """Do an import of image_id to the given stores."""
        body = {'method': {'name': 'glance-direct'},
                'stores': stores,
                'all_stores': False}

        return self.api_post(
            '/v2/images/%s/import' % image_id,
            headers=headers,
            json=body)

    def _import_web_download(self, image_id, stores, url, headers=None):
        """Do an import of image_id to the given stores."""
        body = {'method': {'name': 'web-download',
                           'uri': url},
                'stores': stores,
                'all_stores': False}

        return self.api_post(
            '/v2/images/%s/import' % image_id,
            headers=headers,
            json=body)

    def _create_and_upload(self, data_iter=None, expected_code=204,
                           visibility=None):
        data = {
            'name': 'foo',
            'container_format': 'bare',
            'disk_format': 'raw'
        }
        if visibility:
            data['visibility'] = visibility

        resp = self.api_post('/v2/images',
                             json=data)
        self.assertEqual(201, resp.status_code, resp.text)
        image = jsonutils.loads(resp.text)

        if data_iter:
            resp = self.api_put(
                '/v2/images/%s/file' % image['id'],
                headers={'Content-Type': 'application/octet-stream'},
                body_file=data_iter)
        else:
            resp = self.api_put(
                '/v2/images/%s/file' % image['id'],
                headers={'Content-Type': 'application/octet-stream'},
                data=b'IMAGEDATA')
        self.assertEqual(expected_code, resp.status_code)

        return image['id']

    def _create_and_stage(self, data_iter=None, expected_code=204,
                          visibility=None, extra={}):
        data = {
            'name': 'foo',
            'container_format': 'bare',
            'disk_format': 'raw',
        }
        if visibility:
            data['visibility'] = visibility

        data.update(extra)
        resp = self.api_post('/v2/images',
                             json=data)
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
        self.assertEqual(expected_code, resp.status_code)

        return image['id']

    def _wait_for_import(self, image_id, retries=10):
        for i in range(0, retries):
            image = self.api_get('/v2/images/%s' % image_id).json
            if not image.get('os_glance_import_task'):
                break
            self.addDetail('Create-Import task id',
                           ttc.text_content(image['os_glance_import_task']))
            time.sleep(1)

        self.assertIsNone(image.get('os_glance_import_task'),
                          'Timed out waiting for task to complete')

        return image

    def _create_and_import(self, stores=[], data_iter=None, expected_code=202,
                           visibility=None, extra={}):
        """Create an image, stage data, and import into the given stores.

        :returns: image_id
        """
        image_id = self._create_and_stage(data_iter=data_iter,
                                          visibility=visibility,
                                          extra=extra)

        resp = self._import_direct(image_id, stores)
        self.assertEqual(expected_code, resp.status_code)

        if expected_code >= 400:
            return image_id

        # Make sure it becomes active
        image = self._wait_for_import(image_id)
        self.assertEqual('active', image['status'])

        return image_id

    def _get_latest_task(self, image_id):
        tasks = self.api_get('/v2/images/%s/tasks' % image_id).json['tasks']
        tasks = sorted(tasks, key=lambda t: t['updated_at'])
        self.assertGreater(len(tasks), 0)
        return tasks[-1]

    def _wait_for_task_failure(self, image_id, max_sec=40, delay_sec=0.2,
                               start_delay_sec=0):
        """Wait for import task to fail.

        :param image_id: The image ID to check
        :param max_sec: Maximum seconds to wait (default: 40)
        :param delay_sec: Seconds to sleep between checks (default: 0.2)
        :param start_delay_sec: Seconds to wait before first check (default: 0)
        :returns: The task dict from the API response
        """
        done_time = time.time() + max_sec
        if start_delay_sec:
            time.sleep(start_delay_sec)

        while time.time() <= done_time:
            try:
                task = self._get_latest_task(image_id)
                if task['status'] == 'failure':
                    return task
                elif task['status'] == 'success':
                    self.fail("Import unexpectedly succeeded "
                              "(task status=success)")
            except (KeyError, IndexError):
                # Task may not exist yet, continue checking
                pass

            time.sleep(delay_sec)

        task = self._get_latest_task(image_id)
        self.assertEqual('failure', task['status'])
        return task

    def _create(self):
        return self.api_post('/v2/images',
                             json={'name': 'foo',
                                   'container_format': 'bare',
                                   'disk_format': 'raw'})

    def _create_metadef_resource(self, path=None, data=None,
                                 expected_code=201):
        resp = self.api_post(path,
                             json=data)
        md_resource = jsonutils.loads(resp.text)
        self.assertEqual(expected_code, resp.status_code)
        return md_resource
