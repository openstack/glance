# Copyright (c) 2014 OpenStack Foundation.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import pkg_resources
from testtools import matchers

from glance import opts
from glance.tests import utils


class OptsTestCase(utils.BaseTestCase):

    def _check_opt_groups(self, opt_list, expected_opt_groups):
        self.assertThat(opt_list, matchers.HasLength(len(expected_opt_groups)))

        groups = [g for (g, _l) in opt_list]
        self.assertThat(groups, matchers.HasLength(len(expected_opt_groups)))

        for idx, group in enumerate(groups):
            self.assertEqual(expected_opt_groups[idx], group)

    def _check_opt_names(self, opt_list, expected_opt_names):
        opt_names = [o.name for (g, l) in opt_list for o in l]
        self.assertThat(opt_names, matchers.HasLength(len(expected_opt_names)))

        for opt in opt_names:
            self.assertIn(opt, expected_opt_names)

    def _test_entry_point(self, namespace,
                          expected_opt_groups, expected_opt_names):
        opt_list = None
        for ep in pkg_resources.iter_entry_points('oslo.config.opts'):
            if ep.name == namespace:
                list_fn = ep.load()
                opt_list = list_fn()
                break

        self.assertIsNotNone(opt_list)

        self._check_opt_groups(opt_list, expected_opt_groups)
        self._check_opt_names(opt_list, expected_opt_names)

    def test_list_api_opts(self):
        opt_list = opts.list_api_opts()
        expected_opt_groups = [
            None,
            'image_format',
            'task',
            'store_type_location_strategy',
            'paste_deploy'
        ]
        expected_opt_names = [
            'owner_is_tenant',
            'admin_role',
            'allow_anonymous_access',
            'allow_additional_image_properties',
            'image_member_quota',
            'image_property_quota',
            'image_tag_quota',
            'image_location_quota',
            'data_api',
            'limit_param_default',
            'api_limit_max',
            'show_image_direct_url',
            'show_multiple_locations',
            'image_size_cap',
            'user_storage_quota',
            'enable_v1_api',
            'enable_v2_api',
            'enable_v1_registry',
            'enable_v2_registry',
            'pydev_worker_debug_host',
            'pydev_worker_debug_port',
            'metadata_encryption_key',
            'location_strategy',
            'property_protection_file',
            'property_protection_rule_format',
            'allowed_rpc_exception_modules',
            'bind_host',
            'bind_port',
            'workers',
            'max_header_line',
            'backlog',
            'tcp_keepidle',
            'ca_file',
            'cert_file',
            'key_file',
            'image_cache_sqlite_db',
            'image_cache_driver',
            'image_cache_max_size',
            'image_cache_stall_time',
            'image_cache_dir',
            'default_publisher_id',
            'registry_host',
            'registry_port',
            'use_user_token',
            'admin_user',
            'admin_password',
            'admin_tenant_name',
            'auth_url',
            'auth_strategy',
            'auth_region',
            'registry_client_protocol',
            'registry_client_key_file',
            'registry_client_cert_file',
            'registry_client_ca_file',
            'registry_client_insecure',
            'registry_client_timeout',
            'send_identity_headers',
            'scrubber_datadir',
            'scrub_time',
            'cleanup_scrubber',
            'delayed_delete',
            'cleanup_scrubber_time',
            'container_formats',
            'disk_formats',
            'task_time_to_live',
            'task_executor',
            'work_dir',
            'store_type_preference',
            'flavor',
            'config_file',
            'public_endpoint',
            'digest_algorithm',
            'http_keepalive',
            'disabled_notifications',
        ]

        self._check_opt_groups(opt_list, expected_opt_groups)
        self._check_opt_names(opt_list, expected_opt_names)
        self._test_entry_point('glance.api',
                               expected_opt_groups, expected_opt_names)

    def test_list_registry_opts(self):
        opt_list = opts.list_registry_opts()
        expected_opt_groups = [
            None,
            'paste_deploy'
        ]
        expected_opt_names = [
            'owner_is_tenant',
            'admin_role',
            'allow_anonymous_access',
            'allow_additional_image_properties',
            'image_member_quota',
            'image_property_quota',
            'image_tag_quota',
            'image_location_quota',
            'data_api',
            'limit_param_default',
            'api_limit_max',
            'show_image_direct_url',
            'show_multiple_locations',
            'image_size_cap',
            'user_storage_quota',
            'enable_v1_api',
            'enable_v2_api',
            'enable_v1_registry',
            'enable_v2_registry',
            'pydev_worker_debug_host',
            'pydev_worker_debug_port',
            'metadata_encryption_key',
            'bind_host',
            'bind_port',
            'backlog',
            'tcp_keepidle',
            'ca_file',
            'cert_file',
            'key_file',
            'workers',
            'max_header_line',
            'flavor',
            'config_file',
            'digest_algorithm',
            'http_keepalive',
        ]

        self._check_opt_groups(opt_list, expected_opt_groups)
        self._check_opt_names(opt_list, expected_opt_names)
        self._test_entry_point('glance.registry',
                               expected_opt_groups, expected_opt_names)

    def test_list_scrubber_opts(self):
        opt_list = opts.list_scrubber_opts()
        expected_opt_groups = [
            None
        ]
        expected_opt_names = [
            'allow_additional_image_properties',
            'image_member_quota',
            'image_property_quota',
            'image_tag_quota',
            'image_location_quota',
            'data_api',
            'limit_param_default',
            'api_limit_max',
            'show_image_direct_url',
            'show_multiple_locations',
            'image_size_cap',
            'user_storage_quota',
            'enable_v1_api',
            'enable_v2_api',
            'enable_v1_registry',
            'enable_v2_registry',
            'pydev_worker_debug_host',
            'pydev_worker_debug_port',
            'metadata_encryption_key',
            'scrubber_datadir',
            'scrub_time',
            'cleanup_scrubber',
            'delayed_delete',
            'cleanup_scrubber_time',
            'wakeup_time',
            'daemon',
            'use_user_token',
            'admin_user',
            'admin_password',
            'admin_tenant_name',
            'auth_url',
            'auth_strategy',
            'auth_region',
            'registry_host',
            'registry_port',
            'digest_algorithm',
        ]

        self._check_opt_groups(opt_list, expected_opt_groups)
        self._check_opt_names(opt_list, expected_opt_names)
        self._test_entry_point('glance.scrubber',
                               expected_opt_groups, expected_opt_names)

    def test_list_cache_opts(self):
        opt_list = opts.list_cache_opts()
        expected_opt_groups = [
            None
        ]
        expected_opt_names = [
            'allow_additional_image_properties',
            'image_member_quota',
            'image_property_quota',
            'image_tag_quota',
            'image_location_quota',
            'data_api',
            'limit_param_default',
            'api_limit_max',
            'show_image_direct_url',
            'show_multiple_locations',
            'image_size_cap',
            'user_storage_quota',
            'enable_v1_api',
            'enable_v2_api',
            'enable_v1_registry',
            'enable_v2_registry',
            'pydev_worker_debug_host',
            'pydev_worker_debug_port',
            'metadata_encryption_key',
            'image_cache_sqlite_db',
            'image_cache_driver',
            'image_cache_max_size',
            'image_cache_stall_time',
            'image_cache_dir',
            'registry_host',
            'registry_port',
            'use_user_token',
            'admin_user',
            'admin_password',
            'admin_tenant_name',
            'auth_url',
            'auth_strategy',
            'auth_region',
            'digest_algorithm',
        ]

        self._check_opt_groups(opt_list, expected_opt_groups)
        self._check_opt_names(opt_list, expected_opt_names)
        self._test_entry_point('glance.cache',
                               expected_opt_groups, expected_opt_names)

    def test_list_manage_opts(self):
        opt_list = opts.list_manage_opts()
        expected_opt_groups = [
            None,
        ]
        expected_opt_names = [
        ]

        self._check_opt_groups(opt_list, expected_opt_groups)
        self._check_opt_names(opt_list, expected_opt_names)
        self._test_entry_point('glance.manage',
                               expected_opt_groups, expected_opt_names)
