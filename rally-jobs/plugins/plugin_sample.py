# Copyright 2014 Mirantis Inc.
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

""" Sample of plugin for Glance.

For more Glance related benchmarks take a look here:
github.com/openstack/rally/tree/master/samples/tasks/scenarios/glance

About plugins: https://rally.readthedocs.org/en/latest/plugins.html

Rally concepts https://wiki.openstack.org/wiki/Rally/Concepts
"""

import os

from rally.plugins.openstack import scenario
from rally.task import atomic
from rally.task import utils


class GlancePlugin(scenario.OpenStackScenario):

    @atomic.action_timer("glance.create_image_label")
    def _create_image(self, image_name, container_format,
                      image_location, disk_format, **kwargs):
        """Create a new image.

        :param image_name: String used to name the image
        :param container_format: Container format of image.
        Acceptable formats: ami, ari, aki, bare, and ovf.
        :param image_location: image file location used to upload
        :param disk_format: Disk format of image. Acceptable formats:
        ami, ari, aki, vhd, vmdk, raw, qcow2, vdi, and iso.
        :param **kwargs:  optional parameters to create image

        returns: object of image
        """

        kw = {
            "name": image_name,
            "container_format": container_format,
            "disk_format": disk_format,
        }

        kw.update(kwargs)

        try:
            if os.path.isfile(os.path.expanduser(image_location)):
                kw["data"] = open(os.path.expanduser(image_location))
            else:
                kw["copy_from"] = image_location

            image = self.clients("glance").images.create(**kw)
            image = utils.wait_for(image,
                                   is_ready=utils.resource_is("active"),
                                   update_resource=utils.get_from_manager(),
                                   timeout=100,
                                   check_interval=0.5)
        finally:
            if "data" in kw:
                kw["data"].close()

        return image

    @atomic.action_timer("glance.list_images_label")
    def _list_images(self):
        return list(self.clients("glance").images.list())

    @scenario.configure(context={"cleanup": ["glance"]})
    def create_and_list(self, container_format,
                        image_location, disk_format, **kwargs):
        self._create_image(self._generate_random_name(),
                           container_format,
                           image_location,
                           disk_format,
                           **kwargs)
        self._list_images()
