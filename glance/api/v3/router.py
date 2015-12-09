# Copyright (c) 2015 Mirantis, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from oslo_config import cfg
from oslo_log import log as logging
from oslo_log import versionutils

from glance.common import wsgi
from glance.i18n import _LW

CONF = cfg.CONF

LOG = logging.getLogger(__name__)

"""v3 controller stub

Since Glance Artifact Service was released in Liberty as experimental Glance v3
API, its router was referenced in paste configuration as glance.api.v3.router
In Mitaka the Artifacts Service was moved into a standalone process and its
router was renamed to glance.api.artifacts.router.
However, in existing deployments the glance-api-paste.ini may still reference
the glance.api.v3.router. To not break these deployments this stub is included
to redirect the v3 request to glare service (if it is present) or return a 410
otherwise.
This stub controller should be removed in future releases.
"""


class API(wsgi.Router):
    def __init__(self, mapper):
        versionutils.report_deprecated_feature(
            LOG,
            _LW('/v3 controller is deprecated and will be removed from '
                'glance-api soon. Remove the reference to it from '
                'glance-api-paste.ini configuration file and use Glance '
                'Artifact Service API instead'))
        redirector = self._get_redirector()
        mapper.connect(None, "/artifacts",
                       controller=redirector, action='redirect')
        mapper.connect(None, "/artifacts/{path:.*}",
                       controller=redirector, action='redirect')
        super(API, self).__init__(mapper)

    def _get_redirector(self):
        return wsgi.Resource(RedirectController(),
                             serializer=RedirectResponseSerializer())


class RedirectController(object):
    def redirect(self, req, path=None):
        try:
            glare_endpoint = next((s['endpoints']
                                   for s in req.context.service_catalog
                                   if s['type'] == 'artifact'))[0]['publicURL']
            if path:
                path = '/' + path
            return '{0}/v0.1/artifacts{1}'.format(glare_endpoint, path or "")
        except StopIteration:
            return None


class RedirectResponseSerializer(wsgi.JSONResponseSerializer):
    def default(self, response, res):
        if res:
            response.location = res
            response.status_int = 301
        else:
            response.status_int = 410
