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
from glance.common import format_inspector
from glance.i18n import _, _LI

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

    def __init__(self, context, task_id, task_type, action_wrapper):
        self.context = context
        self.task_id = task_id
        self.task_type = task_type
        self.action_wrapper = action_wrapper
        self.image_id = action_wrapper.image_id
        self.dest_path = ""
        self.python = CONF.wsgi.python_interpreter
        super(_ConvertImage, self).__init__(
            name='%s-Convert_Image-%s' % (task_type, task_id))

    def execute(self, file_path, **kwargs):
        with self.action_wrapper as action:
            return self._execute(action, file_path, **kwargs)

    def _execute(self, action, file_path, **kwargs):

        target_format = CONF.image_conversion.output_format
        # TODO(jokke): Once we support other schemas we need to take them into
        # account and handle the paths here.
        src_path = file_path.split('file://')[-1]
        dest_path = "%(path)s.%(target)s" % {'path': src_path,
                                             'target': target_format}
        self.dest_path = dest_path

        source_format = action.image_disk_format
        inspector_cls = format_inspector.get_inspector(source_format)
        if not inspector_cls:
            # We cannot convert from disk_format types that qemu-img doesn't
            # support (like iso, ploop, etc). The ones it supports overlaps
            # with the ones we have inspectors for, so reject conversion for
            # any format we don't have an inspector for.
            raise RuntimeError(
                'Unable to convert from format %s' % source_format)

        # Use our own cautious inspector module (if we have one for this
        # format) to make sure a file is the format the submitter claimed
        # it is and that it passes some basic safety checks _before_ we run
        # qemu-img on it.
        # See https://bugs.launchpad.net/nova/+bug/2059809 for details.
        try:
            inspector = inspector_cls.from_file(src_path)
            if not inspector.safety_check():
                LOG.error('Image failed %s safety check; aborting conversion',
                          source_format)
                raise RuntimeError('Image has disallowed configuration')
        except RuntimeError:
            raise
        except format_inspector.ImageFormatError as e:
            LOG.error('Image claimed to be %s format failed format '
                      'inspection: %s', source_format, e)
            raise RuntimeError('Image format detection failed')
        except Exception as e:
            LOG.exception('Unknown error inspecting image format: %s', e)
            raise RuntimeError('Unable to inspect image')

        try:
            stdout, stderr = putils.trycmd("qemu-img", "info",
                                           "-f", source_format,
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
        if metadata.get('format') != source_format:
            LOG.error('Image claiming to be %s reported as %s by qemu-img',
                      source_format, metadata.get('format', 'unknown'))
            raise RuntimeError('Image metadata disagrees about format')

        virtual_size = metadata.get('virtual-size', 0)
        action.set_image_attribute(virtual_size=virtual_size)

        if 'backing-filename' in metadata:
            LOG.warning('Refusing to process QCOW image with a backing file')
            raise RuntimeError(
                'QCOW images with backing files are not allowed')

        try:
            data_file = metadata['format-specific']['data']['data-file']
        except KeyError:
            data_file = None
        if data_file is not None:
            raise RuntimeError(
                'QCOW images with data-file set are not allowed')

        if metadata.get('format') == 'vmdk':
            create_type = metadata.get(
                'format-specific', {}).get(
                    'data', {}).get('create-type')
            allowed = CONF.image_format.vmdk_allowed_types
            if not create_type:
                raise RuntimeError(_('Unable to determine VMDK create-type'))
            if not len(allowed):
                LOG.warning(_('Refusing to process VMDK file as '
                              'vmdk_allowed_types is empty'))
                raise RuntimeError(_('Image is a VMDK, but no VMDK createType '
                                     'is specified'))
            if create_type not in allowed:
                LOG.warning(_('Refusing to process VMDK file with create-type '
                              'of %r which is not in allowed set of: %s'),
                            create_type, ','.join(allowed))
                raise RuntimeError(_('Invalid VMDK create-type specified'))

        if source_format == target_format:
            LOG.debug("Source is already in target format, "
                      "not doing conversion for %s", self.image_id)
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

        action.set_image_attribute(disk_format=target_format,
                                   container_format='bare')
        new_size = os.stat(dest_path).st_size
        action.set_image_attribute(size=new_size)
        LOG.info(_LI('Updated image %s size=%i disk_format=%s'),
                 self.image_id, new_size, target_format)

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
    :param action_wrapper: An api_image_import.ActionWrapper.
    """
    context = kwargs.get('context')
    task_id = kwargs.get('task_id')
    task_type = kwargs.get('task_type')
    action_wrapper = kwargs.get('action_wrapper')

    return lf.Flow(task_type).add(
        _ConvertImage(context, task_id, task_type, action_wrapper)
    )
