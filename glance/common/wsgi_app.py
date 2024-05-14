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

import atexit
import os
import threading

import glance_store
from oslo_config import cfg
from oslo_log import log as logging
import osprofiler.initializer

from glance.api import common
import glance.async_
from glance.common import config
from glance.common import store_utils
from glance import housekeeping
from glance.i18n import _, _LW
from glance import notifier
from glance import sqlite_migration

CONF = cfg.CONF
CONF.import_group("profiler", "glance.common.wsgi")
CONF.import_opt("enabled_backends", "glance.common.wsgi")
logging.register_options(CONF)
LOG = logging.getLogger(__name__)

# Detect if we're running under the uwsgi server
try:
    import uwsgi
    LOG.debug('Detected running under uwsgi')
except ImportError:
    LOG.debug('Detected not running under uwsgi')
    uwsgi = None

CONFIG_FILES = ['glance-image-import.conf',
                'glance-api.conf']

# Reserved file stores for staging and tasks operations
RESERVED_STORES = {
    'os_glance_staging_store': 'file',
    'os_glance_tasks_store': 'file'
}


def _get_config_files(env=None):
    if env is None:
        env = os.environ
    dirname = env.get('OS_GLANCE_CONFIG_DIR', '/etc/glance').strip()
    config_files = []
    for config_file in CONFIG_FILES:
        cfg_file = os.path.join(dirname, config_file)
        # As 'glance-image-import.conf' is optional conf file
        # so include it only if it's existing.
        if config_file == 'glance-image-import.conf' and (
                not os.path.exists(cfg_file)):
            continue
        config_files.append(cfg_file)

    return config_files


def _setup_os_profiler():
    notifier.set_defaults()
    if CONF.profiler.enabled:
        osprofiler.initializer.init_from_conf(conf=CONF,
                                              context={},
                                              project='glance',
                                              service='api',
                                              host=CONF.bind_host)


def drain_workers():
    # NOTE(danms): If there are any other named pools that we need to
    # drain before exit, they should be in this list.
    pools_to_drain = ['tasks_pool']
    for pool_name in pools_to_drain:
        pool_model = common.get_thread_pool(pool_name)
        LOG.info('Waiting for remaining threads in pool %r', pool_name)
        pool_model.pool.shutdown()

    from glance.api.v2 import cached_images  # noqa
    if cached_images.WORKER:
        # If we started a cache worker, signal it to exit
        # and wait until it does.
        cached_images.WORKER.terminate()


def run_staging_cleanup():
    cleaner = housekeeping.StagingStoreCleaner(glance.db.get_api())
    # NOTE(danms): Start thread as a daemon. It is still a
    # single-shot, but this will not block our shutdown if it is
    # running.
    cleanup_thread = threading.Thread(
        target=cleaner.clean_orphaned_staging_residue,
        daemon=True)
    cleanup_thread.start()


def init_app():
    config.set_config_defaults()
    config_files = _get_config_files()
    CONF([], project='glance', default_config_files=config_files)
    logging.setup(CONF, "glance")

    # NOTE(danms): We are running inside uwsgi or mod_wsgi, so no eventlet;
    # use native threading instead.
    glance.async_.set_threadpool_model('native')
    if uwsgi:
        uwsgi.atexit = drain_workers
    else:
        atexit.register(drain_workers)

    # NOTE(danms): Change the default threadpool size since we
    # are dealing with native threads and not greenthreads.
    # Right now, the only pool of default size is tasks_pool,
    # so if others are created this will need to change to be
    # more specific.
    common.DEFAULT_POOL_SIZE = CONF.wsgi.task_pool_threads

    if CONF.enabled_backends:
        if store_utils.check_reserved_stores(CONF.enabled_backends):
            msg = _("'os_glance_' prefix should not be used in "
                    "enabled_backends config option. It is reserved "
                    "for internal use only.")
            raise RuntimeError(msg)
        glance_store.register_store_opts(CONF, reserved_stores=RESERVED_STORES)
        glance_store.create_multi_stores(CONF, reserved_stores=RESERVED_STORES)
        glance_store.verify_store()
    else:
        glance_store.register_opts(CONF)
        glance_store.create_stores(CONF)
        glance_store.verify_default_store()

    # NOTE(abhishekk): This will raise RuntimeError if
    # worker_self_reference_url is not set in glance-api.conf
    sqlite_migration.migrate_if_required()

    # NOTE(danms): This may raise GlanceException if the staging store is
    # not configured properly, which will bubble up to the WSGI server,
    # aborting application load as desired.
    staging = housekeeping.staging_store_path()
    if not os.path.exists(staging) and CONF.enabled_import_methods:
        LOG.warning(_LW('Import methods are enabled but staging directory '
                        '%(path)s does not exist; Imports will fail!'),
                    {'path': staging})

    run_staging_cleanup()

    _setup_os_profiler()
    return config.load_paste_app('glance-api')
