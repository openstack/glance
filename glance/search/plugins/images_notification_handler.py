# Copyright (c) 2014 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from oslo_log import log as logging
import oslo_messaging

from glance.common import utils
from glance.search.plugins import base

LOG = logging.getLogger(__name__)


class ImageHandler(base.NotificationBase):

    def __init__(self, *args, **kwargs):
        super(ImageHandler, self).__init__(*args, **kwargs)
        self.image_delete_keys = ['deleted_at', 'deleted',
                                  'is_public', 'properties']

    def process(self, ctxt, publisher_id, event_type, payload, metadata):
        try:
            actions = {
                "image.create": self.create,
                "image.update": self.update,
                "image.delete": self.delete
            }
            actions[event_type](payload)
            return oslo_messaging.NotificationResult.HANDLED
        except Exception as e:
            LOG.error(utils.exception_to_str(e))

    def create(self, payload):
        id = payload['id']
        payload = self.format_image(payload)
        self.engine.create(
            index=self.index_name,
            doc_type=self.document_type,
            body=payload,
            id=id
        )

    def update(self, payload):
        id = payload['id']
        payload = self.format_image(payload)
        doc = {"doc": payload}
        self.engine.update(
            index=self.index_name,
            doc_type=self.document_type,
            body=doc,
            id=id
        )

    def delete(self, payload):
        id = payload['id']
        self.engine.delete(
            index=self.index_name,
            doc_type=self.document_type,
            id=id
        )

    def format_image(self, payload):
        visibility = 'public' if payload['is_public'] else 'private'
        payload['visibility'] = visibility

        payload.update(payload.get('properties', '{}'))

        for key in payload.keys():
            if key in self.image_delete_keys:
                del payload[key]

        return payload
