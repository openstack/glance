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

import copy

import glance_store
from oslo.serialization import jsonutils
from oslo_log import log as logging
from oslo_utils import timeutils
import six
import webob

from glance.api import policy
from glance.common import exception
from glance.common import utils
from glance.common import wsgi
import glance.db
import glance.gateway
from glance import i18n
import glance.notifier
import glance.schema


LOG = logging.getLogger(__name__)
_ = i18n._


class ImageMembersController(object):
    def __init__(self, db_api=None, policy_enforcer=None, notifier=None,
                 store_api=None):
        self.db_api = db_api or glance.db.get_api()
        self.policy = policy_enforcer or policy.Enforcer()
        self.notifier = notifier or glance.notifier.Notifier()
        self.store_api = store_api or glance_store
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
             'status': <MEMBER_STATUS>
             'created_at': ..,
             'updated_at': ..}

        """
        image_repo = self.gateway.get_repo(req.context)
        image_member_factory = self.gateway.get_image_member_factory(
            req.context)
        try:
            image = image_repo.get(image_id)
            member_repo = image.get_member_repo()
            new_member = image_member_factory.new_image_member(image,
                                                               member_id)
            member_repo.add(new_member)

            return new_member
        except exception.NotFound:
            msg = _("Image %s not found.") % image_id
            LOG.warning(msg)
            raise webob.exc.HTTPNotFound(explanation=msg)
        except exception.Forbidden:
            msg = _("Not allowed to create members for image %s.") % image_id
            LOG.warning(msg)
            raise webob.exc.HTTPForbidden(explanation=msg)
        except exception.Duplicate:
            msg = _("Member %(member_id)s is duplicated for image "
                    "%(image_id)s") % {"member_id": member_id,
                                       "image_id": image_id}
            LOG.warning(msg)
            raise webob.exc.HTTPConflict(explanation=msg)
        except exception.ImageMemberLimitExceeded as e:
            msg = (_("Image member limit exceeded for image %(id)s: %(e)s:")
                   % {"id": image_id, "e": utils.exception_to_str(e)})
            LOG.warning(msg)
            raise webob.exc.HTTPRequestEntityTooLarge(explanation=msg)

    @utils.mutating
    def update(self, req, image_id, member_id, status):
        """
        Adds a membership to the image.
        :param req: the Request object coming from the wsgi layer
        :param image_id: the image identifier
        :param member_id: the member identifier
        :retval The response body is a mapping of the following form::

            {'member_id': <MEMBER>,
             'image_id': <IMAGE>,
             'status': <MEMBER_STATUS>
             'created_at': ..,
             'updated_at': ..}

        """
        image_repo = self.gateway.get_repo(req.context)
        try:
            image = image_repo.get(image_id)
            member_repo = image.get_member_repo()
            member = member_repo.get(member_id)
            member.status = status
            member_repo.save(member)
            return member
        except exception.NotFound:
            msg = _("Image %s not found.") % image_id
            LOG.warning(msg)
            raise webob.exc.HTTPNotFound(explanation=msg)
        except exception.Forbidden:
            msg = _("Not allowed to update members for image %s.") % image_id
            LOG.warning(msg)
            raise webob.exc.HTTPForbidden(explanation=msg)
        except ValueError as e:
            msg = _("Incorrect request: %s") % utils.exception_to_str(e)
            LOG.warning(msg)
            raise webob.exc.HTTPBadRequest(explanation=msg)

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
                 'status': <MEMBER_STATUS>
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
        except exception.NotFound:
            msg = _("Image %s not found.") % image_id
            LOG.warning(msg)
            raise webob.exc.HTTPNotFound(explanation=msg)
        except exception.Forbidden:
            msg = _("Not allowed to list members for image %s.") % image_id
            LOG.warning(msg)
            raise webob.exc.HTTPForbidden(explanation=msg)

    def show(self, req, image_id, member_id):
        """
        Returns the membership of the tenant wrt to the image_id specified.

        :param req: the Request object coming from the wsgi layer
        :param image_id: The image identifier
        :retval The response body is a mapping of the following form::

            {'member_id': <MEMBER>,
             'image_id': <IMAGE>,
             'status': <MEMBER_STATUS>
             'created_at': ..,
             'updated_at': ..}
        """
        image_repo = self.gateway.get_repo(req.context)
        try:
            image = image_repo.get(image_id)
            member_repo = image.get_member_repo()
            member = member_repo.get(member_id)
            return member
        except (exception.NotFound, exception.Forbidden):
            msg = _("Image %s not found.") % image_id
            LOG.warning(msg)
            raise webob.exc.HTTPNotFound(explanation=msg)

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
            return webob.Response(body='', status=204)
        except exception.NotFound:
            msg = _("Image %s not found.") % image_id
            LOG.warning(msg)
            raise webob.exc.HTTPNotFound(explanation=msg)
        except exception.Forbidden:
            msg = _("Not allowed to delete members for image %s.") % image_id
            LOG.warning(msg)
            raise webob.exc.HTTPForbidden(explanation=msg)


class RequestDeserializer(wsgi.JSONRequestDeserializer):

    def __init__(self):
        super(RequestDeserializer, self).__init__()

    def _get_request_body(self, request):
        output = super(RequestDeserializer, self).default(request)
        if 'body' not in output:
            msg = _('Body expected in request.')
            raise webob.exc.HTTPBadRequest(explanation=msg)
        return output['body']

    def create(self, request):
        body = self._get_request_body(request)
        try:
            member_id = body['member']
            if not member_id:
                raise ValueError()
        except KeyError:
            msg = _("Member to be added not specified")
            raise webob.exc.HTTPBadRequest(explanation=msg)
        except ValueError:
            msg = _("Member can't be empty")
            raise webob.exc.HTTPBadRequest(explanation=msg)
        return dict(member_id=member_id)

    def update(self, request):
        body = self._get_request_body(request)
        try:
            status = body['status']
        except KeyError:
            msg = _("Status not specified")
            raise webob.exc.HTTPBadRequest(explanation=msg)
        return dict(status=status)


class ResponseSerializer(wsgi.JSONResponseSerializer):
    def __init__(self, schema=None):
        super(ResponseSerializer, self).__init__()
        self.schema = schema or get_schema()

    def _format_image_member(self, member):
        member_view = {}
        attributes = ['member_id', 'image_id', 'status']
        for key in attributes:
            member_view[key] = getattr(member, key)
        member_view['created_at'] = timeutils.isotime(member.created_at)
        member_view['updated_at'] = timeutils.isotime(member.updated_at)
        member_view['schema'] = '/v2/schemas/member'
        member_view = self.schema.filter(member_view)
        return member_view

    def create(self, response, image_member):
        image_member_view = self._format_image_member(image_member)
        body = jsonutils.dumps(image_member_view, ensure_ascii=False)
        response.unicode_body = six.text_type(body)
        response.content_type = 'application/json'

    def update(self, response, image_member):
        image_member_view = self._format_image_member(image_member)
        body = jsonutils.dumps(image_member_view, ensure_ascii=False)
        response.unicode_body = six.text_type(body)
        response.content_type = 'application/json'

    def index(self, response, image_members):
        image_members = image_members['members']
        image_members_view = []
        for image_member in image_members:
            image_member_view = self._format_image_member(image_member)
            image_members_view.append(image_member_view)
        totalview = dict(members=image_members_view)
        totalview['schema'] = '/v2/schemas/members'
        body = jsonutils.dumps(totalview, ensure_ascii=False)
        response.unicode_body = six.text_type(body)
        response.content_type = 'application/json'

    def show(self, response, image_member):
        image_member_view = self._format_image_member(image_member)
        body = jsonutils.dumps(image_member_view, ensure_ascii=False)
        response.unicode_body = six.text_type(body)
        response.content_type = 'application/json'


_MEMBER_SCHEMA = {
    'member_id': {
        'type': 'string',
        'description': _('An identifier for the image member (tenantId)')
    },
    'image_id': {
        'type': 'string',
        'description': _('An identifier for the image'),
        'pattern': ('^([0-9a-fA-F]){8}-([0-9a-fA-F]){4}-([0-9a-fA-F]){4}'
                    '-([0-9a-fA-F]){4}-([0-9a-fA-F]){12}$'),
    },
    'created_at': {
        'type': 'string',
        'description': _('Date and time of image member creation'),
        # TODO(brian-rosmaita): our jsonschema library doesn't seem to like the
        # format attribute, figure out why (and also fix in images.py)
        # 'format': 'date-time',
    },
    'updated_at': {
        'type': 'string',
        'description': _('Date and time of last modification of image member'),
        # 'format': 'date-time',
    },
    'status': {
        'type': 'string',
        'description': _('The status of this image member'),
        'enum': [
            'pending',
            'accepted',
            'rejected'
        ]
    },
    'schema': {'type': 'string'}
}


def get_schema():
    properties = copy.deepcopy(_MEMBER_SCHEMA)
    schema = glance.schema.Schema('member', properties)
    return schema


def get_collection_schema():
    member_schema = get_schema()
    return glance.schema.CollectionSchema('members', member_schema)


def create_resource():
    """Image Members resource factory method"""
    deserializer = RequestDeserializer()
    serializer = ResponseSerializer()
    controller = ImageMembersController()
    return wsgi.Resource(controller, deserializer, serializer)
