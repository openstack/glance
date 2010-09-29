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

from glance.common import wsgi
from glance.common import db
from glance.common import exception
from webob import exc

class Controller(wsgi.Controller):

    _serialization_metadata = {
        'application/xml': {
            "attributes": {
                "image": [ "id", "name", "updated", "created", "status",
                           "serverId", "progress" ]
            }
        }
    }

    def __init__(self):
        pass

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

        chunk_dicts = []
        for chunk in image.image_chunks:
            chunk_dict = dict(location=chunk.location, size=chunk.size)
            chunk_dicts.append(chunk_dict)

        metadata_dicts = []
        for metadatum in image.image_metadata:
            metadatum_dict = dict(key=metadatum.key, value=metadatum.value)
            metadata_dicts.append(metadatum_dict)

        image_dict = dict(id=image.id, name=image.name, state=image.state,
                          public=image.public, chunks=chunk_dicts,
                          metadata=metadata_dicts)
        return dict(image=image_dict)

    def delete(self, req, id):
        """Delete is not currently supported """
        raise exc.HTTPNotImplemented()

    def create(self, req):
        """Create is not currently supported """
        raise exc.HTTPNotImplemented()

    def update(self, req, id):
        """Update is not currently supported """
        raise exc.HTTPNotImplemented()
