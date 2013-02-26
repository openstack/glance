# Copyright 2012 OpenStack Foundation.
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

import webob.exc

import glance.api.policy
from glance.common import exception
from glance.common import utils
from glance.common import wsgi
import glance.db
import glance.domain
import glance.gateway
import glance.notifier
import glance.openstack.common.log as logging
import glance.store

LOG = logging.getLogger(__name__)


class ImageDataController(object):
    def __init__(self, db_api=None, store_api=None,
                 policy_enforcer=None, notifier=None,
                 gateway=None):
        if gateway is None:
            db_api = db_api or glance.db.get_api()
            db_api.setup_db_env()
            store_api = store_api or glance.store
            policy = policy_enforcer or glance.api.policy.Enforcer()
            notifier = notifier or glance.notifier.Notifier()
            gateway = glance.gateway.Gateway(db_api, store_api,
                                             notifier, policy)
        self.gateway = gateway

    @utils.mutating
    def upload(self, req, image_id, data, size):
        image_repo = self.gateway.get_repo(req.context)
        try:
            image = image_repo.get(image_id)
            image.status = 'saving'
            image_repo.save(image)
            image.set_data(data, size)
            image_repo.save(image)
        except ValueError, e:
            LOG.debug("Cannot save data for image %s: %s", image_id, e)
            raise webob.exc.HTTPBadRequest(explanation=unicode(e))
        except exception.Duplicate, e:
            msg = _("Unable to upload duplicate image data for image: %s")
            LOG.debug(msg % image_id)
            raise webob.exc.HTTPConflict(explanation=msg, request=req)

        except exception.Forbidden, e:
            msg = _("Not allowed to upload image data for image %s")
            LOG.debug(msg % image_id)
            raise webob.exc.HTTPForbidden(explanation=msg, request=req)

        except exception.NotFound, e:
            raise webob.exc.HTTPNotFound(explanation=unicode(e))

        except exception.StorageFull, e:
            msg = _("Image storage media is full: %s") % e
            LOG.error(msg)
            raise webob.exc.HTTPRequestEntityTooLarge(explanation=msg,
                                                      request=req)

        except exception.StorageWriteDenied, e:
            msg = _("Insufficient permissions on image storage media: %s") % e
            LOG.error(msg)
            raise webob.exc.HTTPServiceUnavailable(explanation=msg,
                                                   request=req)

        except webob.exc.HTTPError, e:
            LOG.error(_("Failed to upload image data due to HTTP error"))
            raise

        except Exception, e:
            LOG.exception(_("Failed to upload image data due to "
                            "internal error"))
            raise

    def download(self, req, image_id):
        image_repo = self.gateway.get_repo(req.context)
        try:
            image = image_repo.get(image_id)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=unicode(e))
        except exception.Forbidden as e:
            raise webob.exc.HTTPForbidden(explanation=unicode(e))

        if not image.locations:
            reason = _("No image data could be found")
            raise webob.exc.HTTPNotFound(reason)
        return image


class RequestDeserializer(wsgi.JSONRequestDeserializer):
    def upload(self, request):
        try:
            request.get_content_type('application/octet-stream')
        except exception.InvalidContentType:
            raise webob.exc.HTTPUnsupportedMediaType()

        image_size = request.content_length or None
        return {'size': image_size, 'data': request.body_file}


class ResponseSerializer(wsgi.JSONResponseSerializer):
    def download(self, response, image):
        response.headers['Content-Type'] = 'application/octet-stream'
        # NOTE(markwash): filesystem store (and maybe others?) cause a problem
        # with the caching middleware if they are not wrapped in an iterator
        # very strange
        response.app_iter = iter(image.get_data())
        #NOTE(saschpe): "response.app_iter = ..." currently resets Content-MD5
        # (https://github.com/Pylons/webob/issues/86), so it should be set
        # afterwards for the time being.
        if image.checksum:
            response.headers['Content-MD5'] = image.checksum
        #NOTE(markwash): "response.app_iter = ..." also erroneously resets the
        # content-length
        response.headers['Content-Length'] = str(image.size)

    def upload(self, response, result):
        response.status_int = 204


def create_resource():
    """Image data resource factory method"""
    deserializer = RequestDeserializer()
    serializer = ResponseSerializer()
    controller = ImageDataController()
    return wsgi.Resource(controller, deserializer, serializer)
