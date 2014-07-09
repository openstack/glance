# Copyright 2014 Hewlett-Packard Development Company, L.P.
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

from glance.db.registry.api import *  # noqa
from glance.common.rpc import RPCClient
from glance.registry.client.v2 import api
from glance.registry.client.v2 import client


def patched_bulk_request(self, commands):
    # We add some auth headers which are typically
    # added by keystone. This is required when testing
    # without keystone, otherwise the tests fail.
    # We use the 'trusted-auth' deployment flavour
    # for testing so that these headers are interpreted
    # as expected (ie the same way as if keystone was
    # present)
    body = self._serializer.to_json(commands)
    headers = {"X-Identity-Status": "Confirmed", 'X-Roles': 'member'}
    if self.context.user is not None:
        headers['X-User-Id'] = self.context.user
    if self.context.tenant is not None:
        headers['X-Tenant-Id'] = self.context.tenant
    response = super(RPCClient, self).do_request('POST',
                                                 self.base_path,
                                                 body,
                                                 headers=headers)
    return self._deserializer.from_json(response.read())


def client_wrapper(func):
    def call(context):
        reg_client = func(context)
        reg_client.context = context
        return reg_client
    return call

client.RegistryClient.bulk_request = patched_bulk_request

api.get_registry_client = client_wrapper(api.get_registry_client)
