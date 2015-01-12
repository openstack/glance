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

import wsme
from wsme.rest import json
from wsme import types

from glance.api.v2.model.metadef_object import MetadefObject
from glance.api.v2.model.metadef_property_type import PropertyType
from glance.api.v2.model.metadef_resource_type import ResourceTypeAssociation
from glance.api.v2.model.metadef_tag import MetadefTag
from glance.common.wsme_utils import WSMEModelTransformer


class Namespace(types.Base, WSMEModelTransformer):

    # Base fields
    namespace = wsme.wsattr(types.text, mandatory=True)
    display_name = wsme.wsattr(types.text, mandatory=False)
    description = wsme.wsattr(types.text, mandatory=False)
    visibility = wsme.wsattr(types.text, mandatory=False)
    protected = wsme.wsattr(bool, mandatory=False)
    owner = wsme.wsattr(types.text, mandatory=False)

    # Not using datetime since time format has to be
    # in oslo_utils.timeutils.isotime() format
    created_at = wsme.wsattr(types.text, mandatory=False)
    updated_at = wsme.wsattr(types.text, mandatory=False)

    # Contained fields
    resource_type_associations = wsme.wsattr([ResourceTypeAssociation],
                                             mandatory=False)
    properties = wsme.wsattr({types.text: PropertyType}, mandatory=False)
    objects = wsme.wsattr([MetadefObject], mandatory=False)
    tags = wsme.wsattr([MetadefTag], mandatory=False)

    # Generated fields
    self = wsme.wsattr(types.text, mandatory=False)
    schema = wsme.wsattr(types.text, mandatory=False)

    def __init__(cls, **kwargs):
        super(Namespace, cls).__init__(**kwargs)

    @staticmethod
    def to_model_properties(db_property_types):
        property_types = {}
        for db_property_type in db_property_types:
            # Convert the persisted json schema to a dict of PropertyTypes
            property_type = json.fromjson(
                PropertyType, db_property_type.schema)
            property_type_name = db_property_type.name
            property_types[property_type_name] = property_type

        return property_types


class Namespaces(types.Base, WSMEModelTransformer):

    namespaces = wsme.wsattr([Namespace], mandatory=False)

    # Pagination
    next = wsme.wsattr(types.text, mandatory=False)
    schema = wsme.wsattr(types.text, mandatory=True)
    first = wsme.wsattr(types.text, mandatory=True)

    def __init__(self, **kwargs):
        super(Namespaces, self).__init__(**kwargs)
