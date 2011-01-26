# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack LLC.
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

"""
Registry API
"""

from glance.common import flags
from glance.registry import client

FLAGS = flags.FLAGS

# TODO(jaypipes): Separate server flags from client flags
#                 and allow a list of client host/port
#                 combinations
flags.DEFINE_string('registry_host', '0.0.0.0',
                    'Registry server lives at this address')
flags.DEFINE_integer('registry_port', 9191,
                     'Registry server listens on this port')


def get_images_list():
    c = client.RegistryClient(FLAGS.registry_host, FLAGS.registry_port)
    return c.get_images()


def get_images_detail():
    c = client.RegistryClient(FLAGS.registry_host, FLAGS.registry_port)
    return c.get_images_detailed()


def get_image_metadata(image_id):
    c = client.RegistryClient(FLAGS.registry_host, FLAGS.registry_port)
    return c.get_image(image_id)


def add_image_metadata(image_data):
    c = client.RegistryClient(FLAGS.registry_host, FLAGS.registry_port)
    return c.add_image(image_data)


def update_image_metadata(image_id, image_data):
    c = client.RegistryClient(FLAGS.registry_host, FLAGS.registry_port)
    return c.update_image(image_id, image_data)


def delete_image_metadata(image_id):
    c = client.RegistryClient(FLAGS.registry_host, FLAGS.registry_port)
    return c.delete_image(image_id)
