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
from glance.registry import db
from glance.store import get_from_backend, delete_from_backend
from glance import registry


class Controller(wsgi.Controller):

    """Main Glance controller"""
    
    def index(self, req):
        """
        Return basic information for all public, non-deleted images
        
        :param req: the Request object coming from the wsgi layer
        :retval a mapping of the following form::

            dict(images=[image_list])

        Where image_list is a sequence of mappings::

            {'id': image_id, 'name': image_name}
        
        """
        images = registry.get_images_list()
        return dict(images=images)

    def detail(self, req):
        """Return detailed information for all public, non-deleted images
        
        :param req: the Request object coming from the wsgi layer
        :retval a mapping of the following form::

            dict(images=[image_list])

        Where image_list is a sequence of mappings containing
        all image model fields.
        
        """
        images = registry.get_images_detail()
        return dict(images=images)

    def meta(self, req, id):
        """Return data about the given image id."""
        reg, image = self.get_registry_and_image(req, id)

        res = Response(request=req)
        for k, v in image.iteritems():
            res.headers.add("x-image-meta-%s" % k.lower(), v)
        return req.get_response(res)

    def create(self, req):
        """Registers a new image with the registry.

        :param req: Request body.  A JSON-ified dict of information about
                    the image.

        :retval Returns the newly-created image information as a mapping,
                which will include the newly-created image's internal id
                in the 'id' field

        """
        image_data = json.loads(req.body)['image']

        # Ensure the image has a status set
        image_data.setdefault('status', 'available')

        try:
            new_image = registry.add_image_metadata(image_data)
            return dict(image=new_image)
        except exception.Duplicate:
            return exc.HTTPConflict()
        except exception.Invalid:
            return exc.HTTPBadRequest()

    def update(self, req, id):
        """Updates an existing image with the registry.

        :param req: Request body.  A JSON-ified dict of information about
                    the image.  This will replace the information in the
                    registry about this image
        :param id:  The opaque internal identifier for the image

        :retval Returns the updated image information as a mapping,

        """
        reg, image = self.get_registry_and_image(req, id)

        try:
            image_data = json.loads(req.body)['image']
            updated_image = registry.update_image_metadata(id)
            return dict(image=updated_image)
        except exception.NotAuthorized:
            raise exc.HTTPNotAuthorized(body='You are not authorized to '
                                        'delete image chunk %s' % file,
                                        request=req,
                                        content_type='text/plain')
        except exception.NotFound:
            raise exc.HTTPNotFound(body='Image chunk %s not found' %
                                   file, request=req,
                                   content_type='text/plain')

    def show(self, req, id):
        """
        Query the registry service for the image registry for the passed in 
        req['uri']. If it exists, we connect to the appropriate backend as
        determined by the URI scheme and yield chunks of data back to the
        client. 

        Optionally, we can pass in 'registry' which will use a given
        RegistryAdapter for the request. This is useful for testing.
        """
        reg, image = self.get_registry_and_image(req, id)

        def image_iterator():
            for file in image['files']:
                chunks = get_from_backend(file['location'],
                                                   expected_size=file['size'])

                for chunk in chunks:
                    yield chunk

        res = Response(app_iter=image_iterator(),
                       content_type="text/plain")
        return req.get_response(res)

    def delete(self, req, id):
        """
        Deletes the image and all its chunks from the Teller service.
        Note that this DOES NOT delete the image from the image
        registry (Registry or other registry service). The caller
        should delete the metadata from the registry if necessary.

        :param request: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :raises HttpBadRequest if image registry is invalid
        :raises HttpNotFound if image or any chunk is not available
        :raises HttpNotAuthorized if image or any chunk is not
                deleteable by the requesting user
        """
        reg, image = self.get_registry_and_image(req, id)

        try:
            for file in image['files']:
                delete_from_backend(file['location'])

            registry.delete_image_metadata(id)
        except exception.NotAuthorized:
            raise exc.HTTPNotAuthorized(body='You are not authorized to '
                                        'delete image chunk %s' % file,
                                        request=req,
                                        content_type='text/plain')
        except exception.NotFound:
            raise exc.HTTPNotFound(body='Image chunk %s not found' %
                                   file, request=req,
                                   content_type='text/plain')

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
        reg = req.str_GET.get('registry', 'registry')

        try:
            image = registry.get_image_metadata(id)
            return reg, image
        except exception.NotFound:
            raise exc.HTTPNotFound(body='Image not found', request=req,
                                   content_type='text/plain')


class API(wsgi.Router):

    """WSGI entry point for all Glance API requests."""

    def __init__(self):
        mapper = routes.Mapper()
        mapper.resource("image", "images", controller=Controller(),
                       collection={'detail': 'GET'})
        mapper.connect("/", controller=Controller(), action="index")
        mapper.connect("/images/{id}", controller=Controller(), action="meta",
                       conditions=dict(method=["HEAD"]))
        super(API, self).__init__(mapper)
