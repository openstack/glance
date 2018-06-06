# Copyright 2018 NTT DATA, Inc.
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
from taskflow.patterns import linear_flow as lf
from taskflow import task

from glance.i18n import _


CONF = cfg.CONF


inject_metadata_opts = [

    cfg.ListOpt('ignore_user_roles',
                default='admin',
                help=_("""
Specify name of user roles to be ignored for injecting metadata
properties in the image.

Possible values:
    * List containing user roles. For example: [admin,member]

""")),
    cfg.DictOpt('inject',
                default={},
                help=_("""
Dictionary contains metadata properties to be injected in image.

Possible values:
    * Dictionary containing key/value pairs. Key characters
    length should be <= 255. For example: k1:v1,k2:v2


""")),
]

CONF.register_opts(inject_metadata_opts, group='inject_metadata_properties')


class _InjectMetadataProperties(task.Task):

    def __init__(self, context, task_id, task_type, image_repo, image_id):
        self.context = context
        self.task_id = task_id
        self.task_type = task_type
        self.image_repo = image_repo
        self.image_id = image_id
        super(_InjectMetadataProperties, self).__init__(
            name='%s-InjectMetadataProperties-%s' % (task_type, task_id))

    def execute(self):
        """Inject custom metadata properties to image

        :param image_id: Glance Image ID
        """
        user_roles = self.context.roles
        ignore_user_roles = CONF.inject_metadata_properties.ignore_user_roles

        if not [role for role in user_roles if role in ignore_user_roles]:
            properties = CONF.inject_metadata_properties.inject

            if properties:
                image = self.image_repo.get(self.image_id)
                image.extra_properties.update(properties)
                self.image_repo.save(image)


def get_flow(**kwargs):
    """Return task flow for inject_image_metadata.

    :param task_id: Task ID.
    :param task_type: Type of the task.
    :param image_repo: Image repository used.
    :param image_id: Image_ID used.
    :param context: Context used.
    """
    task_id = kwargs.get('task_id')
    task_type = kwargs.get('task_type')
    image_repo = kwargs.get('image_repo')
    image_id = kwargs.get('image_id')
    context = kwargs.get('context')

    return lf.Flow(task_type).add(
        _InjectMetadataProperties(context, task_id, task_type, image_repo,
                                  image_id),
    )
