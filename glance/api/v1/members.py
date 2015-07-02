# Copyright 2012 OpenStack Foundation.
# Copyright 2013 NTT corp.
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
from oslo_utils import encodeutils
import webob.exc

from glance.api import policy
from glance.api.v1 import controller
from glance.common import exception
from glance.common import utils
from glance.common import wsgi
from glance import i18n
import glance.registry.client.v1.api as registry

LOG = logging.getLogger(__name__)
_ = i18n._
CONF = cfg.CONF
CONF.import_opt('image_member_quota', 'glance.common.config')


class Controller(controller.BaseController):

    def __init__(self):
        self.policy = policy.Enforcer()

    def _check_can_access_image_members(self, context):
        if context.owner is None and not context.is_admin:
            raise webob.exc.HTTPUnauthorized(_("No authenticated user"))

    def _enforce(self, req, action):
        """Authorize an action against our policies"""
        try:
            self.policy.enforce(req.context, action, {})
        except exception.Forbidden:
            LOG.debug("User not permitted to perform '%s' action", action)
            raise webob.exc.HTTPForbidden()

    def _raise_404_if_image_deleted(self, req, image_id):
        image = self.get_image_meta_or_404(req, image_id)
        if image['status'] == 'deleted':
            msg = _("Image with identifier %s has been deleted.") % image_id
            raise webob.exc.HTTPNotFound(msg)

    def index(self, req, image_id):
        """
        Return a list of dictionaries indicating the members of the
        image, i.e., those tenants the image is shared with.

        :param req: the Request object coming from the wsgi layer
        :param image_id: The opaque image identifier
        :retval The response body is a mapping of the following form::

            {'members': [
                {'member_id': <MEMBER>,
                 'can_share': <SHARE_PERMISSION>, ...}, ...
            ]}
        """
        self._enforce(req, 'get_members')
        self._raise_404_if_image_deleted(req, image_id)

        try:
            members = registry.get_image_members(req.context, image_id)
        except exception.NotFound:
            msg = _("Image with identifier %s not found") % image_id
            LOG.warn(msg)
            raise webob.exc.HTTPNotFound(msg)
        except exception.Forbidden:
            msg = _("Unauthorized image access")
            LOG.warn(msg)
            raise webob.exc.HTTPForbidden(msg)
        return dict(members=members)

    @utils.mutating
    def delete(self, req, image_id, id):
        """
        Removes a membership from the image.
        """
        self._check_can_access_image_members(req.context)
        self._enforce(req, 'delete_member')
        self._raise_404_if_image_deleted(req, image_id)

        try:
            registry.delete_member(req.context, image_id, id)
            self._update_store_acls(req, image_id)
        except exception.NotFound as e:
            LOG.debug(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except exception.Forbidden as e:
            LOG.debug("User not permitted to remove membership from image "
                      "'%s'", image_id)
            raise webob.exc.HTTPNotFound(explanation=e.msg)

        return webob.exc.HTTPNoContent()

    def default(self, req, image_id, id, body=None):
        """This will cover the missing 'show' and 'create' actions"""
        raise webob.exc.HTTPMethodNotAllowed()

    def _enforce_image_member_quota(self, req, attempted):
        if CONF.image_member_quota < 0:
            # If value is negative, allow unlimited number of members
            return

        maximum = CONF.image_member_quota
        if attempted > maximum:
            msg = _("The limit has been exceeded on the number of allowed "
                    "image members for this image. Attempted: %(attempted)s, "
                    "Maximum: %(maximum)s") % {'attempted': attempted,
                                               'maximum': maximum}
            raise webob.exc.HTTPRequestEntityTooLarge(explanation=msg,
                                                      request=req)

    @utils.mutating
    def update(self, req, image_id, id, body=None):
        """
        Adds a membership to the image, or updates an existing one.
        If a body is present, it is a dict with the following format::

            {"member": {
                "can_share": [True|False]
            }}

        If "can_share" is provided, the member's ability to share is
        set accordingly.  If it is not provided, existing memberships
        remain unchanged and new memberships default to False.
        """
        self._check_can_access_image_members(req.context)
        self._enforce(req, 'modify_member')
        self._raise_404_if_image_deleted(req, image_id)

        new_number_of_members = len(registry.get_image_members(req.context,
                                                               image_id)) + 1
        self._enforce_image_member_quota(req, new_number_of_members)

        # Figure out can_share
        can_share = None
        if body and 'member' in body and 'can_share' in body['member']:
            can_share = bool(body['member']['can_share'])
        try:
            registry.add_member(req.context, image_id, id, can_share)
            self._update_store_acls(req, image_id)
        except exception.Invalid as e:
            LOG.debug(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        except exception.NotFound as e:
            LOG.debug(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except exception.Forbidden as e:
            LOG.debug(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPNotFound(explanation=e.msg)

        return webob.exc.HTTPNoContent()

    @utils.mutating
    def update_all(self, req, image_id, body):
        """
        Replaces the members of the image with those specified in the
        body.  The body is a dict with the following format::

            {"memberships": [
                {"member_id": <MEMBER_ID>,
                 ["can_share": [True|False]]}, ...
            ]}
        """
        self._check_can_access_image_members(req.context)
        self._enforce(req, 'modify_member')
        self._raise_404_if_image_deleted(req, image_id)

        memberships = body.get('memberships')
        if memberships:
            new_number_of_members = len(body['memberships'])
            self._enforce_image_member_quota(req, new_number_of_members)

        try:
            registry.replace_members(req.context, image_id, body)
            self._update_store_acls(req, image_id)
        except exception.Invalid as e:
            LOG.debug(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        except exception.NotFound as e:
            LOG.debug(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except exception.Forbidden as e:
            LOG.debug(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPNotFound(explanation=e.msg)

        return webob.exc.HTTPNoContent()

    def index_shared_images(self, req, id):
        """
        Retrieves list of image memberships for the given member.

        :param req: the Request object coming from the wsgi layer
        :param id: the opaque member identifier
        :retval The response body is a mapping of the following form::

            {'shared_images': [
                {'image_id': <IMAGE>,
                 'can_share': <SHARE_PERMISSION>, ...}, ...
            ]}
        """
        try:
            members = registry.get_member_images(req.context, id)
        except exception.NotFound as e:
            LOG.debug(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except exception.Forbidden as e:
            LOG.debug(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        return dict(shared_images=members)

    def _update_store_acls(self, req, image_id):
        image_meta = self.get_image_meta_or_404(req, image_id)
        location_uri = image_meta.get('location')
        public = image_meta.get('is_public')
        self.update_store_acls(req, image_id, location_uri, public)


def create_resource():
    """Image members resource factory method"""
    deserializer = wsgi.JSONRequestDeserializer()
    serializer = wsgi.JSONResponseSerializer()
    return wsgi.Resource(Controller(), deserializer, serializer)
