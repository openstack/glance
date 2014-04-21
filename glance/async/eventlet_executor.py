# Copyright 2014 OpenStack Foundation
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

import eventlet
from oslo.config import cfg

import glance.async
import glance.common.scripts as scripts
from glance import i18n
from glance.openstack.common import lockutils
import glance.openstack.common.log as logging


_LI = i18n._LI
LOG = logging.getLogger(__name__)
CONF = cfg.CONF
CONF.import_opt('eventlet_executor_pool_size', 'glance.common.config',
                group='task')

_MAX_EXECUTOR_THREADS = CONF.task.eventlet_executor_pool_size
_THREAD_POOL = None


class TaskExecutor(glance.async.TaskExecutor):
    def __init__(self, context, task_repo, image_repo, image_factory):
        super(TaskExecutor, self).__init__(context, task_repo, image_repo,
                                           image_factory)
        if _THREAD_POOL is None:
            self._set_gobal_threadpool_if_none()

    @lockutils.synchronized("tasks_eventlet_pool")
    def _set_gobal_threadpool_if_none(self):
        global _THREAD_POOL
        if _THREAD_POOL is None:
            _THREAD_POOL = eventlet.GreenPool(size=_MAX_EXECUTOR_THREADS)

    def _run(self, task_id, task_type):
        LOG.info(_LI('Eventlet executor picked up the execution of task ID '
                     '%(task_id)s of task type '
                     '%(task_type)s') % {'task_id': task_id,
                                         'task_type': task_type})

        _THREAD_POOL.spawn_n(scripts.run_task,
                             task_id,
                             task_type,
                             self.context,
                             self.task_repo,
                             self.image_repo,
                             self.image_factory)
