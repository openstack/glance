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
=================
Glance API Server
=================

Configuration Options
---------------------

    `chunksize`: Set to the size, in bytes, that you want
                 Glance to stream chunks of the image data.
                 Defaults to 64M
"""

import json
import logging

import routes
from webob import Response
from webob.exc import (HTTPNotFound,
                       HTTPConflict,
                       HTTPBadRequest)

from glance.common import exception
from glance.common import flags
from glance.common import wsgi
from glance.store import get_from_backend, delete_from_backend
from glance import registry


flags.DEFINE_integer('image_read_chunksize', 64*1024*1024,
                     'Size in bytes to read chunks of image data.')


FLAGS = flags.FLAGS


class Controller(wsgi.Controller):

    """
    Main WSGI application controller for Glance.
    
    The Glance API is a RESTful web service for image data. The API
    is as follows::
        
        GET /images -- Returns a set of brief metadata about images
        GET /images/detail -- Returns a set of detailed metadata about
                              images
        HEAD /images/<ID> -- Return metadata about an image with id <ID>
        GET /images/<ID> -- Return image data for image with id <ID>
        POST /images -- Store image data and return metadata about the
                        newly-stored image
        PUT /images/<ID> -- Not supported.  Once images are created, they
                            are immutable
        DELETE /images/<ID> -- Delete the image with id <ID>
    """
    
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
        image = self.get_image_meta_or_404(req, id)

        res = Response(request=req)
        self.inject_image_meta_headers(res, image)

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
            return HTTPConflict()
        except exception.Invalid:
            return HTTPBadRequest()

    def update(self, req, id):
        """Updates an existing image with the registry.

        :param req: Request body.  A JSON-ified dict of information about
                    the image.  This will replace the information in the
                    registry about this image
        :param id:  The opaque internal identifier for the image

        :retval Returns the updated image information as a mapping,

        """
        image = self.get_image_meta_or_404(req, id)

        image_data = json.loads(req.body)['image']
        updated_image = registry.update_image_metadata(id, image_data)
        return dict(image=updated_image)

    def show(self, req, id):
        """
        Query the registry service for the image registry for the passed in 
        req['uri']. If it exists, we connect to the appropriate backend as
        determined by the URI scheme and yield chunks of data back to the
        client. 

        Optionally, we can pass in 'registry' which will use a given
        RegistryAdapter for the request. This is useful for testing.
        """
        image = self.get_image_meta_or_404(req, id)

        def image_iterator():
            for file in image['files']:
                chunks = get_from_backend(file['location'],
                                                   expected_size=file['size'])

                for chunk in chunks:
                    yield chunk

        res = Response(app_iter=image_iterator(),
                       content_type="text/plain")
        self.inject_image_meta_headers(res, image)
        return req.get_response(res)

    def delete(self, req, id):
        """
        Deletes the image and all its chunks from the Glance

        :param request: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :raises HttpBadRequest if image registry is invalid
        :raises HttpNotFound if image or any chunk is not available
        :raises HttpNotAuthorized if image or any chunk is not
                deleteable by the requesting user
        """
        image = self.get_image_meta_or_404(req, id)

        for file in image['files']:
            delete_from_backend(file['location'])

        registry.delete_image_metadata(id)

    def get_image_meta_or_404(self, request, id):
        """
        Grabs the image metadata for an image with a supplied
        identifier or raises an HTTPNotFound (404) response

        :param request: The WSGI/Webob Request object
        :param id: The opaque image identifier

        :raises HTTPNotFound if image does not exist
        """
        try:
            return registry.get_image_metadata(id)
        except exception.NotFound:
            raise HTTPNotFound(body='Image not found',
                               request=request,
                               content_type='text/plain')

    def inject_image_meta_headers(self, response, image_meta):
        """
        Given a response and mapping of image metadata, injects
        the Response with a set of HTTP headers for the image
        metadata. Each main image metadata field is injected
        as a HTTP header with key 'x-image-meta-<FIELD>' except
        for the properties field, which is further broken out
        into a set of 'x-image-meta-property-<KEY>' headers

        :param response: The Webob Response object
        :param image_meta: Mapping of image metadata
        """
        for k, v in image_meta.iteritems():
            if k == 'properties':
                for pk, pv in v.iteritems():
                    response.headers.add("x-image-meta-property-%s"
                                         % pk.lower(), pv)

            response.headers.add("x-image-meta-%s" % k.lower(), v)


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
