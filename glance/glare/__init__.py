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

import six

from glance.common import exception


class Showlevel(object):
    # None - do not show additional properties and blobs with locations;
    # Basic - show all artifact fields except dependencies;
    # Direct - show all artifact fields with only direct dependencies;
    # Transitive - show all artifact fields with all of dependencies.
    NONE = 0
    BASIC = 1
    DIRECT = 2
    TRANSITIVE = 3

    _level_map = {'none': NONE, 'basic': BASIC, 'direct': DIRECT,
                  'transitive': TRANSITIVE}
    _inverted_level_map = {v: k for k, v in six.iteritems(_level_map)}

    @staticmethod
    def to_str(n):
        try:
            return Showlevel._inverted_level_map[n]
        except KeyError:
            raise exception.ArtifactUnsupportedShowLevel()

    @staticmethod
    def from_str(str_value):
        try:
            return Showlevel._level_map[str_value]
        except KeyError:
            raise exception.ArtifactUnsupportedShowLevel()
