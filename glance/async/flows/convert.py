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

import logging
import os

from oslo_concurrency import processutils as putils
from oslo_config import cfg
from taskflow.patterns import linear_flow as lf
from taskflow import task

from glance import i18n

_ = i18n._
_LI = i18n._LI
_LE = i18n._LE
_LW = i18n._LW
LOG = logging.getLogger(__name__)

convert_task_opts = [
    cfg.StrOpt('conversion_format',
               default=None,
               choices=('qcow2', 'raw', 'vmdk'),
               help=_("The format to which images will be automatically "
                      "converted.")),
]

CONF = cfg.CONF

# NOTE(flaper87): Registering under the taskflow_executor section
# for now. It seems a waste to have a whole section dedicated to a
# single task with a single option.
CONF.register_opts(convert_task_opts, group='taskflow_executor')


class _Convert(task.Task):

    conversion_missing_warned = False

    def __init__(self, task_id, task_type, image_repo):
        self.task_id = task_id
        self.task_type = task_type
        self.image_repo = image_repo
        super(_Convert, self).__init__(
            name='%s-Convert-%s' % (task_type, task_id))

    def execute(self, image_id, file_path):

        # NOTE(flaper87): A format must be explicitly
        # specified. There's no "sane" default for this
        # because the dest format may work differently depending
        # on the environment OpenStack is running in.
        conversion_format = CONF.taskflow_executor.conversion_format
        if conversion_format is None:
            if not _Convert.conversion_missing_warned:
                msg = (_LW('The conversion format is None, please add a value '
                           'for it in the config file for this task to '
                           'work: %s') %
                       self.task_id)
                LOG.warn(msg)
                _Convert.conversion_missing_warned = True
            return

        # TODO(flaper87): Check whether the image is in the desired
        # format already. Probably using `qemu-img` just like the
        # `Introspection` task.
        dest_path = os.path.join(CONF.task.work_dir, "%s.converted" % image_id)
        stdout, stderr = putils.trycmd('qemu-img', 'convert', '-O',
                                       conversion_format, file_path, dest_path,
                                       log_errors=putils.LOG_ALL_ERRORS)

        if stderr:
            raise RuntimeError(stderr)

        os.rename(dest_path, file_path.split("file://")[-1])
        return file_path

    def revert(self, image_id, result=None, **kwargs):
        # NOTE(flaper87): If result is None, it probably
        # means this task failed. Otherwise, we would have
        # a result from its execution.
        if result is None:
            return

        fs_path = result.split("file://")[-1]
        if os.path.exists(fs_path):
            os.path.remove(fs_path)


def get_flow(**kwargs):
    """Return task flow for converting images to different formats.

    :param task_id: Task ID.
    :param task_type: Type of the task.
    :param image_repo: Image repository used.
    """
    task_id = kwargs.get('task_id')
    task_type = kwargs.get('task_type')
    image_repo = kwargs.get('image_repo')

    return lf.Flow(task_type).add(
        _Convert(task_id, task_type, image_repo),
    )
