# Copyright 2013 OpenStack Foundation
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

import json
import webob

from glance.api import policy
from glance.common import exception
from glance.common import utils
from glance.common import wsgi
import glance.db
import glance.domain
import glance.gateway
import glance.notifier
from glance.openstack.common import timeutils
import glance.store


class ImageMembersController(object):
    def __init__(self, db_api=None, policy_enforcer=None, notifier=None,
                 store_api=None):
        self.db_api = db_api or glance.db.get_api()
        self.db_api.setup_db_env()
        self.policy = policy_enforcer or policy.Enforcer()
        self.notifier = notifier or glance.notifier.Notifier()
        self.store_api = store_api or glance.store
        self.gateway = glance.gateway.Gateway(self.db_api, self.store_api,
                                              self.notifier, self.policy)

    @utils.mutating
    def create(self, req, image_id, member_id):
        """
        Adds a membership to the image.
        :param req: the Request object coming from the wsgi layer
        :param image_id: the image identifier
        :param member_id: the member identifier
        :retval The response body is a mapping of the following form::

            {'member_id': <MEMBER>,
             'image_id': <IMAGE>,
             'created_at': ..,
             'updated_at': ..}

        """
        image_repo = self.gateway.get_repo(req.context)
        image_member_factory = self.gateway\
                                   .get_image_member_factory(req.context)
        try:
            image = image_repo.get(image_id)
            member_repo = image.get_member_repo()
            new_member = image_member_factory.new_image_member(image,
                                                               member_id)
            member = member_repo.add(new_member)
            self._update_store_acls(req, image)
            return member
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=unicode(e))
        except exception.Forbidden as e:
            raise webob.exc.HTTPForbidden(explanation=unicode(e))

    def index(self, req, image_id):
        """
        Return a list of dictionaries indicating the members of the
        image, i.e., those tenants the image is shared with.

        :param req: the Request object coming from the wsgi layer
        :param image_id: The image identifier
        :retval The response body is a mapping of the following form::

            {'members': [
                {'member_id': <MEMBER>,
                 'image_id': <IMAGE>,
                 'created_at': ..,
                 'updated_at': ..}, ..
            ]}
        """
        image_repo = self.gateway.get_repo(req.context)
        try:
            image = image_repo.get(image_id)
            member_repo = image.get_member_repo()
            members = []
            for member in member_repo.list():
                members.append(member)
            return dict(members=members)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=unicode(e))
        except exception.Forbidden as e:
            raise webob.exc.HTTPForbidden(explanation=unicode(e))

    @utils.mutating
    def delete(self, req, image_id, member_id):
        """
        Removes a membership from the image.
        """

        image_repo = self.gateway.get_repo(req.context)
        try:
            image = image_repo.get(image_id)
            member_repo = image.get_member_repo()
            member = member_repo.get(member_id)
            member_repo.remove(member)
            self._update_store_acls(req, image)
            return webob.Response(body='', status=200)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=unicode(e))
        except exception.Forbidden as e:
            raise webob.exc.HTTPForbidden(explanation=unicode(e))

    def _update_store_acls(self, req, image):
        location_uri = image.location
        public = image.visibility == 'public'
        member_repo = image.get_member_repo()
        if location_uri:
            try:
                read_tenants = []
                write_tenants = []
                members = member_repo.list()
                if members:
                    for member in members:
                        read_tenants.append(member.member_id)
                glance.store.set_acls(req.context, location_uri, public=public,
                                      read_tenants=read_tenants,
                                      write_tenants=write_tenants)
            except exception.UnknownScheme:
                msg = _("Store for image not found: %s") % image_id
                raise webob.exc.HTTPBadRequest(explanation=msg,
                                               request=req,
                                               content_type='text/plain')


class ResponseSerializer(wsgi.JSONResponseSerializer):
    def __init__(self, schema=None):
        super(ResponseSerializer, self).__init__()

    def _format_image_member(self, member):
        member_view = {}
        attributes = ['member_id', 'image_id']
        for key in attributes:
            member_view[key] = getattr(member, key)
        member_view['created_at'] = timeutils.isotime(member.created_at)
        member_view['updated_at'] = timeutils.isotime(member.updated_at)
        return member_view

    def create(self, response, image_member):
        image_member_view = self._format_image_member(image_member)
        body = json.dumps(image_member_view, ensure_ascii=False)
        response.unicode_body = unicode(body)
        response.content_type = 'application/json'

    def index(self, response, image_members):
        image_members = image_members['members']
        image_members_view = []
        for image_member in image_members:
            image_member_view = self._format_image_member(image_member)
            image_members_view.append(image_member_view)
        body = json.dumps(dict(members=image_members_view), ensure_ascii=False)
        response.unicode_body = unicode(body)
        response.content_type = 'application/json'


def create_resource():
    """Image Members resource factory method"""
    deserializer = wsgi.JSONRequestDeserializer()
    serializer = ResponseSerializer()
    controller = ImageMembersController()
    return wsgi.Resource(controller, deserializer, serializer)
