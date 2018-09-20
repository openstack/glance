# Copyright 2018 Red Hat, Inc.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


import glance.async_.flows.plugins.image_conversion
import glance.async_.flows.plugins.inject_image_metadata


# Note(jokke): This list contains tuples of config options for import plugins.
# When new plugin is introduced its config options need to be added to this
# list so that they can be processed, when config generator is used to generate
# the glance-image-import.conf.sample it will also pick up the details. The
# module needs to be imported as the Glance release packaged example(s) above
# and the first part of the tuple refers to the group the options gets
# registered under at the config file.
PLUGIN_OPTS = [
    ('inject_metadata_properties',
     glance.async_.flows.plugins.inject_image_metadata.inject_metadata_opts),
    ('image_conversion',
     glance.async_.flows.plugins.image_conversion.conversion_plugin_opts),
]


def get_plugin_opts():
    return PLUGIN_OPTS
