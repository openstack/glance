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

from oslo_log import log as logging

from glance import i18n


LOG = logging.getLogger(__name__)
_LE = i18n._LE


class TaskExecutor(object):
    """Base class for Asynchronous task executors. It does not support the
    execution mechanism.

    Provisions the extensible classes with necessary variables to utilize
    important Glance modules like, context, task_repo, image_repo,
    image_factory.

    Note:
        It also gives abstraction for the standard pre-processing and
        post-processing operations to be executed by a task. These may include
        validation checks, security checks, introspection, error handling etc.
        The aim is to give developers an abstract sense of the execution
        pipeline logic.

    Args:
        context: glance.context.RequestContext object for AuthZ and AuthN
            checks
        task_repo: glance.db.TaskRepo object which acts as a translator for
            glance.domain.Task and glance.domain.TaskStub objects
            into ORM semantics
        image_repo: glance.db.ImageRepo object which acts as a translator for
            glance.domain.Image object into ORM semantics
        image_factory: glance.domain.ImageFactory object to be used for
            creating new images for certain types of tasks viz. import, cloning
    """

    def __init__(self, context, task_repo, image_repo, image_factory):
        self.context = context
        self.task_repo = task_repo
        self.image_repo = image_repo
        self.image_factory = image_factory

    def begin_processing(self, task_id):
        task = self.task_repo.get(task_id)
        task.begin_processing()
        self.task_repo.save(task)

        # start running
        self._run(task_id, task.type)

    def _run(self, task_id, task_type):
        task = self.task_repo.get(task_id)
        msg = _LE("This execution of Tasks is not setup. Please consult the "
                  "project documentation for more information on the "
                  "executors available.")
        LOG.error(msg)
        task.fail(_LE("Internal error occurred while trying to process task."))
        self.task_repo.save(task)
