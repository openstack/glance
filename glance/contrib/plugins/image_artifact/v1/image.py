# Copyright (c) 2014 Mirantis, Inc.
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

from glance.common.artifacts import definitions


class ImageAsAnArtifact(definitions.ArtifactType):
    __type_name__ = 'Image'
    __endpoint__ = 'images'

    file = definitions.BinaryObject(required=True)
    disk_format = definitions.String(allowed_values=['ami', 'ari', 'aki',
                                                     'vhd', 'vmdk', 'raw',
                                                     'qcow2', 'vdi', 'iso'],
                                     required=True,
                                     mutable=False)
    container_format = definitions.String(allowed_values=['ami', 'ari',
                                                          'aki', 'bare',
                                                          'ovf', 'ova'],
                                          required=True,
                                          mutable=False)
    min_disk = definitions.Integer(min_value=0, default=0)
    min_ram = definitions.Integer(min_value=0, default=0)

    virtual_size = definitions.Integer(min_value=0)
