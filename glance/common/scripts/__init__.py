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

from oslo_log import log as logging

from glance.common.scripts.api_image_import import main as api_image_import
from glance.common.scripts.image_import import main as image_import
from glance.i18n import _LE, _LI


LOG = logging.getLogger(__name__)


def run_task(task_id, task_type, context,
             task_repo=None, image_repo=None, image_factory=None):
    # TODO(nikhil): if task_repo is None get new task repo
    # TODO(nikhil): if image_repo is None get new image repo
    # TODO(nikhil): if image_factory is None get new image factory
    LOG.info(_LI("Loading known task scripts for task_id %(task_id)s "
                 "of type %(task_type)s"), {'task_id': task_id,
                                            'task_type': task_type})
    if task_type == 'import':
        image_import.run(task_id, context, task_repo,
                         image_repo, image_factory)

    elif task_type == 'api_image_import':
        api_image_import.run(task_id,
                             context,
                             task_repo,
                             image_repo,
                             image_factory)

    else:
        msg = _LE("This task type %(task_type)s is not supported by the "
                  "current deployment of Glance. Please refer the "
                  "documentation provided by OpenStack or your operator "
                  "for more information.") % {'task_type': task_type}
        LOG.error(msg)
        task = task_repo.get(task_id)
        task.fail(msg)
        if task_repo:
            task_repo.save(task)
        else:
            LOG.error(_LE("Failed to save task %(task_id)s in DB as task_repo "
                          "is %(task_repo)s"), {"task_id": task_id,
                                                "task_repo": task_repo})
