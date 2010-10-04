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
Teller Image controller
"""

import routes
from webob import exc, Response
from glance.common import wsgi
from glance.common import exception
from glance.parallax import db
from glance.teller import backends
from glance.teller import registries


class ImageController(wsgi.Controller):
    """Image Controller """

    def index(self, req):
        """
        Query the parallax service for the image registry for the passed in 
        req['uri']. If it exists, we connect to the appropriate backend as
        determined by the URI scheme and yield chunks of data back to the
        client. 

        Optionally, we can pass in 'registry' which will use a given
        RegistryAdapter for the request. This is useful for testing.
        """
        try:
            uri = req.str_GET['uri']
        except KeyError:
            return exc.HTTPBadRequest(body="Missing uri", request=req,
                                      content_type="text/plain")

        registry = req.str_GET.get('registry', 'parallax')

        try:
            image = registries.lookup_by_registry(registry, uri)
        except registries.UnknownRegistryAdapter:
            return exc.HTTPBadRequest(body="Uknown registry '%s'" % registry,
                                      request=req,
                                      content_type="text/plain")

        if not image:
            raise exc.HTTPNotFound(body='Image not found', request=req,
                                   content_type='text/plain')

        def image_iterator():
            for file in image['files']:
                chunks = backends.get_from_backend(
                    file['location'], expected_size=file['size'])

                for chunk in chunks:
                    yield chunk


        return req.get_response(Response(app_iter=image_iterator()))
    
    def detail(self, req):
        """Detail is not currently supported """
        raise exc.HTTPNotImplemented()

    def show(self, req):
        """Show is not currently supported """
        raise exc.HTTPNotImplemented()

    def delete(self, req, id):
        """Delete is not currently supported """
        raise exc.HTTPNotImplemented()

    def create(self, req):
        """Create is not currently supported """
        raise exc.HTTPNotImplemented()

    def update(self, req, id):
        """Update is not currently supported """
        raise exc.HTTPNotImplemented()


class API(wsgi.Router):
    """WSGI entry point for all Parallax requests."""

    def __init__(self):
        mapper = routes.Mapper()
        mapper.resource("image", "image", controller=ImageController(),
                        collection={'detail': 'GET'})
        super(API, self).__init__(mapper)








