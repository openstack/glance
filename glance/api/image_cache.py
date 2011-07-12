from contextlib import contextmanager
import logging
import os
import stat
import types

from glance.common import config
from glance import utils

logger = logging.getLogger('glance.api.image_cache')


class ImageCache(object):
    def __init__(self, options):
        self.options = options
        self._make_cache_directory_if_needed()

    def _make_cache_directory_if_needed(self):
        if self.enabled and not os.path.exists(self.path):
            logger.info("image cache directory doesn't exist, creating '%s'",
                        self.path)
            os.makedirs(self.path)

    @property
    def enabled(self):
        return config.get_option(
            self.options, 'image_cache_enabled', type='bool', default=False)

    @property
    def max_size(self):
        default = 1 * 1024 * 1024 * 1024 # 1 GB
        return config.get_option(
            self.options, 'image_cache_max_size_bytes',
            type='int', default=default)

    @property
    def path(self):
        """This is the base path for the image cache"""
        datadir = self.options['image_cache_datadir']
        return datadir

    def path_for_image(self, image_meta):
        """This crafts an absolute path to a specific entry"""
        image_id = image_meta['id']
        return os.path.join(self.path, str(image_id))

    @contextmanager
    def open(self, image_meta, mode="r"):
        path = self.path_for_image(image_meta)
        with open(path, mode) as cache_file:
            yield cache_file

    def hit(self, image_meta):
        path = self.path_for_image(image_meta)
        return os.path.exists(path)

    def delete(self, image_meta):
        path = self.path_for_image(image_meta)
        logger.debug("deleting image cache entry '%s'", path)
        if os.path.exists(path):
            os.unlink(path)

    @property
    def percent_extra_to_free(self):
        return config.get_option(
            self.options, 'image_cache_percent_extra_to_free',
            type='float', default=0.05)

    def prune(self):
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
            for fname in os.listdir(self.path):
                path = os.path.join(self.path, fname)
                file_info = os.stat(path)
                mode = file_info[stat.ST_MODE]
                if not stat.S_ISREG(mode):
                    continue
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
                logger.debug("deleting '%(path)s' to free %(size)d B"
                             % locals())
                os.unlink(path)
                to_free -= size
                freed += size

            return freed

        stats = get_stats()

        # Check for overage
        cur_size = sum(s[2] for s in stats)
        max_size = self.max_size
        logger.debug("cur_size=%(cur_size)d B max_size=%(max_size)d B"
                     % locals())
        if cur_size <= max_size:
            logger.debug("cache has free space, skipping prune...")
            return

        overage = cur_size - max_size
        extra = max_size * self.percent_extra_to_free
        to_free = overage + extra
        logger.debug("overage=%(overage)d B extra=%(extra)d B"
                     " total=%(to_free)d B" % locals())

        freed = prune_lru(stats, to_free)
        logger.debug("finished pruning, freed %(freed)d bytes" % locals())
