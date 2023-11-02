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

"""
Cache driver that uses SQLite to store information about cached images
"""
from contextlib import contextmanager
import os
import sqlite3
import stat
import time

from oslo_concurrency import lockutils
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import excutils
from oslo_utils import fileutils

from glance.common import exception
from glance.i18n import _, _LI, _LW
from glance.image_cache.drivers import base
from glance.image_cache.drivers import common


LOG = logging.getLogger(__name__)

DEPRECATION_REASON = """
As centralized database will now be used for image cache management, the use
of `sqlite` database and driver will be dropped from 'E' (2025.1)
development cycle.
"""

sqlite_opts = [
    cfg.StrOpt('image_cache_sqlite_db', default='cache.db',
               deprecated_for_removal=True,
               deprecated_reason=DEPRECATION_REASON,
               deprecated_since='Caracal (2024.1)',
               help=_("""
The relative path to sqlite file database that will be used for image cache
management.

This is a relative path to the sqlite file database that tracks the age and
usage statistics of image cache. The path is relative to image cache base
directory, specified by the configuration option ``image_cache_dir``.

This is a lightweight database with just one table.

Possible values:
    * A valid relative path to sqlite file database

Related options:
    * ``image_cache_dir``

""")),
]

CONF = cfg.CONF
CONF.register_opts(sqlite_opts)


