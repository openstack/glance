# Copyright 2013 OpenStack Foundation
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

import os
import sys

import oslo_utils.strutils as strutils

from glance import i18n

try:
    import dns  # NOQA
except ImportError:
    dnspython_installed = False
else:
    dnspython_installed = True


def fix_greendns_ipv6():
    if dnspython_installed:
        # All of this is because if dnspython is present in your environment
        # then eventlet monkeypatches socket.getaddrinfo() with an
        # implementation which doesn't work for IPv6. What we're checking here
        # is that the magic environment variable was set when the import
        # happened.
        nogreendns = 'EVENTLET_NO_GREENDNS'
        flag = os.environ.get(nogreendns, '')
        if 'eventlet' in sys.modules and not strutils.bool_from_string(flag):
            msg = i18n._("It appears that the eventlet module has been "
                         "imported prior to setting %s='yes'. It is currently "
                         "necessary to disable eventlet.greendns "
                         "if using ipv6 since eventlet.greendns currently "
                         "breaks with ipv6 addresses. Please ensure that "
                         "eventlet is not imported prior to this being set.")
            raise ImportError(msg % (nogreendns))

        os.environ[nogreendns] = 'yes'


i18n.enable_lazy()
fix_greendns_ipv6()
