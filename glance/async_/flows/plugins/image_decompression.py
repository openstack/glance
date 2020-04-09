# Copyright 2020 Red Hat, Inc.
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

import gzip
import os
import shutil
import zipfile

from oslo_log import log as logging
from oslo_utils import encodeutils
from taskflow.patterns import linear_flow as lf
from taskflow import task

LOG = logging.getLogger(__name__)

# Note(jokke): The number before '_' is offset for the magic number in header
MAGIC_NUMBERS = {
    '0_zipfile': bytes([0x50, 0x4B, 0x03, 0x04]),
    '2_lhafile': bytes([0x2D, 0x6C, 0x68]),
    '0_gzipfile': bytes([0x1F, 0x8B, 0x08])}

NO_LHA = False

try:
    import lhafile
except ImportError:
    LOG.debug("No lhafile available.")
    NO_LHA = True


def header_lengths():
    headers = []
    for key, val in MAGIC_NUMBERS.items():
        offset, key = key.split("_")
        headers.append(int(offset) + len(val))
    return headers


MAX_HEADER = max(header_lengths())


def _zipfile(src_path, dest_path, image_id):
    try:
        with zipfile.ZipFile(src_path, 'r') as zfd:
            content = zfd.namelist()
            if len(content) != 1:
                raise Exception("Archive contains more than one file.")
            else:
                zfd.extract(content[0], dest_path)
    except Exception as e:
        LOG.debug("ZIP: Error decompressing image %(iid)s: %(msg)s", {
                  "iid": image_id,
                  "msg": encodeutils.exception_to_unicode(e)})
        raise


def _lhafile(src_path, dest_path, image_id):
    if NO_LHA:
        raise Exception("No lhafile available.")
    try:
        with lhafile.LhaFile(src_path, 'r') as lfd:
            content = lfd.namelist()
            if len(content) != 1:
                raise Exception("Archive contains more than one file.")
            else:
                lfd.extract(content[0], dest_path)
    except Exception as e:
        LOG.debug("LHA: Error decompressing image %(iid)s: %(msg)s", {
                  "iid": image_id,
                  "msg": encodeutils.exception_to_unicode(e)})
        raise


def _gzipfile(src_path, dest_path, image_id):
    try:
        with gzip.open(src_path, 'r') as gzfd:
            with open(dest_path, 'wb') as fd:
                shutil.copyfileobj(gzfd, fd)
    except gzip.BadGzipFile as e:
        LOG.debug("ZIP: Error decompressing image %(iid)s: Bad GZip file: "
                  "%(msg)s", {"iid": image_id,
                              "msg": encodeutils.exception_to_unicode(e)})
        raise
    except Exception as e:
        LOG.debug("GZIP: Error decompressing image %(iid)s: %(msg)s", {
                  "iid": image_id,
                  "msg": encodeutils.exception_to_unicode(e)})
        raise


class _DecompressImage(task.Task):

    default_provides = 'file_path'

    def __init__(self, context, task_id, task_type,
                 image_repo, image_id):
        self.context = context
        self.task_id = task_id
        self.task_type = task_type
        self.image_repo = image_repo
        self.image_id = image_id
        self.dest_path = ""
        super(_DecompressImage, self).__init__(
            name='%s-Decompress_Image-%s' % (task_type, task_id))

    def execute(self, file_path, **kwargs):

        # TODO(jokke): Once we support other schemas we need to take them into
        # account and handle the paths here.
        src_path = file_path.split('file://')[-1]
        self.dest_path = "%(path)s.uc" % {'path': src_path}
        image = self.image_repo.get(self.image_id)
        # NOTE(jokke): If the container format is 'compressed' the image is
        # expected to be compressed so lets not decompress it.
        if image.container_format == 'compressed':
            return "file://%s" % src_path
        head = None
        with open(src_path, 'rb') as fd:
            head = fd.read(MAX_HEADER)
        for key, val in MAGIC_NUMBERS.items():
            offset, key = key.split("_")
            offset = int(offset)
            key = "_" + key
            if head.startswith(val, offset):
                globals()[key](src_path, self.dest_path, self.image_id)
                os.replace(self.dest_path, src_path)

        return "file://%s" % src_path

    def revert(self, result=None, **kwargs):
        # NOTE(flaper87, jokke): If result is None, it probably
        # means this task failed. Otherwise, we would have
        # a result from its execution. This includes the case
        # that nothing was to be compressed.
        if result is not None:
            LOG.debug("Image decompression failed.")
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
        _DecompressImage(context, task_id, task_type,
                         image_repo, image_id),
    )
