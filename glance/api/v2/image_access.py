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
        image = self.db_api.image_get(req.context, image_id)
        #TODO(bcwaldon): We have to filter on non-deleted members
        # manually. This should be done for us in the db api
        return filter(lambda m: not m['deleted'], image['members'])

    def show(self, req, image_id, tenant_id):
        try:
            return self.db_api.image_member_find(req.context,
                    image_id, tenant_id)
        except exception.NotFound:
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
        member = self.db_api.image_member_find(req.context, image_id,
                tenant_id, session=session)
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

    def _get_access_links(self, access):
        self_link = self._get_access_href(access['image_id'], access['member'])
        return [
            {'rel': 'self', 'href': self_link},
            {'rel': 'describedby', 'href': '/v2/schemas/image/access'},
        ]

    def _format_access(self, access):
        return {
            'tenant_id': access['member'],
            'can_share': access['can_share'],
            'links': self._get_access_links(access),
        }

    def _get_container_links(self, image_id):
        return [{'rel': 'self', 'href': self._get_access_href(image_id)}]

    def show(self, response, access):
        record = {'access_record': self._format_access(access)}
        response.body = json.dumps(record)

    def index(self, response, access_records):
        body = {
            'access_records': [self._format_access(a) for a in access_records],
            'links': [],
        }
        response.body = json.dumps(body)

    def create(self, response, access):
        response.status_int = 201
        response.content_type = 'application/json'
        response.location = self._get_access_href(access['image_id'],
                                                  access['member'])
        response.body = json.dumps({'access': self._format_access(access)})

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
    }
    return glance.schema.Schema('access', properties)


def create_resource():
    """Image access resource factory method"""
    deserializer = RequestDeserializer()
    serializer = ResponseSerializer()
    controller = Controller()
    return wsgi.Resource(controller, deserializer, serializer)
