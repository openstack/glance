# Copyright (c) 2015 Mirantis, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import uuid

from oslo_utils import timeutils

from glance import i18n

_ = i18n._


class Artifact(object):

    def __init__(self, id, name, version, type_name, type_version,
                 visibility, state, owner, created_at=None,
                 updated_at=None, **kwargs):
        self.id = id
        self.name = name
        self.type_name = type_name
        self.version = version
        self.type_version = type_version
        self.visibility = visibility
        self.state = state
        self.owner = owner
        self.created_at = created_at
        self.updated_at = updated_at
        self.description = kwargs.pop('description', None)
        self.blobs = kwargs.pop('blobs', {})
        self.properties = kwargs.pop('properties', {})
        self.dependencies = kwargs.pop('dependencies', {})
        self.tags = kwargs.pop('tags', [])

        if kwargs:
            message = _("__init__() got unexpected keyword argument '%s'")
            raise TypeError(message % kwargs.keys()[0])


class ArtifactFactory(object):
    def __init__(self, context, klass):
        self.klass = klass
        self.context = context

    def new_artifact(self, name, version, **kwargs):
        id = kwargs.pop('id', str(uuid.uuid4()))
        tags = kwargs.pop('tags', [])
        # pop reserved fields from kwargs dict
        for param in ['owner', 'created_at', 'updated_at',
                      'deleted_at', 'visibility', 'state']:
            kwargs.pop(param, '')
        curr_timestamp = timeutils.utcnow()
        base = self.klass(id=id,
                          name=name,
                          version=version,
                          visibility='private',
                          state='creating',
                          # XXX FIXME remove after using authentification
                          # paste-flavor
                          # (no or '' as owner will always be there)
                          owner=self.context.owner or '',
                          created_at=curr_timestamp,
                          updated_at=curr_timestamp,
                          tags=tags,
                          **kwargs)
        return base
