# Copyright 2018 Red Hat, Inc.
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

import json
import os

from oslo_concurrency import processutils as putils
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import encodeutils
from oslo_utils import excutils
from taskflow.patterns import linear_flow as lf
from taskflow import task

from glance.async_ import utils
from glance.i18n import _

LOG = logging.getLogger(__name__)

conversion_plugin_opts = [
    cfg.StrOpt('output_format',
               default='raw',
               choices=('qcow2', 'raw', 'vmdk'),
               help=_("""
Desired output format for image conversion plugin.

Provide a valid image format to which the conversion plugin
will convert the image before storing it to the back-end.

Note, if the Image Conversion plugin for image import is defined, users
should only upload disk formats that are supported by `quemu-img` otherwise
the conversion and import will fail.

Possible values:
    * qcow2
    * raw
    * vmdk

Related Options:
    * disk_formats
""")),
]

CONF = cfg.CONF

CONF.register_opts(conversion_plugin_opts, group='image_conversion')


class _ConvertImage(task.Task):

    default_provides = 'file_path'

    def __init__(self, context, task_id, task_type,
                 image_repo, image_id):
        self.context = context
        self.task_id = task_id
        self.task_type = task_type
        self.image_repo = image_repo
        self.image_id = image_id
        self.dest_path = ""
        self.python = CONF.wsgi.python_interpreter
        super(_ConvertImage, self).__init__(
            name='%s-Convert_Image-%s' % (task_type, task_id))

    def execute(self, file_path, **kwargs):

        target_format = CONF.image_conversion.output_format
        # TODO(jokke): Once we support other schemas we need to take them into
        # account and handle the paths here.
        src_path = file_path.split('file://')[-1]
        dest_path = "%(path)s.%(target)s" % {'path': src_path,
                                             'target': target_format}
        self.dest_path = dest_path

        try:
            stdout, stderr = putils.trycmd("qemu-img", "info",
                                           "--output=json",
                                           src_path,
                                           prlimit=utils.QEMU_IMG_PROC_LIMITS,
                                           python_exec=self.python,
                                           log_errors=putils.LOG_ALL_ERRORS,)
        except OSError as exc:
            with excutils.save_and_reraise_exception():
                exc_message = encodeutils.exception_to_unicode(exc)
                msg = ("Failed to do introspection as part of image "
                       "conversion for %(iid)s: %(err)s")
                LOG.error(msg, {'iid': self.image_id, 'err': exc_message})

        if stderr:
            raise RuntimeError(stderr)

        metadata = json.loads(stdout)
        source_format = metadata.get('format')
        virtual_size = metadata.get('virtual-size', 0)
        image = self.image_repo.get(self.image_id)
        image.virtual_size = virtual_size

        if source_format == target_format:
            LOG.debug("Source is already in target format, "
                      "not doing conversion for %s", self.image_id)
            self.image_repo.save(image)
            return file_path

        try:
            stdout, stderr = putils.trycmd('qemu-img', 'convert',
                                           '-f', source_format,
                                           '-O', target_format,
                                           src_path, dest_path,
                                           log_errors=putils.LOG_ALL_ERRORS)
        except OSError as exc:
            with excutils.save_and_reraise_exception():
                exc_message = encodeutils.exception_to_unicode(exc)
                msg = "Failed to do image conversion for %(iid)s: %(err)s"
                LOG.error(msg, {'iid': self.image_id, 'err': exc_message})

        if stderr:
            raise RuntimeError(stderr)

        image.disk_format = target_format
        image.container_format = 'bare'
        self.image_repo.save(image)

        os.remove(src_path)

        return "file://%s" % dest_path

    def revert(self, result=None, **kwargs):
        # NOTE(flaper87): If result is None, it probably
        # means this task failed. Otherwise, we would have
        # a result from its execution.
        if result is not None:
            LOG.debug("Image conversion failed.")
            if os.path.exists(self.dest_path):
                os.remove(self.dest_path)


def get_flow(**kwargs):
    """Return task flow for no-op.

    :param context: request context
    :param task_id: Task ID.
    :param task_type: Type of the task.
    :param image_repo: Image repository used.
    :param image_id: Image ID
    """
    context = kwargs.get('context')
    task_id = kwargs.get('task_id')
    task_type = kwargs.get('task_type')
    image_repo = kwargs.get('image_repo')
    image_id = kwargs.get('image_id')

    return lf.Flow(task_type).add(
        _ConvertImage(context, task_id, task_type,
                      image_repo, image_id),
    )
