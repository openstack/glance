# Copyright 2015 Intel Corporation
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

from sqlalchemy.orm import joinedload

from oslo_utils import timeutils

from glance.api import policy
from glance.common import property_utils
import glance.db
from glance.db.sqlalchemy import models
from glance.search.plugins import base
from glance.search.plugins import images_notification_handler


class ImageIndex(base.IndexBase):
    def __init__(self, db_api=None, policy_enforcer=None):
        super(ImageIndex, self).__init__()
        self.db_api = db_api or glance.db.get_api()
        self.policy = policy_enforcer or policy.Enforcer()
        if property_utils.is_property_protection_enabled():
            self.property_rules = property_utils.PropertyRules(self.policy)
        self._image_base_properties = [
            'checksum', 'created_at', 'container_format', 'disk_format', 'id',
            'min_disk', 'min_ram', 'name', 'size', 'virtual_size', 'status',
            'tags', 'updated_at', 'visibility', 'protected', 'owner',
            'members']

    def get_index_name(self):
        return 'glance'

    def get_document_type(self):
        return 'image'

    def get_mapping(self):
        return {
            'dynamic': True,
            'properties': {
                'id': {'type': 'string', 'index': 'not_analyzed'},
                'name': {'type': 'string'},
                'description': {'type': 'string'},
                'tags': {'type': 'string'},
                'disk_format': {'type': 'string'},
                'container_format': {'type': 'string'},
                'size': {'type': 'long'},
                'virtual_size': {'type': 'long'},
                'status': {'type': 'string'},
                'visibility': {'type': 'string'},
                'checksum': {'type': 'string'},
                'min_disk': {'type': 'long'},
                'min_ram': {'type': 'long'},
                'owner': {'type': 'string', 'index': 'not_analyzed'},
                'protected': {'type': 'boolean'},
                'members': {'type': 'string', 'index': 'not_analyzed'},
                "created_at": {'type': 'date'},
                "updated_at": {'type': 'date'}
            },
        }

    def get_rbac_filter(self, request_context):
        return [
            {
                "and": [
                    {
                        'or': [
                            {
                                'term': {
                                    'owner': request_context.owner
                                }
                            },
                            {
                                'term': {
                                    'visibility': 'public'
                                }
                            },
                            {
                                'term': {
                                    'members': request_context.tenant
                                }
                            }
                        ]
                    },
                    {
                        'type': {
                            'value': self.get_document_type()
                        }
                    }
                ]
            }
        ]

    def filter_result(self, result, request_context):
        if property_utils.is_property_protection_enabled():
            hits = result['hits']['hits']
            for hit in hits:
                if hit['_type'] == self.get_document_type():
                    source = hit['_source']
                    for key in source.keys():
                        if key not in self._image_base_properties:
                            if not self.property_rules.check_property_rules(
                                    key, 'read', request_context):
                                del hit['_source'][key]
        return result

    def get_objects(self):
        session = self.db_api.get_session()
        images = session.query(models.Image).options(
            joinedload('properties'), joinedload('members'), joinedload('tags')
        ).filter_by(deleted=False)
        return images

    def serialize(self, obj):
        visibility = 'public' if obj.is_public else 'private'
        members = []
        for member in obj.members:
            if member.status == 'accepted' and member.deleted == 0:
                members.append(member.member)

        document = {
            'id': obj.id,
            'name': obj.name,
            'tags': obj.tags,
            'disk_format': obj.disk_format,
            'container_format': obj.container_format,
            'size': obj.size,
            'virtual_size': obj.virtual_size,
            'status': obj.status,
            'visibility': visibility,
            'checksum': obj.checksum,
            'min_disk': obj.min_disk,
            'min_ram': obj.min_ram,
            'owner': obj.owner,
            'protected': obj.protected,
            'members': members,
            'created_at': timeutils.isotime(obj.created_at),
            'updated_at': timeutils.isotime(obj.updated_at)
        }
        for image_property in obj.properties:
            document[image_property.name] = image_property.value

        return document

    def get_notification_handler(self):
        return images_notification_handler.ImageHandler(
            self.engine,
            self.get_index_name(),
            self.get_document_type()
        )

    def get_notification_supported_events(self):
        return ['image.create', 'image.update', 'image.delete']
