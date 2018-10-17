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

__all__ = [
    'run',
]

from oslo_concurrency import lockutils
from oslo_log import log as logging
from oslo_utils import encodeutils
from oslo_utils import excutils
import six

from glance.api.v2 import images as v2_api
from glance.common import exception
from glance.common.scripts import utils as script_utils
from glance.common import store_utils
from glance.i18n import _

LOG = logging.getLogger(__name__)


def run(t_id, context, task_repo, image_repo, image_factory):
    LOG.info('Task %(task_id)s beginning image import '
             'execution.', {'task_id': t_id})
    _execute(t_id, task_repo, image_repo, image_factory)


# NOTE(nikhil): This lock prevents more than N number of threads to be spawn
# simultaneously. The number N represents the number of threads in the
# executor pool. The value is set to 10 in the eventlet executor.
@lockutils.synchronized("glance_image_import")
def _execute(t_id, task_repo, image_repo, image_factory):
    task = script_utils.get_task(task_repo, t_id)

    if task is None:
        # NOTE: This happens if task is not found in the database. In
        # such cases, there is no way to update the task status so,
        # it's ignored here.
        return

    try:
        task_input = script_utils.unpack_task_input(task)

        image_id = task_input.get('image_id')

        task.succeed({'image_id': image_id})
    except Exception as e:
        # Note: The message string contains Error in it to indicate
        # in the task.message that it's a error message for the user.

        # TODO(nikhil): need to bring back save_and_reraise_exception when
        # necessary
        err_msg = ("Error: " + six.text_type(type(e)) + ': ' +
                   encodeutils.exception_to_unicode(e))
        log_msg = err_msg + ("Task ID %s" % task.task_id)
        LOG.exception(log_msg)

        task.fail(_(err_msg))  # noqa
    finally:
        task_repo.save(task)


def import_image(image_repo, image_factory, task_input, task_id, uri):
    original_image = v2_api.create_image(image_repo,
                                         image_factory,
                                         task_input.get('image_properties'),
                                         task_id)
    # NOTE: set image status to saving just before setting data
    original_image.status = 'saving'
    image_repo.save(original_image)
    image_id = original_image.image_id

    # NOTE: Retrieving image from the database because the Image object
    # returned from create_image method does not have appropriate factories
    # wrapped around it.
    new_image = image_repo.get(image_id)
    set_image_data(new_image, uri, task_id)

    try:
        # NOTE: Check if the Image is not deleted after setting the data
        # before saving the active image. Here if image status is
        # saving, then new_image is saved as it contains updated location,
        # size, virtual_size and checksum information and the status of
        # new_image is already set to active in set_image_data() call.
        image = image_repo.get(image_id)
        if image.status == 'saving':
            image_repo.save(new_image)
            return image_id
        else:
            msg = _("The Image %(image_id)s object being created by this task "
                    "%(task_id)s, is no longer in valid status for further "
                    "processing.") % {"image_id": image_id,
                                      "task_id": task_id}
            raise exception.Conflict(msg)
    except (exception.Conflict, exception.NotFound,
            exception.NotAuthenticated):
        with excutils.save_and_reraise_exception():
            if new_image.locations:
                for location in new_image.locations:
                    store_utils.delete_image_location_from_backend(
                        new_image.context,
                        image_id,
                        location)


def set_image_data(image, uri, task_id, backend=None):
    data_iter = None
    try:
        LOG.info("Task %(task_id)s: Got image data uri %(data_uri)s to be "
                 "imported", {"data_uri": uri, "task_id": task_id})
        data_iter = script_utils.get_image_data_iter(uri)
        image.set_data(data_iter, backend=backend)
    except Exception as e:
        with excutils.save_and_reraise_exception():
            LOG.warn("Task %(task_id)s failed with exception %(error)s" %
                     {"error": encodeutils.exception_to_unicode(e),
                      "task_id": task_id})
            LOG.info("Task %(task_id)s: Could not import image file"
                     " %(image_data)s", {"image_data": uri,
                                         "task_id": task_id})
    finally:
        if hasattr(data_iter, 'close'):
            data_iter.close()
