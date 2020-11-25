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
from glance.i18n import _, _LW


context_opts = [
    cfg.BoolOpt('owner_is_tenant',
                default=True,
                deprecated_for_removal=True,
                deprecated_since="Rocky",
                deprecated_reason=_("""
The non-default setting for this option misaligns Glance with other
OpenStack services with respect to resource ownership.  Further, surveys
indicate that this option is not used by operators.  The option will be
removed early in the 'S' development cycle following the standard OpenStack
deprecation policy.  As the option is not in wide use, no migration path is
proposed.
"""),
                help=_("""
Set the image owner to tenant or the authenticated user.

Assign a boolean value to determine the owner of an image. When set to
True, the owner of the image is the tenant. When set to False, the
owner of the image will be the authenticated user issuing the request.
Setting it to False makes the image private to the associated user and
sharing with other users within the same tenant (or "project")
requires explicit image sharing via image membership.

Possible values:
    * True
    * False

Related options:
    * None

""")),

    cfg.BoolOpt('allow_anonymous_access', default=False,
                help=_("""
Allow limited access to unauthenticated users.

Assign a boolean to determine API access for unathenticated
users. When set to False, the API cannot be accessed by
unauthenticated users. When set to True, unauthenticated users can
access the API with read-only privileges. This however only applies
when using ContextMiddleware.

Possible values:
    * True
    * False

Related options:
    * None

""")),

    cfg.IntOpt('max_request_id_length', default=64, min=0,
               help=_("""
Limit the request ID length.

Provide  an integer value to limit the length of the request ID to
the specified length. The default value is 64. Users can change this
to any ineteger value between 0 and 16384 however keeping in mind that
a larger value may flood the logs.

Possible values:
    * Integer value between 0 and 16384

Related options:
    * None

""")),
]

CONF = cfg.CONF
CONF.register_opts(context_opts)

LOG = logging.getLogger(__name__)


class BaseContextMiddleware(wsgi.Middleware):
    def process_response(self, resp):
        try:
            request_id = resp.request.context.request_id
        except AttributeError:
            LOG.warn(_LW('Unable to retrieve request id from context'))
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
        :raises webob.exc.HTTPUnauthorized: when value of the
                                            X-Identity-Status  header is not
                                            'Confirmed' and anonymous access
                                            is disallowed
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
            'owner_is_tenant': CONF.owner_is_tenant,
            'service_catalog': service_catalog,
            'policy_enforcer': self.policy_enforcer,
            'request_id': request_id,
        }

        ctxt = glance.context.RequestContext.from_environ(req.environ,
                                                          **kwargs)

        # FIXME(jamielennox): glance has traditionally lowercased its roles.
        # This was related to bug #1010519 where at least the admin role was
        # case insensitive. This seems to no longer be the case and should be
        # fixed.
        ctxt.roles = [r.lower() for r in ctxt.roles]

        return ctxt


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
