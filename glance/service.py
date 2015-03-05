#!/usr/bin/env python
#
# Copyright 2012-2014 eNovance <licensing@enovance.com>
# Copyright (c) 2014 Hewlett-Packard Development Company, L.P.
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

import os
import socket
import sys

from oslo.config import cfg
from oslo import i18n
import oslo.messaging
from oslo_log import log

CONF = cfg.CONF

OPTS = [
    cfg.StrOpt('host',
               default=socket.gethostname(),
               help='Name of this node, which must be valid in an AMQP '
               'key. Can be an opaque identifier. For ZeroMQ only, must '
               'be a valid host name, FQDN, or IP address.'),
    cfg.IntOpt('listener_workers',
               default=1,
               help='Number of workers for notification service. A single '
               'notification agent is enabled by default.'),
    cfg.IntOpt('http_timeout',
               default=600,
               help='Timeout seconds for HTTP requests. Set it to None to '
                    'disable timeout.'),
]
CONF.register_opts(OPTS)

CLI_OPTS = [
    cfg.StrOpt('os-username',
               deprecated_group="DEFAULT",
               default=os.environ.get('OS_USERNAME', 'glance'),
               help='User name to use for OpenStack service access.'),
    cfg.StrOpt('os-password',
               deprecated_group="DEFAULT",
               secret=True,
               default=os.environ.get('OS_PASSWORD', 'admin'),
               help='Password to use for OpenStack service access.'),
    cfg.StrOpt('os-tenant-id',
               deprecated_group="DEFAULT",
               default=os.environ.get('OS_TENANT_ID', ''),
               help='Tenant ID to use for OpenStack service access.'),
    cfg.StrOpt('os-tenant-name',
               deprecated_group="DEFAULT",
               default=os.environ.get('OS_TENANT_NAME', 'admin'),
               help='Tenant name to use for OpenStack service access.'),
    cfg.StrOpt('os-cacert',
               default=os.environ.get('OS_CACERT'),
               help='Certificate chain for SSL validation.'),
    cfg.StrOpt('os-auth-url',
               deprecated_group="DEFAULT",
               default=os.environ.get('OS_AUTH_URL',
                                      'http://localhost:5000/v2.0'),
               help='Auth URL to use for OpenStack service access.'),
    cfg.StrOpt('os-region-name',
               deprecated_group="DEFAULT",
               default=os.environ.get('OS_REGION_NAME'),
               help='Region name to use for OpenStack service endpoints.'),
    cfg.StrOpt('os-endpoint-type',
               default=os.environ.get('OS_ENDPOINT_TYPE', 'publicURL'),
               help='Type of endpoint in Identity service catalog to use for '
                    'communication with OpenStack services.'),
    cfg.BoolOpt('insecure',
                default=False,
                help='Disables X.509 certificate validation when an '
                     'SSL connection to Identity Service is established.'),
]
CONF.register_cli_opts(CLI_OPTS, group="service_credentials")

LOG = log.getLogger(__name__)
_DEFAULT_LOG_LEVELS = ['keystonemiddleware=WARN', 'stevedore=WARN']


class WorkerException(Exception):
    """Exception for errors relating to service workers."""


def get_workers(name):
    return 1


def prepare_service(argv=None):
    i18n.enable_lazy()
    log.set_defaults(_DEFAULT_LOG_LEVELS)
    log.register_options(CONF)
    if argv is None:
        argv = sys.argv
    CONF(argv[1:], project='glance-search')
    log.setup(cfg.CONF, 'glance-search')
    oslo.messaging.set_transport_defaults('glance')
