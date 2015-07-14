# Copyright 2015 OpenStack Foundation
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

import contextlib

import futurist
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import excutils
from stevedore import driver
from taskflow import engines
from taskflow.listeners import logging as llistener

import glance.async
from glance.common.scripts import utils as script_utils
from glance import i18n

_ = i18n._
_LE = i18n._LE
LOG = logging.getLogger(__name__)

_deprecated_opt = cfg.DeprecatedOpt('eventlet_executor_pool_size',
                                    group='task')

taskflow_executor_opts = [
    cfg.StrOpt('engine_mode',
               default='parallel',
               choices=('serial', 'parallel'),
               help=_("The mode in which the engine will run. "
                      "Can be 'serial' or 'parallel'.")),
    cfg.IntOpt('max_workers',
               default=10,
               help=_("The number of parallel activities executed at the "
                      "same time by the engine. The value can be greater "
                      "than one when the engine mode is 'parallel'."),
               deprecated_opts=[_deprecated_opt])
]


CONF = cfg.CONF
CONF.register_opts(taskflow_executor_opts, group='taskflow_executor')


class TaskExecutor(glance.async.TaskExecutor):

    def __init__(self, context, task_repo, image_repo, image_factory):
        self.context = context
        self.task_repo = task_repo
        self.image_repo = image_repo
        self.image_factory = image_factory
        self.engine_conf = {
            'engine': CONF.taskflow_executor.engine_mode,
        }
        self.engine_kwargs = {}
        if CONF.taskflow_executor.engine_mode == 'parallel':
            self.engine_kwargs['max_workers'] = (
                CONF.taskflow_executor.max_workers)
        super(TaskExecutor, self).__init__(context, task_repo, image_repo,
                                           image_factory)

    @contextlib.contextmanager
    def _executor(self):
        if CONF.taskflow_executor.engine_mode != 'parallel':
            yield None
        else:
            max_workers = CONF.taskflow_executor.max_workers
            try:
                yield futurist.GreenThreadPoolExecutor(max_workers=max_workers)
            except RuntimeError:
                yield futurist.ThreadPoolExecutor(max_workers=max_workers)

    def _get_flow(self, task):
        try:
            task_input = script_utils.unpack_task_input(task)
            uri = script_utils.validate_location_uri(
                task_input.get('import_from'))

            kwds = {
                'uri': uri,
                'task_id': task.task_id,
                'task_type': task.type,
                'context': self.context,
                'task_repo': self.task_repo,
                'image_repo': self.image_repo,
                'image_factory': self.image_factory
            }

            return driver.DriverManager('glance.flows', task.type,
                                        invoke_on_load=True,
                                        invoke_kwds=kwds).driver
        except RuntimeError:
            raise NotImplementedError()

    def _run(self, task_id, task_type):
        LOG.debug('Taskflow executor picked up the execution of task ID '
                  '%(task_id)s of task type '
                  '%(task_type)s' % {'task_id': task_id,
                                     'task_type': task_type})

        task = script_utils.get_task(self.task_repo, task_id)
        if task is None:
            # NOTE: This happens if task is not found in the database. In
            # such cases, there is no way to update the task status so,
            # it's ignored here.
            return

        flow = self._get_flow(task)

        try:
            with self._executor() as executor:
                engine = engines.load(flow, self.engine_conf,
                                      executor=executor, **self.engine_kwargs)
                with llistener.DynamicLoggingListener(engine, log=LOG):
                    engine.run()
        except Exception as exc:
            with excutils.save_and_reraise_exception():
                LOG.error(_LE('Failed to execute task %(task_id)s: %(exc)s') %
                          {'task_id': task_id, 'exc': exc.message})
                # TODO(sabari): Check for specific exceptions and update the
                # task failure message.
                task.fail(_('Task failed due to Internal Error'))
                self.task_repo.save(task)
