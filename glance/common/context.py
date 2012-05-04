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

import webob.exc

from glance.common import exception
from glance.common import wsgi
from glance.openstack.common import cfg
from glance.registry.db import api as db_api


class RequestContext(object):
    """
    Stores information about the security context under which the user
    accesses the system, as well as additional request information.
    """

    def __init__(self, auth_tok=None, user=None, tenant=None, roles=None,
                 is_admin=False, read_only=False, show_deleted=False,
                 owner_is_tenant=True):
        self.auth_tok = auth_tok
        self.user = user
        self.tenant = tenant
        self.roles = roles or []
        self.is_admin = is_admin
        self.read_only = read_only
        self._show_deleted = show_deleted
        self.owner_is_tenant = owner_is_tenant

    @property
    def owner(self):
        """Return the owner to correlate with an image."""
        return self.tenant if self.owner_is_tenant else self.user

    @property
    def show_deleted(self):
        """Admins can see deleted by default"""
        if self._show_deleted or self.is_admin:
            return True
        return False

    def is_image_visible(self, image):
        """Return True if the image is visible in this context."""
        # Is admin == image visible
        if self.is_admin:
            return True

        # No owner == image visible
        if image['owner'] is None:
            return True

        # Image is_public == image visible
        if image['is_public']:
            return True

        # Perform tests based on whether we have an owner
        if self.owner is not None:
            if self.owner == image['owner']:
                return True

            # Figure out if this image is shared with that tenant
            try:
                tmp = db_api.image_member_find(self, image['id'], self.owner)
                return not tmp['deleted']
            except exception.NotFound:
                pass

        # Private image
        return False

    def is_image_mutable(self, image):
        """Return True if the image is mutable in this context."""
        # Is admin == image mutable
        if self.is_admin:
            return True

        # No owner == image not mutable
        if image['owner'] is None or self.owner is None:
            return False

        # Image only mutable by its owner
        return image['owner'] == self.owner

    def is_image_sharable(self, image, **kwargs):
        """Return True if the image can be shared to others in this context."""
        # Only allow sharing if we have an owner
        if self.owner is None:
            return False

        # Is admin == image sharable
        if self.is_admin:
            return True

        # If we own the image, we can share it
        if self.owner == image['owner']:
            return True

        # Let's get the membership association
        if 'membership' in kwargs:
            membership = kwargs['membership']
            if membership is None:
                # Not shared with us anyway
                return False
        else:
            try:
                membership = db_api.image_member_find(self, image['id'],
                                                      self.owner)
            except exception.NotFound:
                # Not shared with us anyway
                return False

        # It's the can_share attribute we're now interested in
        return membership['can_share']


class ContextMiddleware(wsgi.Middleware):

    opts = [
        cfg.BoolOpt('owner_is_tenant', default=True),
        cfg.StrOpt('admin_role', default='admin'),
    ]

    def __init__(self, app, conf, **local_conf):
        self.conf = conf
        self.conf.register_opts(self.opts)
        super(ContextMiddleware, self).__init__(app)

    def process_request(self, req):
        """Convert authentication informtion into a request context

        Generate a RequestContext object from the available
        authentication headers and store on the 'context' attribute
        of the req object.

        :param req: wsgi request object that will be given the context object
        :raises webob.exc.HTTPUnauthorized: when value of the X-Identity-Status
                                            header is not 'Confirmed'
        """
        if req.headers.get('X-Identity-Status') != 'Confirmed':
            raise webob.exc.HTTPUnauthorized()

        #NOTE(bcwaldon): X-Roles is a csv string, but we need to parse
        # it into a list to be useful
        roles_header = req.headers.get('X-Roles', '')
        roles = [r.strip() for r in roles_header.split(',')]

        #NOTE(bcwaldon): This header is deprecated in favor of X-Auth-Token
        deprecated_token = req.headers.get('X-Storage-Token')

        kwargs = {
            'user': req.headers.get('X-User-Id'),
            'tenant': req.headers.get('X-Tenant-Id'),
            'roles': roles,
            'is_admin': self.conf.admin_role in roles,
            'auth_tok': req.headers.get('X-Auth-Token', deprecated_token),
            'owner_is_tenant': self.conf.owner_is_tenant,
        }

        req.context = RequestContext(**kwargs)


class UnauthenticatedContextMiddleware(wsgi.Middleware):

    def __init__(self, app, conf, **local_conf):
        self.conf = conf
        super(UnauthenticatedContextMiddleware, self).__init__(app)

    def process_request(self, req):
        """Create a context without an authorized user."""
        kwargs = {
            'user': None,
            'tenant': None,
            'roles': [],
            'is_admin': True,
        }

        req.context = RequestContext(**kwargs)
