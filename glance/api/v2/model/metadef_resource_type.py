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
from wsme import types

from glance.common.wsme_utils import WSMEModelTransformer


class ResourceTypeAssociation(types.Base, WSMEModelTransformer):
    name = wsme.wsattr(types.text, mandatory=True)
    prefix = wsme.wsattr(types.text, mandatory=False)
    properties_target = wsme.wsattr(types.text, mandatory=False)

    # Not using datetime since time format has to be
    # in oslo_utils.timeutils.isotime() format
    created_at = wsme.wsattr(types.text, mandatory=False)
    updated_at = wsme.wsattr(types.text, mandatory=False)

    def __init__(self, **kwargs):
        super(ResourceTypeAssociation, self).__init__(**kwargs)


class ResourceTypeAssociations(types.Base, WSMEModelTransformer):

    resource_type_associations = wsme.wsattr([ResourceTypeAssociation],
                                             mandatory=False)

    def __init__(self, **kwargs):
        super(ResourceTypeAssociations, self).__init__(**kwargs)


class ResourceType(types.Base, WSMEModelTransformer):
    name = wsme.wsattr(types.text, mandatory=True)

    # Not using datetime since time format has to be
    # in oslo_utils.timeutils.isotime() format
    created_at = wsme.wsattr(types.text, mandatory=False)
    updated_at = wsme.wsattr(types.text, mandatory=False)

    def __init__(self, **kwargs):
        super(ResourceType, self).__init__(**kwargs)


class ResourceTypes(types.Base, WSMEModelTransformer):

    resource_types = wsme.wsattr([ResourceType], mandatory=False)

    def __init__(self, **kwargs):
        super(ResourceTypes, self).__init__(**kwargs)
