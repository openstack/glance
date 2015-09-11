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

from oslo_config import cfg
from oslo_serialization import jsonutils
import six
from six.moves import http_client
import webob.dec

from glance.common import wsgi
from glance import i18n

_ = i18n._

versions_opts = [
    cfg.StrOpt('public_endpoint', default=None,
               help=_('Public url to use for versions endpoint. The default '
                      'is None, which will use the request\'s host_url '
                      'attribute to populate the URL base. If Glance is '
                      'operating behind a proxy, you will want to change '
                      'this to represent the proxy\'s URL.')),
]

CONF = cfg.CONF
CONF.register_opts(versions_opts)


class Controller(object):

    """A wsgi controller that reports which API versions are supported."""

    def index(self, req, explicit=False):
        """Respond to a request for all OpenStack API versions."""
        def build_version_object(version, path, status):
            url = CONF.public_endpoint or req.host_url
            return {
                'id': 'v%s' % version,
                'status': status,
                'links': [
                    {
                        'rel': 'self',
                        'href': '%s/%s/' % (url, path),
                    },
                ],
            }

        version_objs = []
        if CONF.enable_v3_api:
            version_objs.append(
                build_version_object(3.0, 'v3', 'EXPERIMENTAL'))
        if CONF.enable_v2_api:
            version_objs.extend([
                build_version_object(2.3, 'v2', 'CURRENT'),
                build_version_object(2.2, 'v2', 'SUPPORTED'),
                build_version_object(2.1, 'v2', 'SUPPORTED'),
                build_version_object(2.0, 'v2', 'SUPPORTED'),
            ])
        if CONF.enable_v1_api:
            version_objs.extend([
                build_version_object(1.1, 'v1', 'SUPPORTED'),
                build_version_object(1.0, 'v1', 'SUPPORTED'),
            ])

        status = explicit and http_client.OK or http_client.MULTIPLE_CHOICES
        response = webob.Response(request=req,
                                  status=status,
                                  content_type='application/json')
        json = jsonutils.dumps(dict(versions=version_objs))
        if six.PY3:
            json = json.encode('utf-8')
        response.body = json
        return response

    @webob.dec.wsgify(RequestClass=wsgi.Request)
    def __call__(self, req):
        return self.index(req)


def create_resource(conf):
    return wsgi.Resource(Controller())
