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

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import encodeutils
from oslo_utils import excutils
from six.moves import urllib
from stevedore import driver
from taskflow import engines
from taskflow.listeners import logging as llistener

import glance.async_
from glance.common import exception
from glance.common.scripts import utils as script_utils
from glance.i18n import _, _LE

LOG = logging.getLogger(__name__)

_deprecated_opt = cfg.DeprecatedOpt('eventlet_executor_pool_size',
                                    group='task')

taskflow_executor_opts = [
    cfg.StrOpt('engine_mode',
               default='parallel',
               choices=('serial', 'parallel'),
               help=_("""
Set the taskflow engine mode.

Provide a string type value to set the mode in which the taskflow
engine would schedule tasks to the workers on the hosts. Based on
this mode, the engine executes tasks either in single or multiple
threads. The possible values for this configuration option are:
``serial`` and ``parallel``. When set to ``serial``, the engine runs
all the tasks in a single thread which results in serial execution
of tasks. Setting this to ``parallel`` makes the engine run tasks in
multiple threads. This results in parallel execution of tasks.

Possible values:
    * serial
    * parallel

Related options:
    * max_workers

""")),

    cfg.IntOpt('max_workers',
               default=10,
               min=1,
               help=_("""
Set the number of engine executable tasks.

Provide an integer value to limit the number of workers that can be
instantiated on the hosts. In other words, this number defines the
number of parallel tasks that can be executed at the same time by
the taskflow engine. This value can be greater than one when the
engine mode is set to parallel.

Possible values:
    * Integer value greater than or equal to 1

Related options:
    * engine_mode

"""),
               deprecated_opts=[_deprecated_opt])
]


CONF = cfg.CONF
CONF.register_opts(taskflow_executor_opts, group='taskflow_executor')


class TaskExecutor(glance.async_.TaskExecutor):

    def __init__(self, context, task_repo, image_repo, image_factory,
                 admin_repo=None):
        self.context = context
        self.task_repo = task_repo
        self.image_repo = image_repo
        self.image_factory = image_factory
        self.admin_repo = admin_repo
        super(TaskExecutor, self).__init__(context, task_repo, image_repo,
                                           image_factory,
                                           admin_repo=admin_repo)

    @staticmethod
    def _fetch_an_executor():
        if CONF.taskflow_executor.engine_mode != 'parallel':
            return None
        else:
            max_workers = CONF.taskflow_executor.max_workers
            threadpool_cls = glance.async_.get_threadpool_model()
            return threadpool_cls(max_workers).pool

    def _get_flow(self, task):
        try:
            task_input = script_utils.unpack_task_input(task)

            kwds = {
                'task_id': task.task_id,
                'task_type': task.type,
                'context': self.context,
                'task_repo': self.task_repo,
                'image_repo': self.image_repo,
                'image_factory': self.image_factory,
                'backend': task_input.get('backend')
            }

            if self.admin_repo:
                kwds['admin_repo'] = self.admin_repo

            if task.type == "import":
                uri = script_utils.validate_location_uri(
                    task_input.get('import_from'))
                kwds['uri'] = uri
            if task.type == 'api_image_import':
                kwds['image_id'] = task_input['image_id']
                kwds['import_req'] = task_input['import_req']
            return driver.DriverManager('glance.flows', task.type,
                                        invoke_on_load=True,
                                        invoke_kwds=kwds).driver
        except urllib.error.URLError as exc:
            raise exception.ImportTaskError(message=exc.reason)
        except (exception.BadStoreUri, exception.Invalid) as exc:
            raise exception.ImportTaskError(message=exc.msg)
        except RuntimeError:
            raise NotImplementedError()

    def begin_processing(self, task_id):
        try:
            super(TaskExecutor, self).begin_processing(task_id)
        except exception.ImportTaskError as exc:
            LOG.error(_LE('Failed to execute task %(task_id)s: %(exc)s') %
                      {'task_id': task_id, 'exc': exc.msg})
            task = self.task_repo.get(task_id)
            task.fail(exc.msg)
            self.task_repo.save(task)

    def _run(self, task_id, task_type):
        LOG.debug('Taskflow executor picked up the execution of task ID '
                  '%(task_id)s of task type '
                  '%(task_type)s', {'task_id': task_id,
                                    'task_type': task_type})

        task = script_utils.get_task(self.task_repo, task_id)
        if task is None:
            # NOTE: This happens if task is not found in the database. In
            # such cases, there is no way to update the task status so,
            # it's ignored here.
            return

        flow = self._get_flow(task)
        executor = self._fetch_an_executor()
        try:
            engine = engines.load(
                flow,
                engine=CONF.taskflow_executor.engine_mode, executor=executor,
                max_workers=CONF.taskflow_executor.max_workers)
            with llistener.DynamicLoggingListener(engine, log=LOG):
                engine.run()
        except exception.UploadException as exc:
            task.fail(encodeutils.exception_to_unicode(exc))
            self.task_repo.save(task)
        except Exception as exc:
            with excutils.save_and_reraise_exception():
                LOG.error(_LE('Failed to execute task %(task_id)s: %(exc)s') %
                          {'task_id': task_id,
                           'exc': encodeutils.exception_to_unicode(exc)})
                # TODO(sabari): Check for specific exceptions and update the
                # task failure message.
                task.fail(_('Task failed due to Internal Error'))
                self.task_repo.save(task)
        finally:
            if executor is not None:
                executor.shutdown()
