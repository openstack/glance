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

from common.db import api


def make_fake_image():
    """Create a fake image record """
    image = api.image_create(
        None,
        dict(name="Test Image",
             state="available",
             public=True,
             image_type="tarball"))

    api.image_chunk_create(
        None, 
        dict(image_id=image.id,
             location="swift://myacct/mycontainer/obj.tar.gz.0",
             size=101))
    api.image_chunk_create(
        None, 
        dict(image_id=image.id,
             location="swift://myacct/mycontainer/obj.tar.gz.1",
             size=101))

    api.image_metadatum_create(
        None,
        dict(image_id=image.id,
             key_name="testkey",
             key_data="testvalue"))


if __name__ == "__main__":
    make_fake_image()
