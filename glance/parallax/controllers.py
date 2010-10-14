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

import json
import routes
from webob import exc

from glance.common import wsgi
from glance.common import exception
from glance.parallax import db


class ImageController(wsgi.Controller):

    """Image Controller """
    
    def index(self, req):
        """Return basic information for all public, non-deleted images
        
        :param req: the Request object coming from the wsgi layer
        :retval a mapping of the following form::

            dict(images=[image_list])

        Where image_list is a sequence of mappings::

            {'id': image_id, 'name': image_name}
        
        """
        images = db.image_get_all_public(None)
        image_dicts = [dict(id=i['id'], name=i['name']) for i in images]
        return dict(images=image_dicts)

    def detail(self, req):
        """Return detailed information for all public, non-deleted images
        
        :param req: the Request object coming from the wsgi layer
        :retval a mapping of the following form::

            dict(images=[image_list])

        Where image_list is a sequence of mappings containing
        all image model fields.
        
        """
        images = db.image_get_all_public(None)
        image_dicts = [self._make_image_dict(i) for i in images]
        return dict(images=image_dicts)

    def show(self, req, id):
        """Return data about the given image id."""
        try:
            image = db.image_get(None, id)
        except exception.NotFound:
            raise exc.HTTPNotFound()
        
        return dict(image=self._make_image_dict(image))

    def delete(self, req, id):
        """Deletes an existing image with the registry.

        :param req: Request body.  Ignored.
        :param id:  The opaque internal identifier for the image

        :retval Returns 200 if delete was successful, a fault if not.

        """
        context = None
        updated_image = db.image_destroy(context, id)

    def create(self, req):
        """Registers a new image with the registry.

        :param req: Request body.  A JSON-ified dict of information about
                    the image.

        :retval Returns the newly-created image information as a mapping,
                which will include the newly-created image's internal id
                in the 'id' field

        """
        image_data = json.loads(req.body)

        # Ensure the image has a status set
        image_data.setdefault('status', 'available')

        context = None
        new_image = db.image_create(context, image_data)
        return dict(new_image)

    def update(self, req, id):
        """Updates an existing image with the registry.

        :param req: Request body.  A JSON-ified dict of information about
                    the image.  This will replace the information in the
                    registry about this image
        :param id:  The opaque internal identifier for the image

        :retval Returns the updated image information as a mapping,

        """
        image_data = json.loads(req.body)

        context = None
        updated_image = db.image_update(context, id, image_data)
        return dict(updated_image)

    @staticmethod
    def _make_image_dict(image):
        """Create a dict representation of an image which we can use to
        serialize the image.
        
        """
        
        def _fetch_attrs(d, attrs):
            return dict([(a, d[a]) for a in attrs])

        file_attrs = db.BASE_MODEL_ATTRS | set(['location', 'size'])
        files = [_fetch_attrs(f, file_attrs) for f in image['files']]

        # TODO(sirp): should this be a dict, or a list of dicts?
        # A plain dict is more convenient, but list of dicts would provide
        # access to created_at, etc
        metadata = dict((m['key'], m['value']) for m in image['metadata'] 
                        if not m['deleted'])

        image_attrs = db.BASE_MODEL_ATTRS | set(['name', 'image_type', 'status', 'is_public'])
        image_dict = _fetch_attrs(image, image_attrs)

        image_dict['files'] = files
        image_dict['metadata'] = metadata
        return image_dict


class API(wsgi.Router):
    """WSGI entry point for all Parallax requests."""

    def __init__(self):
        # TODO(sirp): should we add back the middleware for parallax?
        mapper = routes.Mapper()
        mapper.resource("image", "images", controller=ImageController(),
                       collection={'detail': 'GET'})
        mapper.connect("/", controller=ImageController(), action="index")
        super(API, self).__init__(mapper)
