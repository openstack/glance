
import logging

import webob.exc

from glance import api
from glance.common import exception
from glance.common import wsgi
from glance import registry


logger = logging.getLogger('glance.api.v1.members')


class Controller(object):

    def __init__(self, conf):
        self.conf = conf

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
        try:
            members = registry.get_image_members(req.context, image_id)
        except exception.NotFound:
            msg = _("Image with identifier %s not found") % image_id
            logger.debug(msg)
            raise webob.exc.HTTPNotFound(msg)
        except exception.NotAuthorized:
            msg = _("Unauthorized image access")
            logger.debug(msg)
            raise webob.exc.HTTPForbidden(msg)
        return dict(members=members)

    def delete(self, req, image_id, id):
        """
        Removes a membership from the image.
        """
        if req.context.read_only:
            raise webob.exc.HTTPForbidden()
        elif req.context.owner is None:
            raise webob.exc.HTTPUnauthorized(_("No authenticated user"))

        try:
            registry.delete_member(req.context, image_id, id)
        except exception.NotFound, e:
            msg = "%s" % e
            logger.debug(msg)
            raise webob.exc.HTTPNotFound(msg)
        except exception.NotAuthorized, e:
            msg = "%s" % e
            logger.debug(msg)
            raise webob.exc.HTTPNotFound(msg)

        return webob.exc.HTTPNoContent()

    def default(self, req, image_id, id, body=None):
        """This will cover the missing 'show' and 'create' actions"""
        raise webob.exc.HTTPMethodNotAllowed()

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
        if req.context.read_only:
            raise webob.exc.HTTPForbidden()
        elif req.context.owner is None:
            raise webob.exc.HTTPUnauthorized(_("No authenticated user"))

        # Figure out can_share
        can_share = None
        if body and 'member' in body and 'can_share' in body['member']:
            can_share = bool(body['member']['can_share'])
        try:
            registry.add_member(req.context, image_id, id, can_share)
        except exception.Invalid, e:
            msg = "%s" % e
            logger.debug(msg)
            raise webob.exc.HTTPBadRequest(explanation=msg)
        except exception.NotFound, e:
            msg = "%s" % e
            logger.debug(msg)
            raise webob.exc.HTTPNotFound(msg)
        except exception.NotAuthorized, e:
            msg = "%s" % e
            logger.debug(msg)
            raise webob.exc.HTTPNotFound(msg)

        return webob.exc.HTTPNoContent()

    def update_all(self, req, image_id, body):
        """
        Replaces the members of the image with those specified in the
        body.  The body is a dict with the following format::

            {"memberships": [
                {"member_id": <MEMBER_ID>,
                 ["can_share": [True|False]]}, ...
            ]}
        """
        if req.context.read_only:
            raise webob.exc.HTTPForbidden()
        elif req.context.owner is None:
            raise webob.exc.HTTPUnauthorized(_("No authenticated user"))

        try:
            registry.replace_members(req.context, image_id, body)
        except exception.Invalid, e:
            msg = "%s" % e
            logger.debug(msg)
            raise webob.exc.HTTPBadRequest(explanation=msg)
        except exception.NotFound, e:
            msg = "%s" % e
            logger.debug(msg)
            raise webob.exc.HTTPNotFound(msg)
        except exception.NotAuthorized, e:
            msg = "%s" % e
            logger.debug(msg)
            raise webob.exc.HTTPNotFound(msg)

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
        except exception.NotFound, e:
            msg = "%s" % e
            logger.debug(msg)
            raise webob.exc.HTTPNotFound(msg)
        except exception.NotAuthorized, e:
            msg = "%s" % e
            logger.debug(msg)
            raise webob.exc.HTTPForbidden(msg)
        return dict(shared_images=members)


def create_resource(conf):
    """Image members resource factory method"""
    deserializer = wsgi.JSONRequestDeserializer()
    serializer = wsgi.JSONResponseSerializer()
    return wsgi.Resource(Controller(conf), deserializer, serializer)
