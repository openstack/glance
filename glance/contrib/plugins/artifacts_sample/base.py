# Copyright 2011-2012 OpenStack Foundation
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

from glance.common.artifacts import definitions


class BaseArtifact(definitions.ArtifactType):
    __type_version__ = "1.0"
    prop1 = definitions.String()
    prop2 = definitions.Integer()
    int_list = definitions.Array(item_type=definitions.Integer(max_value=10,
                                                               min_value=1))
    depends_on = definitions.ArtifactReference(type_name='MyArtifact')
    references = definitions.ArtifactReferenceList()

    image_file = definitions.BinaryObject()
    screenshots = definitions.BinaryObjectList()
