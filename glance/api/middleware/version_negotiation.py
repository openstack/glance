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
A filter middleware that inspects the requested URI for a version string
and/or Accept headers and attempts to negotiate an API controller to
return
"""

from oslo_config import cfg
from oslo_log import log as logging

from glance.api import versions
from glance.common import wsgi
from glance import i18n

CONF = cfg.CONF

LOG = logging.getLogger(__name__)
_ = i18n._
_LW = i18n._LW


class VersionNegotiationFilter(wsgi.Middleware):

    def __init__(self, app):
        self.versions_app = versions.Controller()
        super(VersionNegotiationFilter, self).__init__(app)

    def process_request(self, req):
        """Try to find a version first in the accept header, then the URL"""
        msg = _("Determining version of request: %(method)s %(path)s"
                " Accept: %(accept)s")
        args = {'method': req.method, 'path': req.path, 'accept': req.accept}
        LOG.debug(msg % args)

        # If the request is for /versions, just return the versions container
        # TODO(bcwaldon): deprecate this behavior
        if req.path_info_peek() == "versions":
            return self.versions_app.index(req, explicit=True)

        accept = str(req.accept)
        if accept.startswith('application/vnd.openstack.images-'):
            LOG.debug("Using media-type versioning")
            token_loc = len('application/vnd.openstack.images-')
            req_version = accept[token_loc:]
        else:
            LOG.debug("Using url versioning")
            # Remove version in url so it doesn't conflict later
            req_version = self._pop_path_info(req)

        try:
            version = self._match_version_string(req_version)
        except ValueError:
            LOG.debug("Unknown version. Returning version choices.")
            return self.versions_app

        req.environ['api.version'] = version
        req.path_info = ''.join(('/v', str(version), req.path_info))
        LOG.debug("Matched version: v%d", version)
        LOG.debug('new path %s', req.path_info)
        return None

    def _match_version_string(self, subject):
        """
        Given a string, tries to match a major and/or
        minor version number.

        :param subject: The string to check
        :returns version found in the subject
        :raises ValueError if no acceptable version could be found
        """
        if subject in ('v1', 'v1.0', 'v1.1') and CONF.enable_v1_api:
            major_version = 1
        elif subject in ('v2', 'v2.0', 'v2.1', 'v2.2') and CONF.enable_v2_api:
            major_version = 2
        elif subject in ('v3', 'v3.0') and CONF.enable_v3_api:
            major_version = 3
        else:
            raise ValueError()

        return major_version

    def _pop_path_info(self, req):
        """
        'Pops' off the next segment of PATH_INFO, returns the popped
        segment. Do NOT push it onto SCRIPT_NAME.
        """
        path = req.path_info
        if not path:
            return None
        while path.startswith('/'):
            path = path[1:]
        idx = path.find('/')
        if idx == -1:
            idx = len(path)
        r = path[:idx]
        req.path_info = path[idx:]
        return r
