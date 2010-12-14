# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 OpenStack LLC.
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

"""
Glance WSGI servers
"""

import logging

import routes
from webob import exc, Response

from glance.common import wsgi
from glance.common import exception
from glance.parallax import db
from glance.store import get_from_backend, delete_from_backend
from glance.store import registries


class Controller(wsgi.Controller):

    """Main Glance controller"""

    def show(self, req, id):
        """
        Query the parallax service for the image registry for the passed in 
        req['uri']. If it exists, we connect to the appropriate backend as
        determined by the URI scheme and yield chunks of data back to the
        client. 

        Optionally, we can pass in 'registry' which will use a given
        RegistryAdapter for the request. This is useful for testing.
        """
        registry, image = self.get_registry_and_image(req, id)

        def image_iterator():
            for file in image['files']:
                chunks = get_from_backend(file['location'],
                                                   expected_size=file['size'])

                for chunk in chunks:
                    yield chunk

        res = Response(app_iter=image_iterator(),
                       content_type="text/plain")
        return req.get_response(res)
    
    def index(self, req):
        """Index is not currently supported """
        raise exc.HTTPNotImplemented()

    def delete(self, req, id):
        """
        Deletes the image and all its chunks from the Teller service.
        Note that this DOES NOT delete the image from the image
        registry (Parallax or other registry service). The caller
        should delete the metadata from the registry if necessary.

        :param request: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :raises HttpBadRequest if image registry is invalid
        :raises HttpNotFound if image or any chunk is not available
        :raises HttpNotAuthorized if image or any chunk is not
                deleteable by the requesting user
        """
        registry, image = self.get_registry_and_image(req, id)

        try:
            for file in image['files']:
                delete_from_backend(file['location'])
        except exception.NotAuthorized:
            raise exc.HTTPNotAuthorized(body='You are not authorized to '
                                        'delete image chunk %s' % file,
                                        request=req,
                                        content_type='text/plain')
        except exception.NotFound:
            raise exc.HTTPNotFound(body='Image chunk %s not found' %
                                   file, request=req,
                                   content_type='text/plain')

    def create(self, req):
        """Create is not currently supported """
        raise exc.HTTPNotImplemented()

    def update(self, req, id):
        """Update is not currently supported """
        raise exc.HTTPNotImplemented()

    def get_registry_and_image(self, req, id):
        """
        Returns the registry used and the image metadata for a
        supplied image ID and request object.

        :param req: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :raises HttpBadRequest if image registry is invalid
        :raises HttpNotFound if image is not available

        :retval tuple with (registry, image)
        """
        registry = req.str_GET.get('registry', 'parallax')

        try:
            image = registries.lookup_by_registry(registry, id)
            return registry, image
        except registries.UnknownImageRegistry:
            logging.debug("Could not find image registry: %s.", registry)
            raise exc.HTTPBadRequest(body="Unknown registry '%s'" % registry,
                                      request=req,
                                      content_type="text/plain")
        except exception.NotFound:
            raise exc.HTTPNotFound(body='Image not found', request=req,
                                   content_type='text/plain')


class API(wsgi.Router):

    """WSGI entry point for all Glance API requests."""

    def __init__(self):
        mapper = routes.Mapper()
        mapper.resource("image", "images", controller=Controller())
        super(API, self).__init__(mapper)
