# Copyright 2012 OpenStack LLC.
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

from glance.common import exception


UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
UUID2 = '971ec09a-8067-4bc8-a91f-ae3557f1c4c7'

TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'
TENANT2 = '2c014f32-55eb-467d-8fcb-4bd706012f81'


class FakeRequest(object):
    @property
    def context(self):
        return


class FakeDB(object):

    def __init__(self):
        self.images = {
            UUID1: self._image_format(UUID1),
            UUID2: self._image_format(UUID2),
        }
        self.members = {
            UUID1: [
                self._image_member_format(UUID1, TENANT1, True),
                self._image_member_format(UUID1, TENANT2, False),
            ],
            UUID2: [],
        }

    def reset(self):
        self.images = {}
        self.members = {}

    def configure_db(*args, **kwargs):
        pass

    def _image_member_format(self, image_id, tenant_id, can_share):
        return {
            'image_id': image_id,
            'member': tenant_id,
            'can_share': can_share,
        }

    def _image_format(self, image_id):
        return {'id': image_id, 'name': 'image-name', 'foo': 'bar'}

    def image_get(self, context, image_id):
        try:
            return self.images[image_id]
        except KeyError:
            raise exception.ImageNotFound(image_id=image_id)

    def image_get_all(self, context):
        return self.images.values()

    def get_image_members(self, context, image_id):
        try:
            self.images[image_id]
        except KeyError:
            raise exception.ImageNotFound()
        else:
            return self.members.get(image_id, [])
