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


from glance.common import wsgi
from glance.common import db
from glance.common import exception
from webob import exc


class Controller(wsgi.Controller):
    """Image Controller """

    # TODO(sirp): this is not currently used, but should eventually
    # incorporate it
    _serialization_metadata = {
        'application/xml': {
            "attributes": {
                "image": [ "id", "name", "updated", "created", "status",
                           "serverId", "progress" ]
            }
        }
    }

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

        file_dicts = [dict(location=f.location, size=f.size)
                      for f in image.files]

        metadata_dicts = [dict(key=m.key, value=m.value)
                          for m in image.metadata]
        
        return dict(id=image.id, 
                    name=image.name,
                    state=image.state,
                    public=image.public,
                    files=file_dicts,
                    metadata=metadata_dicts)

    def delete(self, req, id):
        """Delete is not currently supported """
        raise exc.HTTPNotImplemented()

    def create(self, req):
        """Create is not currently supported """
        raise exc.HTTPNotImplemented()

    def update(self, req, id):
        """Update is not currently supported """
        raise exc.HTTPNotImplemented()

