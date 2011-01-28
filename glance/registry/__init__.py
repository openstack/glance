# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
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

from glance.registry import client


def get_registry_client(options):
    return client.RegistryClient(options['registry_host'],
                                 int(options['registry_port']))


def get_images_list(options):
    c = get_registry_client(options)
    return c.get_images()


def get_images_detail(options):
    c = get_registry_client(options)
    return c.get_images_detailed()


def get_image_metadata(options, image_id):
    c = get_registry_client(options)
    return c.get_image(image_id)


def add_image_metadata(options, image_data):
    c = get_registry_client(options)
    return c.add_image(image_data)


def update_image_metadata(options, image_id, image_data):
    c = get_registry_client(options)
    return c.update_image(image_id, image_data)


def delete_image_metadata(options, image_id):
    c = get_registry_client(options)
    return c.delete_image(image_id)
