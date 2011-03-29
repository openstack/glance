# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack, LLC
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

import logging

from glance.registry import client

logger = logging.getLogger('glance.registry')


def get_registry_client(options):
    host = options['registry_host']
    port = int(options['registry_port'])
    return client.RegistryClient(host, port)


def get_images_list(options):
    c = get_registry_client(options)
    return c.get_images()


def get_images_detail(options):
    c = get_registry_client(options)
    return c.get_images_detailed()


def get_image_metadata(options, image_id):
    c = get_registry_client(options)
    return c.get_image(image_id)


def add_image_metadata(options, image_meta):
    if options['debug']:
        logger.debug("Adding image metadata...")
        _debug_print_metadata(image_meta)

    c = get_registry_client(options)
    new_image_meta = c.add_image(image_meta)

    if options['debug']:
        logger.debug("Returned image metadata from call to "
                     "RegistryClient.add_image():")
        _debug_print_metadata(new_image_meta)

    return new_image_meta


def update_image_metadata(options, image_id, image_meta, purge_props=False):
    if options['debug']:
        logger.debug("Updating image metadata for image %s...", image_id)
        _debug_print_metadata(image_meta)

    c = get_registry_client(options)
    new_image_meta = c.update_image(image_id, image_meta, purge_props)

    if options['debug']:
        logger.debug("Returned image metadata from call to "
                     "RegistryClient.update_image():")
        _debug_print_metadata(new_image_meta)

    return new_image_meta


def delete_image_metadata(options, image_id):
    logger.debug("Deleting image metadata for image %s...", image_id)
    c = get_registry_client(options)
    return c.delete_image(image_id)


def _debug_print_metadata(image_meta):
    data = image_meta.copy()
    properties = data.pop('properties', None)
    for key, value in sorted(data.items()):
        logger.debug(" %(key)20s: %(value)s" % locals())
    if properties:
        logger.debug(" %d custom properties...",
                     len(properties))
        for key, value in properties.items():
            logger.debug(" %(key)20s: %(value)s" % locals())
