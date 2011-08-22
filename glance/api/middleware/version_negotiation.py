# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
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

import logging
import re

import routes

from glance.api import v1
from glance.api import versions
from glance.common import wsgi

logger = logging.getLogger('glance.api.middleware.version_negotiation')


class VersionNegotiationFilter(wsgi.Middleware):

    def __init__(self, app, options):
        self.versions_app = versions.Controller(options)
        self.version_uri_regex = re.compile(r"^v(\d+)\.?(\d+)?")
        self.options = options
        super(VersionNegotiationFilter, self).__init__(app)

    def process_request(self, req):
        """
        If there is a version identifier in the URI, simply
        return the correct API controller, otherwise, if we
        find an Accept: header, process it
        """
        # See if a version identifier is in the URI passed to
        # us already. If so, simply return the right version
        # API controller
        msg = _("Processing request: %(method)s %(path)s Accept: "
                "%(accept)s") % ({'method': req.method,
                'path': req.path, 'accept': req.accept})
        logger.debug(msg)

        # If the request is for /versions, just return the versions container
        if req.path_info_peek() == "versions":
            return self.versions_app

        match = self._match_version_string(req.path_info_peek(), req)
        if match:
            if (req.environ['api.major_version'] == 1 and
                req.environ['api.minor_version'] == 0):
                logger.debug(_("Matched versioned URI. Version: %d.%d"),
                             req.environ['api.major_version'],
                             req.environ['api.minor_version'])
                # Strip the version from the path
                req.path_info_pop()
                return None
            else:
                logger.debug(_("Unknown version in versioned URI: %d.%d. "
                             "Returning version choices."),
                             req.environ['api.major_version'],
                             req.environ['api.minor_version'])
                return self.versions_app

        accept = str(req.accept)
        if accept.startswith('application/vnd.openstack.images-'):
            token_loc = len('application/vnd.openstack.images-')
            accept_version = accept[token_loc:]
            match = self._match_version_string(accept_version, req)
            if match:
                if (req.environ['api.major_version'] == 1 and
                    req.environ['api.minor_version'] == 0):
                    logger.debug(_("Matched versioned media type. "
                                 "Version: %d.%d"),
                                 req.environ['api.major_version'],
                                 req.environ['api.minor_version'])
                    return None
                else:
                    logger.debug(_("Unknown version in accept header: %d.%d..."
                                 "returning version choices."),
                                 req.environ['api.major_version'],
                                 req.environ['api.minor_version'])
                    return self.versions_app
        else:
            if req.accept not in ('*/*', ''):
                logger.debug(_("Unknown accept header: %s..."
                             "returning version choices."), req.accept)
            return self.versions_app
        return None

    def _match_version_string(self, subject, req):
        """
        Given a subject string, tries to match a major and/or
        minor version number. If found, sets the api.major_version
        and api.minor_version environ variables.

        Returns True if there was a match, false otherwise.

        :param subject: The string to check
        :param req: Webob.Request object
        """
        match = self.version_uri_regex.match(subject)
        if match:
            major_version, minor_version = match.groups(0)
            major_version = int(major_version)
            minor_version = int(minor_version)
            req.environ['api.major_version'] = major_version
            req.environ['api.minor_version'] = minor_version
        return match is not None


def filter_factory(global_conf, **local_conf):
    """
    Factory method for paste.deploy
    """
    conf = global_conf.copy()
    conf.update(local_conf)

    def filter(app):
        return VersionNegotiationFilter(app, conf)

    return filter
