# Copyright 2017 Red Hat, Inc.
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
from taskflow.patterns import linear_flow as lf
from taskflow import task

LOG = logging.getLogger(__name__)

CONF = cfg.CONF


class _Noop(task.Task):

    def __init__(self, task_id, task_type, image_repo):
        self.task_id = task_id
        self.task_type = task_type
        self.image_repo = image_repo
        super(_Noop, self).__init__(
            name='%s-Noop-%s' % (task_type, task_id))

    def execute(self, **kwargs):

        LOG.debug("No_op import plugin")
        return

    def revert(self, result=None, **kwargs):
        # NOTE(flaper87): If result is None, it probably
        # means this task failed. Otherwise, we would have
        # a result from its execution.
        if result is not None:
            LOG.debug("No_op import plugin failed")
            return


def get_flow(**kwargs):
    """Return task flow for no-op.

    :param task_id: Task ID.
    :param task_type: Type of the task.
    :param image_repo: Image repository used.
    """
    task_id = kwargs.get('task_id')
    task_type = kwargs.get('task_type')
    image_repo = kwargs.get('image_repo')

    return lf.Flow(task_type).add(
        _Noop(task_id, task_type, image_repo),
    )
