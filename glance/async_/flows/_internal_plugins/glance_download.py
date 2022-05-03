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

import urllib.request

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import encodeutils
from oslo_utils import excutils
from taskflow.patterns import linear_flow as lf

from glance.async_.flows._internal_plugins import base_download
from glance.async_ import utils
from glance.common import exception
from glance.common import utils as common_utils
from glance.i18n import _, _LI, _LE

LOG = logging.getLogger(__name__)

CONF = cfg.CONF


class _DownloadGlanceImage(base_download.BaseDownload):

    def __init__(self, context, task_id, task_type, action_wrapper, stores,
                 glance_region, glance_image_id, glance_service_interface):
        self.context = context
        self.glance_region = glance_region
        self.glance_image_id = glance_image_id
        self.glance_service_interface = glance_service_interface
        super(_DownloadGlanceImage,
              self).__init__(task_id, task_type, action_wrapper, stores,
                             'GlanceDownload')

    def execute(self, image_size):
        """Create temp file into store and return path to it

        :param image_size: Glance Image Size retrieved from ImportMetadata task
        """
        try:
            glance_endpoint = utils.get_glance_endpoint(
                self.context,
                self.glance_region,
                self.glance_service_interface)
            image_download_url = '%s/v2/images/%s/file' % (
                glance_endpoint, self.glance_image_id)
            if not common_utils.validate_import_uri(image_download_url):
                LOG.debug("Processed URI for glance-download does not pass "
                          "filtering: %s", image_download_url)
                msg = (_("Processed URI for glance-download does not pass "
                         "filtering: %s") % image_download_url)
                raise exception.ImportTaskError(msg)
            LOG.info(_LI("Downloading glance image %s"), image_download_url)
            token = self.context.auth_token
            request = urllib.request.Request(image_download_url,
                                             headers={'X-Auth-Token': token})
            data = urllib.request.urlopen(request)
        except Exception as e:
            with excutils.save_and_reraise_exception():
                LOG.error(
                    _LE("Task %(task_id)s failed with exception %(error)s"), {
                        "error": encodeutils.exception_to_unicode(e),
                        "task_id": self.task_id
                    })

        self._path, bytes_written = self.store.add(self.image_id, data, 0)[0:2]
        if bytes_written != image_size:
            msg = (_("Task %(task_id)s failed because downloaded data "
                     "size %(data_size)i is different from expected %("
                     "expected)i") %
                   {"task_id": self.task_id, "data_size": bytes_written,
                    "expected": image_size})
            raise exception.ImportTaskError(msg)
        return self._path


def get_flow(**kwargs):
    """Return task flow for no-op.

    :param context: request context
    :param task_id: Task ID.
    :param task_type: Type of the task.
    :param image_repo: Image repository used.
    :param image_id: Image ID
    :param source_region: Source region name
    """
    context = kwargs.get('context')
    task_id = kwargs.get('task_id')
    task_type = kwargs.get('task_type')
    action_wrapper = kwargs.get('action_wrapper')
    stores = kwargs.get('backend', [None])
    # glance-download parameters
    import_req = kwargs.get('import_req')
    method = import_req.get('method')
    glance_region = method.get('glance_region')
    glance_image_id = method.get('glance_image_id')
    glance_service_interface = method.get('glance_service_interface')

    return lf.Flow(task_type).add(
        _DownloadGlanceImage(context, task_id, task_type, action_wrapper,
                             stores, glance_region, glance_image_id,
                             glance_service_interface),
    )
