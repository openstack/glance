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

from glance.common import wsgi


class RequestContext(object):
    """Security context and request information.

    Stores information about the security context under which the user
    accesses the system, as well as additional request information.

    """

    def __init__(self, auth_tok=None, user=None, tenant=None, is_admin=False,
                 read_only=False):
        self.auth_tok = auth_tok
        self.user = user
        self.tenant = tenant
        self.is_admin = is_admin
        self.read_only = read_only

    def image_visible(self, image):
        """Return True if the image is visible in this context."""
        # Is admin == image visible
        if self.is_admin:
            return True

        # No owner == image visible
        if image.owner is None:
            return True

        # Image is_public == image visible
        if image.is_public:
            return True

        # Private image
        return self.owner is not None and self.owner == image.owner

    @property
    def owner(self):
        """Return the owner to correlate with an image."""
        return self.tenant


class ContextMiddleware(wsgi.Middleware):
    def __init__(self, app, options):
        self.options = options
        super(ContextMiddleware, self).__init__(app)

    def process_request(self, req):
        """
        Extract any authentication information in the request and
        construct an appropriate context from it.
        """
        # Use the default empty context, with admin turned on for
        # backwards compatibility
        req.context = RequestContext(is_admin=True)


def filter_factory(global_conf, **local_conf):
    """
    Factory method for paste.deploy
    """
    conf = global_conf.copy()
    conf.update(local_conf)

    def filter(app):
        return ContextMiddleware(app, conf)

    return filter
