# Copyright 2011-2012 OpenStack Foundation
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
from oslo_log import log as logging
from oslo_serialization import jsonutils
import webob.exc

from glance.api import policy
from glance.common import wsgi
import glance.context
from glance import i18n

_ = i18n._

context_opts = [
    cfg.BoolOpt('owner_is_tenant', default=True,
                help=_('When true, this option sets the owner of an image '
                       'to be the tenant. Otherwise, the owner of the '
                       ' image will be the authenticated user issuing the '
                       'request.')),
    cfg.StrOpt('admin_role', default='admin',
               help=_('Role used to identify an authenticated user as '
                      'administrator.')),
    cfg.BoolOpt('allow_anonymous_access', default=False,
                help=_('Allow unauthenticated users to access the API with '
                       'read-only privileges. This only applies when using '
                       'ContextMiddleware.')),
    cfg.IntOpt('max_request_id_length', default=64,
               help=_('Limits request ID length.')),
]

CONF = cfg.CONF
CONF.register_opts(context_opts)

LOG = logging.getLogger(__name__)


class BaseContextMiddleware(wsgi.Middleware):
    def process_response(self, resp):
        try:
            request_id = resp.request.context.request_id
        except AttributeError:
            LOG.warn(_('Unable to retrieve request id from context'))
        else:
            # For python 3 compatibility need to use bytes type
            prefix = b'req-' if isinstance(request_id, bytes) else 'req-'

            if not request_id.startswith(prefix):
                request_id = prefix + request_id

            resp.headers['x-openstack-request-id'] = request_id

        return resp


class ContextMiddleware(BaseContextMiddleware):
    def __init__(self, app):
        self.policy_enforcer = policy.Enforcer()
        super(ContextMiddleware, self).__init__(app)

    def process_request(self, req):
        """Convert authentication information into a request context

        Generate a glance.context.RequestContext object from the available
        authentication headers and store on the 'context' attribute
        of the req object.

        :param req: wsgi request object that will be given the context object
        :raises webob.exc.HTTPUnauthorized: when value of the X-Identity-Status
                                            header is not 'Confirmed' and
                                            anonymous access is disallowed
        """
        if req.headers.get('X-Identity-Status') == 'Confirmed':
            req.context = self._get_authenticated_context(req)
        elif CONF.allow_anonymous_access:
            req.context = self._get_anonymous_context()
        else:
            raise webob.exc.HTTPUnauthorized()

    def _get_anonymous_context(self):
        kwargs = {
            'user': None,
            'tenant': None,
            'roles': [],
            'is_admin': False,
            'read_only': True,
            'policy_enforcer': self.policy_enforcer,
        }
        return glance.context.RequestContext(**kwargs)

    def _get_authenticated_context(self, req):
        # NOTE(bcwaldon): X-Roles is a csv string, but we need to parse
        # it into a list to be useful
        roles_header = req.headers.get('X-Roles', '')
        roles = [r.strip().lower() for r in roles_header.split(',')]

        # NOTE(bcwaldon): This header is deprecated in favor of X-Auth-Token
        deprecated_token = req.headers.get('X-Storage-Token')

        service_catalog = None
        if req.headers.get('X-Service-Catalog') is not None:
            try:
                catalog_header = req.headers.get('X-Service-Catalog')
                service_catalog = jsonutils.loads(catalog_header)
            except ValueError:
                raise webob.exc.HTTPInternalServerError(
                    _('Invalid service catalog json.'))

        request_id = req.headers.get('X-Openstack-Request-ID')
        if request_id and (0 < CONF.max_request_id_length <
                           len(request_id)):
            msg = (_('x-openstack-request-id is too long, max size %s') %
                   CONF.max_request_id_length)
            return webob.exc.HTTPRequestHeaderFieldsTooLarge(comment=msg)

        kwargs = {
            'user': req.headers.get('X-User-Id'),
            'tenant': req.headers.get('X-Tenant-Id'),
            'roles': roles,
            'is_admin': CONF.admin_role.strip().lower() in roles,
            'auth_token': req.headers.get('X-Auth-Token', deprecated_token),
            'owner_is_tenant': CONF.owner_is_tenant,
            'service_catalog': service_catalog,
            'policy_enforcer': self.policy_enforcer,
            'request_id': request_id,
        }

        return glance.context.RequestContext(**kwargs)


class UnauthenticatedContextMiddleware(BaseContextMiddleware):
    def process_request(self, req):
        """Create a context without an authorized user."""
        kwargs = {
            'user': None,
            'tenant': None,
            'roles': [],
            'is_admin': True,
        }

        req.context = glance.context.RequestContext(**kwargs)
