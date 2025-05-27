# Copyright 2025 RedHat Inc.
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
import time

from oslo_concurrency import lockutils
from oslo_config import cfg
from oslo_log import log as logging

from glance.common import exception


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


def get_data_dir():
    """Return the filesystem store data directory from config."""
    if CONF.enabled_backends:
        return CONF.os_glance_tasks_store.filesystem_store_datadir
    else:
        # NOTE(abhishekk): strip the 'file://' prefix from the URI
        return CONF.node_staging_uri[7:]


def path_for_op(operation_id, prefix='running-task-'):
    """Construct the file path for a given operation ID."""
    return os.path.join(get_data_dir(), "%s%s" % (prefix, operation_id))


def is_canceled(operation_id):
    """
    Check if the operation has been canceled (file exists and
    is nonzero length).
    """
    operation_path = path_for_op(operation_id)
    return os.path.exists(operation_path) and os.path.getsize(
        operation_path) > 0


def register_operation(operation_id):
    """Register a new operation by creating a lock file."""
    with lockutils.external_lock('tasks'):
        operation_path = path_for_op(operation_id)
        try:
            # Use os.open with O_CREAT | O_EXCL to ensure atomic creation
            fd = os.open(operation_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
        except FileExistsError:
            # Handle the case where the lock file already exists
            raise RuntimeError(f"Operation {operation_id} is "
                               f"already registered.")


def cancel_operation(operation_id):
    """
    Mark an operation as canceled by writing to the lock file if it exists.
    """
    with lockutils.external_lock('tasks'):
        operation_path = path_for_op(operation_id)
        if not os.path.exists(operation_path):
            raise exception.ServerError(
                "Operation file for %s does not exist, cannot cancel.",
                operation_id)
        with open(operation_path, 'w') as f:
            f.write(str(operation_id))

    # Wait for the system to acknowledge the cancellation
    for _ in range(60):
        if os.path.exists(operation_path):
            time.sleep(0.5)
            continue
        return

    # If still not canceled after timeout, raise an exception
    raise exception.ServerError("Timeout canceling in-progress "
                                "task %s" % operation_id)


def signal_finished(operation_id):
    """Remove the lock file to signal that the operation is canceled."""
    with lockutils.external_lock('tasks'):
        operation_path = path_for_op(operation_id)
        try:
            os.remove(operation_path)
        except FileNotFoundError:
            LOG.warning("Attempted to signal finished for operation %s, "
                        "but the operation file does not "
                        "exist.", operation_path)
