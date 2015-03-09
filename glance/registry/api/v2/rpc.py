# Copyright 2013 Red Hat, Inc.
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
RPC Controller
"""

from oslo_config import cfg
from oslo_log import log as logging

from glance.common import rpc
from glance.common import wsgi
import glance.db
from glance import i18n


LOG = logging.getLogger(__name__)
_ = i18n._

CONF = cfg.CONF


class Controller(rpc.Controller):

    def __init__(self, raise_exc=False):
        super(Controller, self).__init__(raise_exc)

        # NOTE(flaper87): Avoid using registry's db
        # driver for the registry service. It would
        # end up in an infinite loop.
        if CONF.data_api == "glance.db.registry.api":
            msg = _("Registry service can't use %s") % CONF.data_api
            raise RuntimeError(msg)

        # NOTE(flaper87): Register the
        # db_api as a resource to expose.
        db_api = glance.db.get_api()
        self.register(glance.db.unwrap(db_api))


def create_resource():
    """Images resource factory method."""
    deserializer = rpc.RPCJSONDeserializer()
    serializer = rpc.RPCJSONSerializer()
    return wsgi.Resource(Controller(), deserializer, serializer)
