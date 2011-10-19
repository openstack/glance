# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack, LLC
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

import keystone.manage

DEFAULT_FIXTURE = [
# Tenants
    ('tenant', 'add', 'openstack'),
    ('tenant', 'add', 'pattieblack'),
    ('tenant', 'add', 'froggy'),
    ('tenant', 'add', 'bacon'),
    ('tenant', 'add', 'prosciutto'),
# Users
    ('user', 'add', 'pattieblack', 'secrete', 'pattieblack'),
    ('user', 'add', 'froggy', 'secrete', 'froggy'),
    ('user', 'add', 'bacon', 'secrete', 'bacon'),
    ('user', 'add', 'prosciutto', 'secrete', 'prosciutto'),
    ('user', 'add', 'admin', 'secrete', 'openstack'),
# Roles
    ('role', 'add', 'Admin'),
    ('role', 'add', 'KeystoneServiceAdmin'),
    ('role', 'grant', 'Admin', 'admin'),
    ('role', 'grant', 'KeystoneServiceAdmin', 'admin'),
# Tokens
    ('token', 'add', '887665443383', 'pattieblack', 'pattieblack',
     '2015-02-05T00:00'),
    ('token', 'add', '383344566788', 'froggy', 'froggy',
     '2015-02-05T00:00'),
    ('token', 'add', '111111111111', 'bacon', 'bacon',
     '2015-02-05T00:00'),
    ('token', 'add', '222222222222', 'prosciutto', 'prosciutto',
     '2015-02-05T00:00'),
    ('token', 'add', '999888777666', 'admin', 'openstack',
     '2015-02-05T00:00'),
#Services
    #2 Service Name:swift Type:object-store
    ('service', 'add', 'swift',
        'object-store', 'Swift-compatible service'),
    ('service', 'add', 'object_store',
        'object-store', 'Swift-compatible service'),
    #3 Service Name:cdn Type:object-store
    ('service', 'add', 'cdn',
        'object-store', 'Swift-compatible service'),
    #4 Service Name:nova Type:compute
    ('service', 'add', 'nova',
        'compute', 'OpenStack Compute Service'),
    ('service', 'add', 'compute',
        'compute', 'OpenStack Compute Service'),
    ('service', 'add', 'compute_v1',
        'compute', 'OpenStack Compute Service'),
    #5 Service Name:nova_compat Type:Compute
    ('service', 'add', 'nova_compat',
        'compute', 'OpenStack Compute Service'),
    #6 Service Name:glance Type:image
    ('service', 'add', 'glance',
        'image', 'OpenStack Image Service'),
    ('service', 'add', 'image',
        'image', 'OpenStack Image Service'),
    #7 Service Name:keystone Type:identity
    ('service', 'add', 'identity',
        'identity', 'OpenStack Identity Service'),
# Keeping for compatibility for a while till dashboard catches up
    ('endpointTemplates', 'add', 'RegionOne', 'swift',
        'http://swift.publicinternets.com/v1/AUTH_%tenant_id%',
        'http://swift.admin-nets.local:8080/',
        'http://127.0.0.1:8080/v1/AUTH_%tenant_id%', '1', '0'),
    ('endpointTemplates', 'add', 'RegionOne', 'nova_compat',
        'http://nova.publicinternets.com/v1.0/',
        'http://127.0.0.1:8774/v1.0', 'http://localhost:8774/v1.0', '1', '0'),
    ('endpointTemplates', 'add', 'RegionOne', 'nova',
        'http://nova.publicinternets.com/v1.1/', 'http://127.0.0.1:8774/v1.1',
        'http://localhost:8774/v1.1', '1', '0'),
    ('endpointTemplates', 'add', 'RegionOne', 'glance',
        'http://glance.publicinternets.com/v1.1/%tenant_id%',
        'http://nova.admin-nets.local/v1.1/%tenant_id%',
        'http://127.0.0.1:9292/v1.1/%tenant_id%', '1', '0'),
    ('endpointTemplates', 'add', 'RegionOne', 'cdn',
        'http://cdn.publicinternets.com/v1.1/%tenant_id%',
        'http://cdn.admin-nets.local/v1.1/%tenant_id%',
        'http://127.0.0.1:7777/v1.1/%tenant_id%', '1', '0'),
# endpointTemplates
    ('endpointTemplates', 'add', 'RegionOne', 'object_store',
        'http://swift.publicinternets.com/v1/AUTH_%tenant_id%',
        'http://swift.admin-nets.local:8080/',
        'http://127.0.0.1:8080/v1/AUTH_%tenant_id%', '1', '0'),
    ('endpointTemplates', 'add', 'RegionOne', 'compute',
        'http://nova.publicinternets.com/v1.0/', 'http://127.0.0.1:8774/v1.0',
        'http://localhost:8774/v1.0', '1', '0'),
    ('endpointTemplates', 'add', 'RegionOne', 'compute_v1',
        'http://nova.publicinternets.com/v1.1/', 'http://127.0.0.1:8774/v1.1',
        'http://localhost:8774/v1.1', '1', '0'),
    ('endpointTemplates', 'add', 'RegionOne', 'image',
        'http://glance.publicinternets.com/v1.1/%tenant_id%',
        'http://nova.admin-nets.local/v1.1/%tenant_id%',
        'http://127.0.0.1:9292/v1.1/%tenant_id%', '1', '0'),
    ('endpointTemplates', 'add', 'RegionOne', 'cdn',
        'http://cdn.publicinternets.com/v1.1/%tenant_id%',
        'http://cdn.admin-nets.local/v1.1/%tenant_id%',
        'http://127.0.0.1:7777/v1.1/%tenant_id%', '1', '0'),
# Tenant endpointsGlobal endpoint not added
    ('endpoint', 'add', 'openstack', '1'),
    ('endpoint', 'add', 'openstack', '2'),
    ('endpoint', 'add', 'openstack', '3'),
    ('endpoint', 'add', 'openstack', '4'),
    ('endpoint', 'add', 'openstack', '5'),
    ('endpoint', 'add', 'pattieblack', '1'),
    ('endpoint', 'add', 'pattieblack', '2'),
    ('endpoint', 'add', 'pattieblack', '3'),
    ('endpoint', 'add', 'pattieblack', '4'),
    ('endpoint', 'add', 'pattieblack', '5'),
    ('endpoint', 'add', 'froggy', '1'),
    ('endpoint', 'add', 'froggy', '2'),
    ('endpoint', 'add', 'froggy', '3'),
    ('endpoint', 'add', 'froggy', '4'),
    ('endpoint', 'add', 'froggy', '5'),
    ('endpoint', 'add', 'bacon', '1'),
    ('endpoint', 'add', 'bacon', '2'),
    ('endpoint', 'add', 'bacon', '3'),
    ('endpoint', 'add', 'bacon', '4'),
    ('endpoint', 'add', 'bacon', '5'),
    ('endpoint', 'add', 'prosciutto', '1'),
    ('endpoint', 'add', 'prosciutto', '2'),
    ('endpoint', 'add', 'prosciutto', '3'),
    ('endpoint', 'add', 'prosciutto', '4'),
    ('endpoint', 'add', 'prosciutto', '5'),
]


def load_fixture(fixture=DEFAULT_FIXTURE, args=None):
    keystone.manage.parse_args(args)
    for cmd in fixture:
        keystone.manage.process(*cmd)


def main():
    load_fixture()


if __name__ == '__main__':
    main()
