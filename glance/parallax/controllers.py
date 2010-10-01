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
Parllax Image controller
"""

import routes
from glance.common import wsgi
from glance.common import exception
from glance.parallax import db
from webob import exc


class ImageController(wsgi.Controller):
    """Image Controller """

    def index(self, req):
        """Index is not currently supported """
        raise exc.HTTPNotImplemented()

    def detail(self, req):
        """Detail is not currently supported """
        raise exc.HTTPNotImplemented()

    def show(self, req, id):
        """Return data about the given image id."""
        try:
            image = db.image_get(None, id)
        except exception.NotFound:
            raise exc.HTTPNotFound()

        files = [dict(location=f.location, size=f.size) for f in image.files]
        metadata = dict((m.key, m.value) for m in image.metadata)
        
        return dict(id=image.id, 
                    name=image.name,
                    state=image.state,
                    public=image.public,
                    files=files,
                    metadata=metadata)

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
        # TODO(sirp): should we add back the middleware for parallax?
        mapper = routes.Mapper()
        mapper.resource("image", "images", controller=ImageController(),
                        collection={'detail': 'GET'})
        super(API, self).__init__(mapper)








