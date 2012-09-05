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

import webob.exc

from glance.api import common
from glance.api import policy
import glance.api.v2 as v2
from glance.common import exception
from glance.common import utils
from glance.common import wsgi
import glance.db
import glance.notifier
import glance.openstack.common.log as logging
import glance.store

LOG = logging.getLogger(__name__)


class ImageDataController(object):
    def __init__(self, db_api=None, store_api=None,
                 policy_enforcer=None, notifier=None):
        self.db_api = db_api or glance.db.get_api()
        self.db_api.configure_db()
        self.store_api = store_api or glance.store
        self.store_api.create_stores()
        self.policy = policy_enforcer or policy.Enforcer()
        self.notifier = notifier or glance.notifier.Notifier()

    def _get_image(self, context, image_id):
        try:
            return self.db_api.image_get(context, image_id)
        except exception.NotFound:
            raise webob.exc.HTTPNotFound(_("Image does not exist"))

    def _enforce(self, req, action):
        """Authorize an action against our policies"""
        try:
            self.policy.enforce(req.context, action, {})
        except exception.Forbidden:
            raise webob.exc.HTTPForbidden()

    @utils.mutating
    def upload(self, req, image_id, data, size):
        try:
            image = self._get_image(req.context, image_id)
            location, size, checksum = self.store_api.add_to_backend(
                    req.context, 'file', image_id, data, size)

        except exception.Duplicate, e:
            msg = _("Unable to upload duplicate image data for image: %s")
            LOG.debug(msg % image_id)
            raise webob.exc.HTTPConflict(explanation=msg, request=req)

        except exception.Forbidden, e:
            msg = _("Not allowed to upload image data for image %s")
            LOG.debug(msg % image_id)
            raise webob.exc.HTTPForbidden(explanation=msg, request=req)

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
            LOG.error("Failed to upload image data due to HTTP error")
            raise

        except Exception, e:
            LOG.exception("Failed to upload image data due to internal error")
            raise

        else:
            v2.update_image_read_acl(req, self.store_api, self.db_api, image)
            values = {'location': location, 'size': size, 'checksum': checksum}
            self.db_api.image_update(req.context, image_id, values)
            updated_image = self._get_image(req.context, image_id)
            self.notifier.info('image.upload', updated_image)

    def download(self, req, image_id):
        self._enforce(req, 'download_image')
        ctx = req.context
        image = self._get_image(ctx, image_id)
        location = image['location']
        if location:
            image_data, image_size = self.store_api.get_from_backend(ctx,
                                                                     location)
            #NOTE(bcwaldon): This is done to match the behavior of the v1 API.
            # The store should always return a size that matches what we have
            # in the database. If the store says otherwise, that's a security
            # risk.
            if image_size is not None:
                image['size'] = int(image_size)
            return {'data': image_data, 'meta': image}
        else:
            raise webob.exc.HTTPNotFound(_("No image data could be found"))


class RequestDeserializer(wsgi.JSONRequestDeserializer):
    def upload(self, request):
        try:
            request.get_content_type('application/octet-stream')
        except exception.InvalidContentType:
            raise webob.exc.HTTPUnsupportedMediaType()

        image_size = request.content_length or None
        return {'size': image_size, 'data': request.body_file}


class ResponseSerializer(wsgi.JSONResponseSerializer):
    def __init__(self, notifier=None):
        super(ResponseSerializer, self).__init__()
        self.notifier = notifier or glance.notifier.Notifier()

    def download(self, response, result):
        size = result['meta']['size']
        checksum = result['meta']['checksum']
        response.headers['Content-Length'] = size
        response.headers['Content-Type'] = 'application/octet-stream'
        if checksum:
            response.headers['Content-MD5'] = checksum
        response.app_iter = common.size_checked_iter(
                response, result['meta'], size, result['data'], self.notifier)

    def upload(self, response, result):
        response.status_int = 201


def create_resource():
    """Image data resource factory method"""
    deserializer = RequestDeserializer()
    serializer = ResponseSerializer()
    controller = ImageDataController()
    return wsgi.Resource(controller, deserializer, serializer)