class Driver(base.Driver):

    """
    Cache driver that uses xattr file tags and requires a filesystem
    that has atimes set.
    """

    def configure(self):
        """
        Configure the driver to use the stored configuration options
        Any store that needs special configuration should implement
        this method. If the store was not able to successfully configure
        itself, it should raise `exception.BadDriverConfiguration`
        """
        LOG.warning(_(DEPRECATION_REASON))
        super(Driver, self).configure()

        # Create the SQLite database that will hold our cache attributes
        self.initialize_db()

    def initialize_db(self):
        db = CONF.image_cache_sqlite_db
        self.db_path = os.path.join(self.base_dir, db)
        lockutils.set_defaults(self.base_dir)

        @lockutils.synchronized('image_cache_db_init', external=True)
        def create_db():
            try:
                conn = sqlite3.connect(self.db_path, check_same_thread=False,
                                       factory=common.SqliteConnection)
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS cached_images (
                        image_id TEXT PRIMARY KEY,
                        last_accessed REAL DEFAULT 0.0,
                        last_modified REAL DEFAULT 0.0,
                        size INTEGER DEFAULT 0,
                        hits INTEGER DEFAULT 0,
                        checksum TEXT
                    );
                """)
                conn.close()
            except sqlite3.DatabaseError as e:
                msg = _("Failed to initialize the image cache database. "
                        "Got error: %s") % e
                LOG.error(msg)
                raise exception.BadDriverConfiguration(driver_name='sqlite',
                                                       reason=msg)

        create_db()

    def get_cache_size(self):
        """
        Returns the total size in bytes of the image cache.
        """
        sizes = []
        for path in self.get_cache_files(self.base_dir):
            if path == self.db_path:
                continue
            file_info = os.stat(path)
            sizes.append(file_info[stat.ST_SIZE])
        return sum(sizes)

    def get_hit_count(self, image_id):
        """
        Return the number of hits that an image has.

        :param image_id: Opaque image identifier
        """
        if not self.is_cached(image_id):
            return 0

        hits = 0
        with common.get_db(self.db_path) as db:
            cur = db.execute("""SELECT hits FROM cached_images
                             WHERE image_id = ?""",
                             (image_id,))
            hits = cur.fetchone()[0]
        return hits

    def get_cached_images(self):
        """
        Returns a list of records about cached images.
        """
        LOG.debug("Gathering cached image entries.")
        with common.get_db(self.db_path) as db:
            cur = db.execute("""SELECT
                             image_id, hits, last_accessed, last_modified, size
                             FROM cached_images
                             ORDER BY image_id""")
            cur.row_factory = common.dict_factory
            return [r for r in cur]

    def is_cached(self, image_id):
        """
        Returns True if the image with the supplied ID has its image
        file cached.

        :param image_id: Image ID
        """
        return os.path.exists(self.get_image_filepath(image_id))

    def is_cacheable(self, image_id):
        """
        Returns True if the image with the supplied ID can have its
        image file cached, False otherwise.

        :param image_id: Image ID
        """
        # Make sure we're not already cached or caching the image
        return not (self.is_cached(image_id) or
                    self.is_being_cached(image_id))

    def is_being_cached(self, image_id):
        """
        Returns True if the image with supplied id is currently
        in the process of having its image file cached.

        :param image_id: Image ID
        """
        path = self.get_image_filepath(image_id, 'incomplete')
        return os.path.exists(path)

    def is_queued(self, image_id):
        """
        Returns True if the image identifier is in our cache queue.

        :param image_id: Image ID
        """
        path = self.get_image_filepath(image_id, 'queue')
        return os.path.exists(path)

    def delete_all_cached_images(self):
        """
        Removes all cached image files and any attributes about the images
        """
        deleted = 0
        with common.get_db(self.db_path) as db:
            for path in self.get_cache_files(self.base_dir):
                delete_cached_file(path)
                deleted += 1
            db.execute("""DELETE FROM cached_images""")
            db.commit()
        return deleted

    def delete_cached_image(self, image_id):
        """
        Removes a specific cached image file and any attributes about the image

        :param image_id: Image ID
        """
        path = self.get_image_filepath(image_id)
        with common.get_db(self.db_path) as db:
            delete_cached_file(path)
            db.execute("""DELETE FROM cached_images WHERE image_id = ?""",
                       (image_id, ))
            db.commit()

    def delete_all_queued_images(self):
        """
        Removes all queued image files and any attributes about the images
        """
        files = [f for f in self.get_cache_files(self.queue_dir)]
        for file in files:
            fileutils.delete_if_exists(file)
        return len(files)

    def delete_queued_image(self, image_id):
        """
        Removes a specific queued image file and any attributes about the image

        :param image_id: Image ID
        """
        path = self.get_image_filepath(image_id, 'queue')
        fileutils.delete_if_exists(path)

    def clean(self, stall_time=None):
        """
        Delete any image files in the invalid directory and any
        files in the incomplete directory that are older than a
        configurable amount of time.
        """
        self.delete_invalid_files()

        if stall_time is None:
            stall_time = CONF.image_cache_stall_time

        now = time.time()
        older_than = now - stall_time
        self.delete_stalled_files(older_than)

    def get_least_recently_accessed(self):
        """
        Return a tuple containing the image_id and size of the least recently
        accessed cached file, or None if no cached files.
        """
        with common.get_db(self.db_path) as db:
            cur = db.execute("""SELECT image_id FROM cached_images
                             ORDER BY last_accessed LIMIT 1""")
            try:
                image_id = cur.fetchone()[0]
            except TypeError:
                # There are no more cached images
                return None

        path = self.get_image_filepath(image_id)
        try:
            file_info = os.stat(path)
            size = file_info[stat.ST_SIZE]
        except OSError:
            size = 0
        return image_id, size

    @contextmanager
    def open_for_write(self, image_id):
        """
        Open a file for writing the image file for an image
        with supplied identifier.

        :param image_id: Image ID
        """
        incomplete_path = self.get_image_filepath(image_id, 'incomplete')

        def commit():
            with common.get_db(self.db_path) as db:
                final_path = self.get_image_filepath(image_id)
                LOG.debug("Fetch finished, moving "
                          "'%(incomplete_path)s' to '%(final_path)s'",
                          dict(incomplete_path=incomplete_path,
                               final_path=final_path))
                os.rename(incomplete_path, final_path)

                # Make sure that we "pop" the image from the queue...
                if self.is_queued(image_id):
                    fileutils.delete_if_exists(
                        self.get_image_filepath(image_id, 'queue'))

                filesize = os.path.getsize(final_path)
                now = time.time()

                db.execute("""INSERT INTO cached_images
                           (image_id, last_accessed, last_modified, hits, size)
                           VALUES (?, ?, ?, 0, ?)""",
                           (image_id, now, now, filesize))
                db.commit()

        def rollback(e):
            with common.get_db(self.db_path) as db:
                if os.path.exists(incomplete_path):
                    invalid_path = self.get_image_filepath(image_id, 'invalid')

                    msg = (_LW("Fetch of cache file failed (%(e)s), rolling "
                               "back by moving '%(incomplete_path)s' to "
                               "'%(invalid_path)s'"),
                           {'e': e,
                            'incomplete_path': incomplete_path,
                            'invalid_path': invalid_path})
                    LOG.warning(msg)
                    os.rename(incomplete_path, invalid_path)

                db.execute("""DELETE FROM cached_images
                           WHERE image_id = ?""", (image_id, ))
                db.commit()

        try:
            with open(incomplete_path, 'wb') as cache_file:
                yield cache_file
        except Exception as e:
            with excutils.save_and_reraise_exception():
                rollback(e)
        else:
            commit()
        finally:
            # if the generator filling the cache file neither raises an
            # exception, nor completes fetching all data, neither rollback
            # nor commit will have been called, so the incomplete file
            # will persist - in that case remove it as it is unusable
            # example: ^c from client fetch
            if os.path.exists(incomplete_path):
                rollback('incomplete fetch')

    @contextmanager
    def open_for_read(self, image_id):
        """
        Open and yield file for reading the image file for an image
        with supplied identifier.

        :param image_id: Image ID
        """
        path = self.get_image_filepath(image_id)
        with open(path, 'rb') as cache_file:
            yield cache_file
        now = time.time()
        with common.get_db(self.db_path) as db:
            db.execute("""UPDATE cached_images
                       SET hits = hits + 1, last_accessed = ?
                       WHERE image_id = ?""",
                       (now, image_id))
            db.commit()

    def queue_image(self, image_id):
        """
        This adds a image to be cache to the queue.

        If the image already exists in the queue or has already been
        cached, we return False, True otherwise

        :param image_id: Image ID
        """
        if self.is_cached(image_id):
            LOG.info(_LI("Not queueing image '%s'. Already cached."), image_id)
            return False

        if self.is_being_cached(image_id):
            LOG.info(_LI("Not queueing image '%s'. Already being "
                         "written to cache"), image_id)
            return False

        if self.is_queued(image_id):
            LOG.info(_LI("Not queueing image '%s'. Already queued."), image_id)
            return False

        path = self.get_image_filepath(image_id, 'queue')

        # Touch the file to add it to the queue
        with open(path, "w"):
            pass

        return True

    def delete_invalid_files(self):
        """
        Removes any invalid cache entries
        """
        for path in self.get_cache_files(self.invalid_dir):
            fileutils.delete_if_exists(path)
            LOG.info(_LI("Removed invalid cache file %s"), path)

    def delete_stalled_files(self, older_than):
        """
        Removes any incomplete cache entries older than a
        supplied modified time.

        :param older_than: Files written to on or before this timestamp
                           will be deleted.
        """
        for path in self.get_cache_files(self.incomplete_dir):
            if os.path.getmtime(path) < older_than:
                try:
                    fileutils.delete_if_exists(path)
                    LOG.info(_LI("Removed stalled cache file %s"), path)
                except Exception as e:
                    msg = (_LW("Failed to delete file %(path)s. "
                               "Got error: %(e)s"),
                           dict(path=path, e=e))
                    LOG.warning(msg)

    def get_queued_images(self):
        """
        Returns a list of image IDs that are in the queue. The
        list should be sorted by the time the image ID was inserted
        into the queue.
        """
        files = [f for f in self.get_cache_files(self.queue_dir)]
        items = []
        for path in files:
            mtime = os.path.getmtime(path)
            items.append((mtime, os.path.basename(path)))

        items.sort()
        return [image_id for (modtime, image_id) in items]

    def get_cache_files(self, basepath):
        """
        Returns cache files in the supplied directory

        :param basepath: Directory to look in for cache files
        """
        for fname in os.listdir(basepath):
            path = os.path.join(basepath, fname)
            if path != self.db_path and os.path.isfile(path):
                yield path


def delete_cached_file(path):
    LOG.debug("Deleting image cache file '%s'", path)
    fileutils.delete_if_exists(path)
