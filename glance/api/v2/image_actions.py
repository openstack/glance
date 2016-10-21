# Copyright 2015 OpenStack Foundation.
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
from six.moves import http_client as http
import webob.exc

from glance.api import policy
from glance.common import exception
from glance.common import utils
from glance.common import wsgi
import glance.db
import glance.gateway
from glance.i18n import _LI
import glance.notifier


LOG = logging.getLogger(__name__)


class ImageActionsController(object):
    def __init__(self, db_api=None, policy_enforcer=None, notifier=None,
                 store_api=None):
        self.db_api = db_api or glance.db.get_api()
        self.policy = policy_enforcer or policy.Enforcer()
        self.notifier = notifier or glance.notifier.Notifier()
        self.store_api = store_api or glance_store
        self.gateway = glance.gateway.Gateway(self.db_api, self.store_api,
                                              self.notifier, self.policy)

    @utils.mutating
    def deactivate(self, req, image_id):
        image_repo = self.gateway.get_repo(req.context)
        try:
            image = image_repo.get(image_id)
            status = image.status
            image.deactivate()
            # not necessary to change the status if it's already 'deactivated'
            if status == 'active':
                image_repo.save(image, from_state='active')
            LOG.info(_LI("Image %s is deactivated"), image_id)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except exception.Forbidden as e:
            LOG.debug("User not permitted to deactivate image '%s'", image_id)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.InvalidImageStatusTransition as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)

    @utils.mutating
    def reactivate(self, req, image_id):
        image_repo = self.gateway.get_repo(req.context)
        try:
            image = image_repo.get(image_id)
            status = image.status
            image.reactivate()
            # not necessary to change the status if it's already 'active'
            if status == 'deactivated':
                image_repo.save(image, from_state='deactivated')
            LOG.info(_LI("Image %s is reactivated"), image_id)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except exception.Forbidden as e:
            LOG.debug("User not permitted to reactivate image '%s'", image_id)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.InvalidImageStatusTransition as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)


class ResponseSerializer(wsgi.JSONResponseSerializer):

    def deactivate(self, response, result):
        response.status_int = http.NO_CONTENT

    def reactivate(self, response, result):
        response.status_int = http.NO_CONTENT


def create_resource():
    """Image data resource factory method"""
    deserializer = None
    serializer = ResponseSerializer()
    controller = ImageActionsController()
    return wsgi.Resource(controller, deserializer, serializer)
