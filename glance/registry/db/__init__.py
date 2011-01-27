# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2010-2011 OpenStack LLC.
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

"""
DB abstraction for Nova and Glance
"""

from glance.registry.db.api import *

# attributes common to all models
BASE_MODEL_ATTRS = set(['id', 'created_at', 'updated_at', 'deleted_at',
                        'deleted'])

IMAGE_ATTRS = BASE_MODEL_ATTRS | set(['name', 'type', 'status', 'size',
                                      'is_public', 'location'])
