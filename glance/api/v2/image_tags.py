# Copyright 2012 OpenStack Foundation
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
import glance_store
from oslo_log import log as logging
from oslo_utils import encodeutils
from six.moves import http_client as http
import webob.exc

from glance.api import policy
from glance.api.v2 import images as v2_api
from glance.common import exception
from glance.common import utils
from glance.common import wsgi
import glance.db
import glance.gateway
from glance.i18n import _
import glance.notifier


LOG = logging.getLogger(__name__)


class Controller(object):
    def __init__(self, db_api=None, policy_enforcer=None, notifier=None,
                 store_api=None):
        self.db_api = db_api or glance.db.get_api()
        self.policy = policy_enforcer or policy.Enforcer()
        self.notifier = notifier or glance.notifier.Notifier()
        self.store_api = store_api or glance_store
        self.gateway = glance.gateway.Gateway(self.db_api, self.store_api,
                                              self.notifier, self.policy)

    @utils.mutating
    def update(self, req, image_id, tag_value):
        image_repo = self.gateway.get_repo(req.context)
        try:
            image = image_repo.get(image_id)
            image.tags.add(tag_value)
            image_repo.save(image)
        except exception.NotFound:
            msg = _("Image %s not found.") % image_id
            LOG.warning(msg)
            raise webob.exc.HTTPNotFound(explanation=msg)
        except exception.Forbidden:
            msg = _("Not allowed to update tags for image %s.") % image_id
            LOG.warning(msg)
            raise webob.exc.HTTPForbidden(explanation=msg)
        except exception.Invalid as e:
            msg = (_("Could not update image: %s")
                   % encodeutils.exception_to_unicode(e))
            LOG.warning(msg)
            raise webob.exc.HTTPBadRequest(explanation=msg)
        except exception.ImageTagLimitExceeded as e:
            msg = (_("Image tag limit exceeded for image %(id)s: %(e)s:")
                   % {"id": image_id,
                      "e": encodeutils.exception_to_unicode(e)})
            LOG.warning(msg)
            raise webob.exc.HTTPRequestEntityTooLarge(explanation=msg)

    @utils.mutating
    def delete(self, req, image_id, tag_value):
        image_repo = self.gateway.get_repo(req.context)
        try:
            image = image_repo.get(image_id)
            if tag_value not in image.tags:
                raise webob.exc.HTTPNotFound()
            image.tags.remove(tag_value)
            image_repo.save(image)
        except exception.NotFound:
            msg = _("Image %s not found.") % image_id
            LOG.warning(msg)
            raise webob.exc.HTTPNotFound(explanation=msg)
        except exception.Forbidden:
            msg = _("Not allowed to delete tags for image %s.") % image_id
            LOG.warning(msg)
            raise webob.exc.HTTPForbidden(explanation=msg)


class ResponseSerializer(wsgi.JSONResponseSerializer):
    def update(self, response, result):
        response.status_int = http.NO_CONTENT

    def delete(self, response, result):
        response.status_int = http.NO_CONTENT


class RequestDeserializer(wsgi.JSONRequestDeserializer):
    def update(self, request):
        try:
            schema = v2_api.get_schema()
            schema_format = {"tags": [request.urlvars.get('tag_value')]}
            schema.validate(schema_format)
        except exception.InvalidObject as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        return super(RequestDeserializer, self).default(request)


def create_resource():
    """Images resource factory method"""
    serializer = ResponseSerializer()
    deserializer = RequestDeserializer()
    controller = Controller()
    return wsgi.Resource(controller, deserializer, serializer)
