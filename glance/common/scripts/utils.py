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
    'get_task',
    'unpack_task_input',
    'set_base_image_properties',
    'validate_location_uri',
    'get_image_data_iter',
]


import urllib2

from glance.common import exception
from glance import i18n
import glance.openstack.common.log as logging


LOG = logging.getLogger(__name__)
_ = i18n._
_LE = i18n._LE


def get_task(task_repo, task_id):
    """Gets a TaskProxy object.

    :param task_repo: TaskRepo object used to perform DB operations
    :param task_id: ID of the Task
    """
    task = None
    try:
        task = task_repo.get(task_id)
    except exception.NotFound:
        msg = _LE('Task not found for task_id %s') % task_id
        LOG.exception(msg)

    return task


def unpack_task_input(task):
    """Verifies and returns valid task input dictionary.

    :param task: Task domain object
    """
    task_input = task.task_input

    # NOTE: until we support multiple task types, we just check for
    # input fields related to 'import task'.
    for key in ["import_from", "import_from_format", "image_properties"]:
        if key not in task_input:
            msg = _("Input does not contain '%(key)s' field") % {"key": key}
            raise exception.Invalid(msg)

    return task_input


def set_base_image_properties(properties=None):
    """Sets optional base properties for creating Image.

    :param properties: Input dict to set some base properties
    """
    if properties is not None:
        # TODO(nikhil): We can make these properties configurable while
        # implementing the pipeline logic for the scripts. The below shown
        # are placeholders to show that the scripts work on 'devstack'
        # environment.
        properties['disk_format'] = 'qcow2'
        properties['container_format'] = 'ovf'


def validate_location_uri(location):
    """Validate location uri into acceptable format.

    :param location: Location uri to be validated
    """
    if not location:
        raise exception.BadStoreUri(_('Invalid location: %s') % location)

    elif location.startswith(('http://', 'https://')):
        return location

    # NOTE: file type uri is being avoided for security reasons,
    # see LP bug #942118 #1400966.
    elif location.startswith(("file:///", "filesystem:///")):
        msg = _("File based imports are not allowed. Please use a non-local "
                "source of image data.")
        # NOTE: raise Exception and let the encompassing block save
        # the error msg in the task.message.
        raise StandardError(msg)

    else:
        # TODO(nikhil): add other supported uris
        supported = ['http', ]
        msg = _("The given uri is not valid. Please specify a "
                "valid uri from the following list of supported uri "
                "%(supported)s") % {'supported': supported}
        raise urllib2.URLError(msg)


def get_image_data_iter(uri):
    """The scripts are expected to support only over non-local locations of
    data. Note the absence of file:// for security reasons, see LP bug #942118.
    If the above constraint is violated, task should fail.
    """
    # NOTE: Current script supports http location. Other locations
    # types are to be supported as the script evolve.
    return urllib2.urlopen(uri)
