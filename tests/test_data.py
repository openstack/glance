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


def make_real_image():
    """Create a real image record """

    # TODO(sirp): Create a testing account, and define gflags for
    # test_swift_username and test_swift_api_key
    USERNAME = "blah" # fill these out for testing
    API_KEY = "blah"

    image = db.image_create(
        None,
        dict(name="testsnap",
             state="available",
             public=True,
             image_type="raw"))

    location = (
        "swift://%s:%s@"
        "auth.api.rackspacecloud.com/v1.0/cloudservers"
        "/testsnap_cloudserver11037.tar.gz.0"
    ) % (USERNAME, API_KEY)

    size = 198848316

    db.image_file_create(None, 
        dict(image_id=image.id, location=location, size=size))


def make_fake_image():
    """Create a fake image record """
    image = db.image_create(
        None,
        dict(name="Test Image",
             state="available",
             public=True,
             image_type="raw"))

    db.image_file_create(
        None, 
        dict(image_id=image.id,
             location="teststr://chunk0",
             size=6))
    db.image_file_create(
        None, 
        dict(image_id=image.id,
             location="teststr://chunk1",
             size=6))

    db.image_metadatum_create(
        None,
        dict(image_id=image.id,
             key="testkey",
             value="testvalue"))


if __name__ == "__main__":
    make_fake_image()
    #make_real_image() # NOTE: uncomment if you have a username and api_key
