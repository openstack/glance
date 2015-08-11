# Copyright 2011 OpenStack Foundation
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

SUPPORTED_FILTERS = ['name', 'status', 'container_format', 'disk_format',
                     'min_ram', 'min_disk', 'size_min', 'size_max',
                     'is_public', 'changes-since', 'protected']

SUPPORTED_PARAMS = ('limit', 'marker', 'sort_key', 'sort_dir')

# Metadata which only an admin can change once the image is active
ACTIVE_IMMUTABLE = ('size', 'checksum')

# Metadata which cannot be changed (irrespective of the current image state)
IMMUTABLE = ('status',)
