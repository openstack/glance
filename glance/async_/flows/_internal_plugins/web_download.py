# Copyright 2018 Red Hat, Inc.
# Copyright 2022 OVHCloud
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
from taskflow.patterns import linear_flow as lf

from glance.async_.flows._internal_plugins import base_download
from glance.common import exception
from glance.common.scripts import utils as script_utils
from glance.i18n import _

LOG = logging.getLogger(__name__)

CONF = cfg.CONF


class _WebDownload(base_download.BaseDownload):

    def __init__(self, task_id, task_type, uri, action_wrapper, stores):
        self.uri = uri
        super(_WebDownload, self).__init__(task_id, task_type, action_wrapper,
                                           stores, 'WebDownload')

    def execute(self):
        """Create temp file into store and return path to it

        """
        # NOTE(jokke): We've decided to use staging area for this task as
        # a way to expect users to configure a local store for pre-import
        # works on the image to happen.
        #
        # While using any path should be "technically" fine, it's not what
        # we recommend as the best solution. For more details on this, please
        # refer to the comment in the `_ImportToStore.execute` method.
        try:
            data = script_utils.get_image_data_iter(self.uri)
        except Exception as e:
            with excutils.save_and_reraise_exception():
                LOG.error("Task %(task_id)s failed with exception %(error)s",
                          {"error": encodeutils.exception_to_unicode(e),
                           "task_id": self.task_id})

        self._path, bytes_written = self.store.add(self.image_id, data, 0)[0:2]
        try:
            content_length = int(data.headers['content-length'])
            if bytes_written != content_length:
                msg = (_("Task %(task_id)s failed because downloaded data "
                         "size %(data_size)i is different from expected %("
                         "expected)i") %
                       {"task_id": self.task_id, "data_size": bytes_written,
                        "expected": content_length})
                raise exception.ImportTaskError(msg)
        except (KeyError, ValueError):
            pass
        return self._path


def get_flow(**kwargs):
    """Return task flow for web-download.

    :param task_id: Task ID.
    :param task_type: Type of the task.
    :param image_repo: Image repository used.
    :param uri: URI the image data is downloaded from.
    :param action_wrapper: An api_image_import.ActionWrapper.
    """
    task_id = kwargs.get('task_id')
    task_type = kwargs.get('task_type')
    uri = kwargs.get('import_req')['method'].get('uri')
    action_wrapper = kwargs.get('action_wrapper')
    stores = kwargs.get('backend', [None])

    return lf.Flow(task_type).add(
        _WebDownload(task_id, task_type, uri, action_wrapper, stores),
    )
