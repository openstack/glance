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

from glance.common import cfg
from glance.common import exception
from glance.common import utils
from glance.common import wsgi
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


class ContextMiddleware(wsgi.Middleware):

    opts = [
        cfg.BoolOpt('owner_is_tenant', default=True),
        ]

    def __init__(self, app, conf, **local_conf):
        self.conf = conf
        self.conf.register_opts(self.opts)

        # Determine the context class to use
        self.ctxcls = RequestContext
        if 'context_class' in local_conf:
            self.ctxcls = utils.import_class(local_conf['context_class'])

        super(ContextMiddleware, self).__init__(app)

    def make_context(self, *args, **kwargs):
        """
        Create a context with the given arguments.
        """
        kwargs.setdefault('owner_is_tenant', self.conf.owner_is_tenant)

        return self.ctxcls(*args, **kwargs)

    def process_request(self, req):
        """
        Extract any authentication information in the request and
        construct an appropriate context from it.

        A few scenarios exist:

        1. If X-Auth-Token is passed in, then consult TENANT and ROLE headers
           to determine permissions.

        2. An X-Auth-Token was passed in, but the Identity-Status is not
           confirmed. For now, just raising a NotAuthorized exception.

        3. X-Auth-Token is omitted. If we were using Keystone, then the
           tokenauth middleware would have rejected the request, so we must be
           using NoAuth. In that case, assume that is_admin=True.
        """
        # TODO(sirp): should we be using the glance_tokeauth shim from
        # Keystone here? If we do, we need to make sure it handles the NoAuth
        # case
        auth_tok = req.headers.get('X-Auth-Token',
                                   req.headers.get('X-Storage-Token'))
        if auth_tok:
            if req.headers.get('X-Identity-Status') == 'Confirmed':
                # 1. Auth-token is passed, check other headers
                user = req.headers.get('X-User')
                tenant = req.headers.get('X-Tenant')
                roles = [r.strip()
                         for r in req.headers.get('X-Role', '').split(',')]
                is_admin = 'Admin' in roles
            else:
                # 2. Indentity-Status not confirmed
                # FIXME(sirp): not sure what the correct behavior in this case
                # is; just raising NotAuthorized for now
                raise exception.NotAuthorized()
        else:
            # 3. Auth-token is ommited, assume NoAuth
            user = None
            tenant = None
            roles = []
            is_admin = True

        req.context = self.make_context(
            auth_tok=auth_tok, user=user, tenant=tenant, roles=roles,
            is_admin=is_admin)
