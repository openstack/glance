# Copyright 2018 Red Hat, Inc.
# Copyright 2022 OVHCloud
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

import abc

import glance_store as store_api
from glance_store import backend
from oslo_config import cfg
from oslo_log import log as logging
from taskflow import task

from glance.common import exception
from glance.i18n import _, _LE

LOG = logging.getLogger(__name__)

CONF = cfg.CONF


class BaseDownload(task.Task, metaclass=abc.ABCMeta):

    default_provides = 'file_uri'

    def __init__(self, task_id, task_type, action_wrapper, stores,
                 plugin_name):
        self.task_id = task_id
        self.task_type = task_type
        self.image_id = action_wrapper.image_id
        self.action_wrapper = action_wrapper
        self.stores = stores
        self._path = None
        self.plugin_name = plugin_name or 'Download'
        super(BaseDownload, self).__init__(
            name='%s-%s-%s' % (task_type, self.plugin_name, task_id))

        # NOTE(abhishekk): Use reserved 'os_glance_staging_store' for
        # staging the data, the else part will be removed once old way
        # of configuring store is deprecated.
        if CONF.enabled_backends:
            self.store = store_api.get_store_from_store_identifier(
                'os_glance_staging_store')
        else:
            if CONF.node_staging_uri is None:
                msg = (_("%(task_id)s of %(task_type)s not configured "
                         "properly. Missing node_staging_uri: %(work_dir)s") %
                       {'task_id': self.task_id,
                        'task_type': self.task_type,
                        'work_dir': CONF.node_staging_uri})
                raise exception.BadTaskConfiguration(msg)

            self.store = self._build_store()

    def _build_store(self):
        # NOTE(flaper87): Due to the nice glance_store api (#sarcasm), we're
        # forced to build our own config object, register the required options
        # (and by required I mean *ALL* of them, even the ones we don't want),
        # and create our own store instance by calling a private function.
        # This is certainly unfortunate but it's the best we can do until the
        # glance_store refactor is done. A good thing is that glance_store is
        # under our team's management and it gates on Glance so changes to
        # this API will (should?) break task's tests.
        # TODO(abhishekk): After removal of backend module from glance_store
        # need to change this to use multi_backend module.
        conf = cfg.ConfigOpts()
        try:
            backend.register_opts(conf)
        except cfg.DuplicateOptError:
            pass

        conf.set_override('filesystem_store_datadir',
                          CONF.node_staging_uri[7:],
                          group='glance_store')

        # NOTE(flaper87): Do not even try to judge me for this... :(
        # With the glance_store refactor, this code will change, until
        # that happens, we don't have a better option and this is the
        # least worst one, IMHO.
        store = store_api.backend._load_store(conf, 'file')

        if store is None:
            msg = (_("%(task_id)s of %(task_type)s not configured "
                     "properly. Could not load the filesystem store") %
                   {'task_id': self.task_id, 'task_type': self.task_type})
            raise exception.BadTaskConfiguration(msg)

        store.configure()
        return store

    def revert(self, result, **kwargs):
        LOG.error(_LE('Task: %(task_id)s failed to import image '
                      '%(image_id)s to the filesystem.'),
                  {'task_id': self.task_id,
                   'image_id': self.image_id})
        # NOTE(abhishekk): Revert image state back to 'queued' as
        # something went wrong.
        # NOTE(danms): If we failed to stage the image, then none
        # of the _ImportToStore() tasks could have run, so we need
        # to move all stores out of "importing" and into "failed".
        with self.action_wrapper as action:
            action.set_image_attribute(status='queued')
            action.remove_importing_stores(self.stores)
            action.add_failed_stores(self.stores)

        # NOTE(abhishekk): Deleting partial image data from staging area
        if self._path is not None:
            LOG.debug(('Deleting image %(image_id)s from staging '
                       'area.'), {'image_id': self.image_id})
            try:
                if CONF.enabled_backends:
                    store_api.delete(self._path, None)
                else:
                    store_api.delete_from_backend(self._path)
            except Exception:
                LOG.exception(_LE("Error reverting web/glance download "
                                  "task: %(task_id)s"), {
                    'task_id': self.task_id})
