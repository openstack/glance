# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 OpenStack, LLC
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

from glance.parallax import db


def make_swift_image():
    """Create a real image record """

    # TODO(sirp): Create a testing account, and define gflags for
    # test_swift_username and test_swift_api_key
    USERNAME = "your user name here" # fill these out for testing
    API_KEY = "your api key here"
    #IMAGE_CHUNKS = [("filename", 123)] # filename, size in bytes
    IMAGE_CHUNKS = [("your test chunk here", 12345)]

    image = db.image_create(
        None,
        dict(name="testsnap",
             state="available",
             public=True,
             image_type="raw"))

    for obj, size in IMAGE_CHUNKS:
        location = (
            "swift://%s:%s@auth.api.rackspacecloud.com/v1.0/cloudservers/%s"
        ) % (USERNAME, API_KEY, obj)

        db.image_file_create(None, 
            dict(image_id=image.id, location=location, size=size))

if __name__ == "__main__":
    make_swift_image() # NOTE: uncomment if you have a username and api_key
