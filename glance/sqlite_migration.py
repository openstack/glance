# Copyright 2024 Red Hat, Inc.
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

import datetime
import os

from oslo_concurrency import lockutils
from oslo_config import cfg
from oslo_log import log as logging

from glance.common import exception
from glance import context
import glance.db
from glance.i18n import _
from glance.image_cache.drivers import common


LOG = logging.getLogger(__name__)
CONF = cfg.CONF
CONF.import_opt("image_cache_sqlite_db", "glance.image_cache.drivers.sqlite")


def can_migrate_to_central_db():
    # Return immediately if cache is disabled
    if not (CONF.paste_deploy.flavor and 'cache' in CONF.paste_deploy.flavor):
        return False

    is_centralized_db_driver = CONF.image_cache_driver == "centralized_db"
    # Check worker_self_reference_url is set if cache is enabled and
    # cache driver is centralized_db
    if is_centralized_db_driver and not CONF.worker_self_reference_url:
        msg = _("'worker_self_reference_url' needs to be set "
                "if `centralized_db` is defined as cache driver "
                "for image_cache_driver config option.")
        raise RuntimeError(msg)

    return is_centralized_db_driver


def migrate_if_required():
    if can_migrate_to_central_db():
        sqlite_db_file = get_db_path()
        if sqlite_db_file:
            LOG.info("Initiating migration process from SQLite to Centralized "
                     "database")
            migrate = Migrate(sqlite_db_file, glance.db.get_api())
            migrate.migrate()


def get_db_path():
    """Return the local path to sqlite database."""
    db = CONF.image_cache_sqlite_db
    base_dir = CONF.image_cache_dir
    db_file = os.path.join(base_dir, db)
    if not os.path.exists(db_file):
        LOG.debug('SQLite caching database not located, skipping migration')
        return

    return db_file


class Migrate:
    def __init__(self, db, db_api):
        self.db = db
        self.db_api = db_api
        self.context = context.get_admin_context()
        self.node_reference = CONF.worker_self_reference_url

    @lockutils.synchronized('sqlite_centralized_migrate', external=True)
    def migrate(self):
        LOG.debug("Adding local node reference %(node)s in centralized db",
                  {'node': self.node_reference})
        to_be_deleted = []
        try:
            self.db_api.node_reference_create(
                self.context, self.node_reference)
        except exception.Duplicate:
            LOG.debug("Node reference %(node)s is already recorded, "
                      "ignoring it", {'node': self.node_reference})

        LOG.debug("Connecting to SQLite db %s", self.db)
        with common.get_db(self.db) as sqlite_db:
            cur = sqlite_db.execute("""SELECT
                             image_id, hits, last_accessed, last_modified, size
                             FROM cached_images
                             ORDER BY image_id""")
            cur.row_factory = common.dict_factory
            for r in cur:
                # NOTE(abhishekk): Check if cache record is already present for
                # current node in centralized db
                if not self.db_api.is_image_cached_for_node(
                        self.context, self.node_reference, r['image_id']):
                    LOG.debug("Migrating image %s from SQLite to Centralized "
                              "db.", r['image_id'])
                    # NOTE(abhishekk): Converting dates to be compatible with
                    # centralized db
                    last_accessed = datetime.datetime.utcfromtimestamp(
                        r['last_accessed']).isoformat()
                    last_modified = datetime.datetime.utcfromtimestamp(
                        r['last_modified']).isoformat()
                    # insert into centralized database
                    self.db_api.insert_cache_details(
                        self.context, self.node_reference, r['image_id'],
                        r['size'], hits=r['hits'], last_modified=last_modified,
                        last_accessed=last_accessed)

                    # Verify entry is made in centralized db before adding
                    # image id to list to delete later from sqlite db
                    if self.db_api.is_image_cached_for_node(
                            self.context, self.node_reference, r['image_id']):
                        LOG.debug("Image %(uuid)s is migrated to centralized "
                                  "db for node %(node)s",
                                  {'uuid': r['image_id'],
                                   'node': self.node_reference})
                        to_be_deleted.append(r['image_id'])
                else:
                    LOG.debug('Skipping migrating image %(uuid)s from SQLite '
                              'to Centralized db for node %(node)s as it is '
                              'present in Centralized db.',
                              {'uuid': r['image_id'],
                               'node': self.node_reference})

            # Delete the images from sqlite db which are migrated to
            # centralized db
            for image_id in to_be_deleted:
                LOG.debug("Deleting image %s from SQLite db", image_id)
                sqlite_db.execute("""DELETE FROM cached_images
                                  WHERE image_id = ?""", (image_id,))
                sqlite_db.commit()

        if to_be_deleted:
            LOG.debug("Migrated %d records from SQLite db to Centralized "
                      "db", len(to_be_deleted))
        else:
            # NOTE(abhishekk): Safe to assume, no records present in SQLite db
            LOG.debug("No cache records found, skipping migration process.")
