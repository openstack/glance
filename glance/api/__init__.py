# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
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

from glance import registry
from glance.common import exception


logger = logging.getLogger('glance.api')


class BaseController(object):
    def get_image_meta_or_404(self, request, image_id):
        """
        Grabs the image metadata for an image with a supplied
        identifier or raises an HTTPNotFound (404) response

        :param request: The WSGI/Webob Request object
        :param image_id: The opaque image identifier

        :raises HTTPNotFound if image does not exist
        """
        context = request.context
        try:
            return registry.get_image_metadata(self.options, context, image_id)
        except exception.NotFound:
            msg = _("Image with identifier %s not found") % image_id
            logger.debug(msg)
            raise webob.exc.HTTPNotFound(
                    msg, request=request, content_type='text/plain')
        except exception.NotAuthorized:
            msg = _("Unauthorized image access")
            logger.debug(msg)
            raise webob.exc.HTTPForbidden(msg, request=request,
                                content_type='text/plain')

    def get_active_image_meta_or_404(self, request, image_id):
        """
        Same as get_image_meta_or_404 except that it will raise a 404 if the
        image isn't 'active'.
        """
        image = self.get_image_meta_or_404(request, image_id)
        if image['status'] != 'active':
            msg = _("Image %s is not active") % image_id
            logger.debug(msg)
            raise webob.exc.HTTPNotFound(
                    msg, request=request, content_type='text/plain')
        return image
