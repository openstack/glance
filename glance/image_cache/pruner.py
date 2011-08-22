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
Prunes the Image Cache
"""
import logging
import os
import stat
import time

from glance.common import config
from glance.image_cache import ImageCache

logger = logging.getLogger('glance.image_cache.pruner')


class Pruner(object):
    def __init__(self, options):
        self.options = options
        self.cache = ImageCache(options)

    @property
    def max_size(self):
        default = 1 * 1024 * 1024 * 1024  # 1 GB
        return config.get_option(
            self.options, 'image_cache_max_size_bytes',
            type='int', default=default)

    @property
    def percent_extra_to_free(self):
        return config.get_option(
            self.options, 'image_cache_percent_extra_to_free',
            type='float', default=0.05)

    def run(self):
        self.prune_cache()

    def prune_cache(self):
        """Prune the cache using an LRU strategy"""

        # NOTE(sirp): 'Recency' is determined via the filesystem, first using
        # atime (access time) and falling back to mtime (modified time).
        #
        # It has become more common to disable access-time updates by setting
        # the `noatime` option for the filesystem. `noatime` is NOT compatible
        # with this method.
        #
        # If `noatime` needs to be supported, we will need to persist access
        # times elsewhere (either as a separate file, in the DB, or as
        # an xattr).
        def get_stats():
            stats = []
            for path in self.cache.get_all_regular_files(self.cache.path):
                file_info = os.stat(path)
                stats.append((file_info[stat.ST_ATIME],  # access time
                              file_info[stat.ST_MTIME],  # modification time
                              file_info[stat.ST_SIZE],   # size in bytes
                              path))                     # absolute path
            return stats

        def prune_lru(stats, to_free):
            # Sort older access and modified times to the back
            stats.sort(reverse=True)

            freed = 0
            while to_free > 0:
                atime, mtime, size, path = stats.pop()
                logger.debug(_("deleting '%(path)s' to free %(size)d B"),
                             locals())
                os.unlink(path)
                to_free -= size
                freed += size

            return freed

        stats = get_stats()

        # Check for overage
        cur_size = sum(s[2] for s in stats)
        max_size = self.max_size
        logger.debug(_("cur_size=%(cur_size)d B max_size=%(max_size)d B"),
                     locals())
        if cur_size <= max_size:
            logger.debug(_("cache has free space, skipping prune..."))
            return

        overage = cur_size - max_size
        extra = max_size * self.percent_extra_to_free
        to_free = overage + extra
        logger.debug(_("overage=%(overage)d B extra=%(extra)d B"
                     " total=%(to_free)d B"), locals())

        freed = prune_lru(stats, to_free)
        logger.debug(_("finished pruning, freed %(freed)d bytes"), locals())


def app_factory(global_config, **local_conf):
    conf = global_config.copy()
    conf.update(local_conf)
    return Pruner(conf)
