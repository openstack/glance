# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
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
Cleans up any invalid cache entries
"""

import logging

from glance.image_cache import ImageCache

logger = logging.getLogger(__name__)


class Cleaner(object):
    def __init__(self, options):
        self.options = options
        self.cache = ImageCache(options)

    def run(self):
        self.cache.clean()


def app_factory(global_config, **local_conf):
    conf = global_config.copy()
    conf.update(local_conf)
    return Cleaner(conf)
