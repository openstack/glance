# Copyright 2012 OpenStack LLC.
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

import webob.exc

from glance.common import exception
from glance.common import utils
from glance.common import wsgi
import glance.db
import glance.schema


class Controller(object):
    def __init__(self, db=None):
        self.db_api = db or glance.db.get_api()
        self.db_api.configure_db()

    def index(self, req, image_id):
        #NOTE(bcwaldon): call image_get to ensure user has permission
        self.db_api.image_get(req.context, image_id)

        members = self.db_api.image_member_find(req.context, image_id=image_id)

        #TODO(bcwaldon): We have to filter on non-deleted members
        # manually. This should be done for us in the db api
        return {
            'access_records': filter(lambda m: not m['deleted'], members),
            'image_id': image_id,
        }

    def show(self, req, image_id, tenant_id):
        members = self.db_api.image_member_find(req.context,
                                                image_id=image_id,
                                                member=tenant_id)
        try:
            return members[0]
        except IndexError:
            raise webob.exc.HTTPNotFound()

    @utils.mutating
    def create(self, req, image_id, access_record):
        #TODO(bcwaldon): Refactor these methods so we don't need to
        # explicitly retrieve a session object here
        session = self.db_api.get_session()
        try:
            image = self.db_api.image_get(req.context, image_id,
                    session=session)
        except exception.NotFound:
            raise webob.exc.HTTPNotFound()
        except exception.Forbidden:
            # If it's private and doesn't belong to them, don't let on
            # that it exists
            raise webob.exc.HTTPNotFound()

        # Image is visible, but authenticated user still may not be able to
        # share it
        if not self.db_api.is_image_sharable(req.context, image):
            msg = _("No permission to share that image")
            raise webob.exc.HTTPForbidden(msg)

        access_record['image_id'] = image_id
        return self.db_api.image_member_create(req.context, access_record)

    @utils.mutating
    def delete(self, req, image_id, tenant_id):
        #TODO(bcwaldon): Refactor these methods so we don't need to explicitly
        # retrieve a session object here
        session = self.db_api.get_session()
        members = self.db_api.image_member_find(req.context,
                                                image_id=image_id,
                                                member=tenant_id,
                                                session=session)
        try:
            member = members[0]
        except IndexError:
            raise webob.exc.HTTPNotFound()

        self.db_api.image_member_delete(req.context, member, session=session)


class RequestDeserializer(wsgi.JSONRequestDeserializer):
    def __init__(self):
        super(RequestDeserializer, self).__init__()
        self.schema = get_schema()

    def create(self, request):
        output = super(RequestDeserializer, self).default(request)
        body = output.pop('body')
        self.schema.validate(body)
        body['member'] = body.pop('tenant_id')
        output['access_record'] = body
        return output


class ResponseSerializer(wsgi.JSONResponseSerializer):
    def _get_access_href(self, image_id, tenant_id=None):
        link = '/v2/images/%s/access' % image_id
        if tenant_id:
            link = '%s/%s' % (link, tenant_id)
        return link

    def _format_access(self, access):
        self_link = self._get_access_href(access['image_id'], access['member'])
        return {
                'tenant_id': access['member'],
                'can_share': access['can_share'],
                'self':  self_link,
                'schema': '/v2/schemas/image/access',
                'image': '/v2/images/%s' % access['image_id'],
            }

    def show(self, response, access):
        response.body = json.dumps(self._format_access(access))
        response.content_type = 'application/json'

    def index(self, response, result):
        access_records = result['access_records']
        first_link = '/v2/images/%s/access' % result['image_id']
        body = {
            'access_records': [self._format_access(a)
                               for a in access_records],
            'first': first_link,
            'schema': '/v2/schemas/image/accesses',
        }
        response.body = json.dumps(body)
        response.content_type = 'application/json'

    def create(self, response, access):
        response.status_int = 201
        response.location = self._get_access_href(access['image_id'],
                                                  access['member'])
        response.body = json.dumps(self._format_access(access))
        response.content_type = 'application/json'

    def delete(self, response, result):
        response.status_int = 204


def get_schema():
    properties = {
        'tenant_id': {
            'type': 'string',
            'description': 'The tenant identifier',
        },
        'can_share': {
            'type': 'boolean',
            'description': 'Ability of tenant to share with others',
            'default': False,
        },
        'self': {
            'type': 'string',
            'description': 'A link to this resource',
        },
        'schema': {
            'type': 'string',
            'description': 'A link to the schema describing this resource',
        },
        'image': {
            'type': 'string',
            'description': 'A link to the image related to this resource',
        },
    }
    links = [
        {'rel': 'self', 'href': '{self}'},
        {'rel': 'up', 'href': '{image}'},
        {'rel': 'describedby', 'href': '{schema}'},
    ]
    return glance.schema.Schema('access', properties, links)


def get_collection_schema():
    access_schema = get_schema()
    return glance.schema.CollectionSchema('accesses', access_schema)


def create_resource():
    """Image access resource factory method"""
    deserializer = RequestDeserializer()
    serializer = ResponseSerializer()
    controller = Controller()
    return wsgi.Resource(controller, deserializer, serializer)
