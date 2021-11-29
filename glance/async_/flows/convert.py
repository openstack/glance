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

import os

from oslo_concurrency import processutils as putils
from oslo_config import cfg
from oslo_log import log as logging
from taskflow.patterns import linear_flow as lf
from taskflow import task

from glance.i18n import _, _LW

LOG = logging.getLogger(__name__)

convert_task_opts = [
    # NOTE: This configuration option requires the operator to explicitly set
    # an image conversion format. There being no sane default due to the
    # dependency on the environment in which OpenStack is running, we do not
    # mark this configuration option as "required". Rather a warning message
    # is given to the operator, prompting for an image conversion format to
    # be set.
    cfg.StrOpt('conversion_format',
               sample_default='raw',
               choices=('qcow2', 'raw', 'vmdk'),
               help=_("""
Set the desired image conversion format.

Provide a valid image format to which you want images to be
converted before they are stored for consumption by Glance.
Appropriate image format conversions are desirable for specific
storage backends in order to facilitate efficient handling of
bandwidth and usage of the storage infrastructure.

By default, ``conversion_format`` is not set and must be set
explicitly in the configuration file.

The allowed values for this option are ``raw``, ``qcow2`` and
``vmdk``. The  ``raw`` format is the unstructured disk format and
should be chosen when RBD or Ceph storage backends are used for
image storage. ``qcow2`` is supported by the QEMU emulator that
expands dynamically and supports Copy on Write. The ``vmdk`` is
another common disk format supported by many common virtual machine
monitors like VMWare Workstation.

Possible values:
    * qcow2
    * raw
    * vmdk

Related options:
    * disk_formats

""")),
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
        abs_file_path = file_path.split("file://")[-1]
        conversion_format = CONF.taskflow_executor.conversion_format
        if conversion_format is None:
            if not _Convert.conversion_missing_warned:
                msg = _LW('The conversion format is None, please add a value '
                          'for it in the config file for this task to '
                          'work: %s')
                LOG.warning(msg, self.task_id)
                _Convert.conversion_missing_warned = True
            return

        image_obj = self.image_repo.get(image_id)
        src_format = image_obj.disk_format

        # TODO(flaper87): Check whether the image is in the desired
        # format already. Probably using `qemu-img` just like the
        # `Introspection` task.

        # NOTE(hemanthm): We add '-f' parameter to the convert command here so
        # that the image format need not be inferred by qemu utils. This
        # shields us from being vulnerable to an attack vector described here
        # https://bugs.launchpad.net/glance/+bug/1449062

        data_dir = CONF.task.work_dir
        # NOTE(abhishekk): Use reserved 'os_glance_tasks_store' for tasks.
        if CONF.enabled_backends:
            data_dir = getattr(
                CONF, 'os_glance_tasks_store').filesystem_store_datadir

        dest_path = os.path.join(data_dir, "%s.converted" % image_id)
        stdout, stderr = putils.trycmd('qemu-img', 'convert',
                                       '-f', src_format,
                                       '-O', conversion_format,
                                       file_path, dest_path,
                                       log_errors=putils.LOG_ALL_ERRORS)

        if stderr:
            raise RuntimeError(stderr)

        os.unlink(abs_file_path)
        os.rename(dest_path, abs_file_path)
        return file_path

    def revert(self, image_id, result=None, **kwargs):
        # NOTE(flaper87): If result is None, it probably
        # means this task failed. Otherwise, we would have
        # a result from its execution.
        if result is None:
            return

        fs_path = result.split("file://")[-1]
        if os.path.exists(fs_path):
            os.remove(fs_path)


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
