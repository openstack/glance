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

from glance.common import wsgi, db, exception
from glance.teller.backends import get_from_backend
from glance.teller.parallax import ParallaxAdapter
from webob import exc, Response


class Controller(wsgi.Controller):
    """Image Controller """

    image_lookup_fn = ParallaxAdapter.lookup

    def index(self, request):
        """ Get a list of images, does this even make sense? """
        raise exc.HTTPNotImplemented

    def detail(self, req):
        """Detail is not currently supported """
        raise exc.HTTPNotImplemented()

    def show(self, request, uri):
        """
        Query the parallax service for the image registry for the passed in 
        request['uri']. If it exists, we connect to the appropriate backend as
        determined by the URI scheme and yield chunks of data back to the
        client. 
        """

        #info(twitch) I don't know if this would actually happen in the wild.
        if uri is None:
            return exc.HTTPBadRequest(body="Missing uri", request=request,
                                      content_type="text/plain")

        image = self.image_lookup_fn(uri)
        if not image:
            raise exc.HTTPNotFound(body='Image not found', request=request,
                                   content_type='text/plain')

        def image_iterator():
            for file in image['files']:
                for chunk in get_from_backend(file['location'], 
                                              expected_size=file['size']):
                    yield chunk


        return request.get_response(Response(app_iter=image_iterator()))

    def delete(self, req, id):
        """Delete is not currently supported """
        raise exc.HTTPNotImplemented()

    def create(self, req):
        """Create is not currently supported """
        raise exc.HTTPNotImplemented()

    def update(self, req, id):
        """Update is not currently supported """
        raise exc.HTTPNotImplemented()

