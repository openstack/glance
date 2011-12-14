# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack LLC.
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

import logging

import webob.exc

from glance.common import exception
from glance.common import wsgi
from glance.registry.db import api as db_api


logger = logging.getLogger('glance.registry.api.v1.members')


class Controller(object):

    def __init__(self, conf):
        self.conf = conf
        db_api.configure_db(conf)

    def index(self, req, image_id):
        """
        Get the members of an image.
        """
        try:
            image = db_api.image_get(req.context, image_id)
        except exception.NotFound:
            raise webob.exc.HTTPNotFound()
        except exception.NotAuthorized:
            # If it's private and doesn't belong to them, don't let on
            # that it exists
            msg = _("Access by %(user)s to image %(id)s "
                    "denied") % ({'user': req.context.user,
                    'id': image_id})
            logger.info(msg)
            raise webob.exc.HTTPNotFound()

        return dict(members=make_member_list(image['members'],
                                             member_id='member',
                                             can_share='can_share'))

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

        # Make sure the image exists
        session = db_api.get_session()
        try:
            image = db_api.image_get(req.context, image_id, session=session)
        except exception.NotFound:
            raise webob.exc.HTTPNotFound()
        except exception.NotAuthorized:
            # If it's private and doesn't belong to them, don't let on
            # that it exists
            msg = _("Access by %(user)s to image %(id)s "
                    "denied") % ({'user': req.context.user,
                    'id': image_id})
            logger.info(msg)
            raise webob.exc.HTTPNotFound()

        # Can they manipulate the membership?
        if not req.context.is_image_sharable(image):
            msg = _("No permission to share that image")
            raise webob.exc.HTTPForbidden(msg)

        # Get the membership list
        try:
            memb_list = body['memberships']
        except Exception, e:
            # Malformed entity...
            msg = _("Invalid membership association: %s") % e
            raise webob.exc.HTTPBadRequest(explanation=msg)

        add = []
        existing = {}
        # Walk through the incoming memberships
        for memb in memb_list:
            try:
                datum = dict(image_id=image['id'],
                             member=memb['member_id'],
                             can_share=None)
            except Exception, e:
                # Malformed entity...
                msg = _("Invalid membership association: %s") % e
                raise webob.exc.HTTPBadRequest(explanation=msg)

            # Figure out what can_share should be
            if 'can_share' in memb:
                datum['can_share'] = bool(memb['can_share'])

            # Try to find the corresponding membership
            try:
                membership = db_api.image_member_find(req.context,
                                                      datum['image_id'],
                                                      datum['member'],
                                                      session=session)

                # Are we overriding can_share?
                if datum['can_share'] is None:
                    datum['can_share'] = membership['can_share']

                existing[membership['id']] = {
                    'values': datum,
                    'membership': membership,
                    }
            except exception.NotFound:
                # Default can_share
                datum['can_share'] = bool(datum['can_share'])
                add.append(datum)

        # We now have a filtered list of memberships to add and
        # memberships to modify.  Let's start by walking through all
        # the existing image memberships...
        for memb in image['members']:
            if memb['id'] in existing:
                # Just update the membership in place
                update = existing[memb['id']]['values']
                db_api.image_member_update(req.context, memb, update,
                                           session=session)
            else:
                # Outdated one; needs to be deleted
                db_api.image_member_delete(req.context, memb, session=session)

        # Now add the non-existant ones
        for memb in add:
            db_api.image_member_create(req.context, memb, session=session)

        # Make an appropriate result
        return webob.exc.HTTPNoContent()

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

        # Make sure the image exists
        try:
            image = db_api.image_get(req.context, image_id)
        except exception.NotFound:
            raise webob.exc.HTTPNotFound()
        except exception.NotAuthorized:
            # If it's private and doesn't belong to them, don't let on
            # that it exists
            msg = _("Access by %(user)s to image %(id)s "
                    "denied") % ({'user': req.context.user,
                    'id': image_id})
            logger.info(msg)
            raise webob.exc.HTTPNotFound()

        # Can they manipulate the membership?
        if not req.context.is_image_sharable(image):
            msg = _("No permission to share that image")
            raise webob.exc.HTTPForbidden(msg)

        # Determine the applicable can_share value
        can_share = None
        if body:
            try:
                can_share = bool(body['member']['can_share'])
            except Exception, e:
                # Malformed entity...
                msg = _("Invalid membership association: %s") % e
                raise webob.exc.HTTPBadRequest(explanation=msg)

        # Look up an existing membership...
        try:
            session = db_api.get_session()
            membership = db_api.image_member_find(req.context,
                                                  image_id, id,
                                                  session=session)
            if can_share is not None:
                values = dict(can_share=can_share)
                db_api.image_member_update(req.context, membership, values,
                                           session=session)
        except exception.NotFound:
            values = dict(image_id=image['id'], member=id,
                          can_share=bool(can_share))
            db_api.image_member_create(req.context, values, session=session)

        return webob.exc.HTTPNoContent()

    def delete(self, req, image_id, id):
        """
        Removes a membership from the image.
        """
        if req.context.read_only:
            raise webob.exc.HTTPForbidden()
        elif req.context.owner is None:
            raise webob.exc.HTTPUnauthorized(_("No authenticated user"))

        # Make sure the image exists
        try:
            image = db_api.image_get(req.context, image_id)
        except exception.NotFound:
            raise webob.exc.HTTPNotFound()
        except exception.NotAuthorized:
            # If it's private and doesn't belong to them, don't let on
            # that it exists
            msg = _("Access by %(user)s to image %(id)s "
                    "denied") % ({'user': req.context.user,
                    'id': image_id})
            logger.info(msg)
            raise webob.exc.HTTPNotFound()

        # Can they manipulate the membership?
        if not req.context.is_image_sharable(image):
            msg = _("No permission to share that image")
            raise webob.exc.HTTPForbidden(msg)

        # Look up an existing membership
        try:
            session = db_api.get_session()
            member_ref = db_api.image_member_find(req.context,
                                                  image_id,
                                                  id,
                                                  session=session)
            db_api.image_member_delete(req.context,
                                       member_ref,
                                       session=session)
        except exception.NotFound:
            pass

        # Make an appropriate result
        return webob.exc.HTTPNoContent()

    def index_shared_images(self, req, id):
        """
        Retrieves images shared with the given member.
        """
        params = {}
        try:
            memberships = db_api.image_member_get_memberships(req.context,
                                                              id,
                                                              **params)
        except exception.NotFound, e:
            msg = _("Invalid marker. Membership could not be found.")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        return dict(shared_images=make_member_list(memberships,
                                                   image_id='image_id',
                                                   can_share='can_share'))


def make_member_list(members, **attr_map):
    """
    Create a dict representation of a list of members which we can use
    to serialize the members list.  Keyword arguments map the names of
    optional attributes to include to the database attribute.
    """

    def _fetch_memb(memb, attr_map):
        return dict([(k, memb[v]) for k, v in attr_map.items()
                                  if v in memb.keys()])

    # Return the list of members with the given attribute mapping
    return [_fetch_memb(memb, attr_map) for memb in members
            if not memb.deleted]


def create_resource(conf):
    """Image members resource factory method."""
    deserializer = wsgi.JSONRequestDeserializer()
    serializer = wsgi.JSONResponseSerializer()
    return wsgi.Resource(Controller(conf), deserializer, serializer)
