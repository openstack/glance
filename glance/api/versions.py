# Copyright 2012 OpenStack Foundation.
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

import http.client
import urllib

from oslo_config import cfg
from oslo_log import log as logging
from oslo_serialization import jsonutils
import webob.dec

from glance.common import wsgi
from glance.i18n import _


versions_opts = [
    cfg.StrOpt('public_endpoint',
               help=_("""
Public url endpoint to use for Glance versions response.

This is the public url endpoint that will appear in the Glance
"versions" response. If no value is specified, the endpoint that is
displayed in the version's response is that of the host running the
API service. Change the endpoint to represent the proxy URL if the
API service is running behind a proxy. If the service is running
behind a load balancer, add the load balancer's URL for this value.

Possible values:
    * None
    * Proxy URL
    * Load balancer URL

Related options:
    * None

""")),
]

CONF = cfg.CONF
CONF.register_opts(versions_opts)

LOG = logging.getLogger(__name__)


class Controller(object):

    """A wsgi controller that reports which API versions are supported."""

    def index(self, req, explicit=False):
        """Respond to a request for all OpenStack API versions."""
        def build_version_object(version, path, status):
            url = CONF.public_endpoint or req.application_url
            # Always add '/' to url end for urljoin href url
            url = url.rstrip('/') + '/'
            href = urllib.parse.urljoin(url, path).rstrip('/') + '/'
            return {
                'id': 'v%s' % version,
                'status': status,
                'links': [
                    {
                        'rel': 'self',
                        'href': '%s' % href,
                    },
                ],
            }

        version_objs = []
        if CONF.image_cache_dir:
            version_objs.extend([
                build_version_object('2.16', 'v2', 'CURRENT'),
                build_version_object('2.15', 'v2', 'SUPPORTED'),
                build_version_object('2.14', 'v2', 'SUPPORTED'),
            ])
        else:
            version_objs.extend([
                build_version_object('2.15', 'v2', 'CURRENT'),
            ])
        if CONF.enabled_backends:
            version_objs.extend([
                build_version_object('2.13', 'v2', 'SUPPORTED'),
                build_version_object('2.12', 'v2', 'SUPPORTED'),
                build_version_object('2.11', 'v2', 'SUPPORTED'),
                build_version_object('2.10', 'v2', 'SUPPORTED'),
                build_version_object('2.9', 'v2', 'SUPPORTED'),
                build_version_object('2.8', 'v2', 'SUPPORTED'),
            ])
        else:
            version_objs.extend([
                build_version_object('2.9', 'v2', 'SUPPORTED'),
            ])
        version_objs.extend([
            build_version_object('2.7', 'v2', 'SUPPORTED'),
            build_version_object('2.6', 'v2', 'SUPPORTED'),
            build_version_object('2.5', 'v2', 'SUPPORTED'),
            build_version_object('2.4', 'v2', 'SUPPORTED'),
            build_version_object('2.3', 'v2', 'SUPPORTED'),
            build_version_object('2.2', 'v2', 'SUPPORTED'),
            build_version_object('2.1', 'v2', 'SUPPORTED'),
            build_version_object('2.0', 'v2', 'SUPPORTED'),
        ])

        status = explicit and http.client.OK or http.client.MULTIPLE_CHOICES
        response = webob.Response(request=req,
                                  status=status,
                                  content_type='application/json')
        response.body = jsonutils.dump_as_bytes(dict(versions=version_objs))
        return response

    @webob.dec.wsgify(RequestClass=wsgi.Request)
    def __call__(self, req):
        return self.index(req)


def create_resource(conf):
    return wsgi.Resource(Controller())
