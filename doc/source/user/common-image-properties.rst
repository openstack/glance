..
      Copyright 2013 OpenStack Foundation
      All Rights Reserved.

      Licensed under the Apache License, Version 2.0 (the "License"); you may
      not use this file except in compliance with the License. You may obtain
      a copy of the License at

          http://www.apache.org/licenses/LICENSE-2.0

      Unless required by applicable law or agreed to in writing, software
      distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
      WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
      License for the specific language governing permissions and limitations
      under the License.

Common Image Properties
=======================

When adding an image to Glance, you may specify some common image properties
that may prove useful to consumers of your image.

This document explains the names of these properties and the expected values.

The common image properties are also described in a JSON schema, found in
``/etc/glance/schema-image.json`` in the Glance source code.

kernel_id
  The ID of image stored in Glance that should be used as the kernel when
  booting an AMI-style image.

ramdisk_id
  The ID of image stored in Glance that should be used as the ramdisk when
  booting an AMI-style image.

instance_uuid
  Metadata which can be used to record which instance this image is associated
  with. (Informational only, does not create an instance snapshot.)

architecture
  Operating system architecture as specified in
  https://docs.openstack.org/python-glanceclient/latest/cli/property-keys.html

os_distro
  The common name of the operating system distribution as specified in
  https://docs.openstack.org/python-glanceclient/latest/cli/property-keys.html

os_version
  The operating system version as specified by the distributor.

description
  A brief human-readable string, suitable for display in a user interface,
  describing the image.

cinder_encryption_key_id
  Identifier in the OpenStack Key Management Service for the encryption key for
  the Block Storage Service to use when mounting a volume created from this
  image.

cinder_encryption_key_deletion_policy
  States the condition under which the Image Service will delete the object
  associated with the 'cinder_encryption_key_id' image property. If this
  property is missing, the Image Service will take no action.

This file is the default schema. An operator can modify
``/etc/schema-image.json`` to include arbitrary properties.

.. warning::
   * Do not delete existing properties from this default schema because this
     will affect interoperability
   * The ``type`` of each property in this JSON schema, specified by the
     ``type`` key, must have value ``string`` even if the property you are
     adding is not a string in common sense. For example, if you want to add a
     property named ``is_removable`` and want its type to be ``boolean``.
     However, you must give the ``type`` key the value ``string``. Otherwise,
     when an end-user makes a call that sets a value on one of these, they
     will gets a 500. This is because everything in the image_properties table
     must be a string in the database. The API, however, won't accept a string
     value when the schema says it is boolean or some other non-string JSON
     data type

.. note::
   If your need is more complicated, we recommend using metadefs_ instead of
   modifying this image schema

.. _metadefs: https://docs.openstack.org/api-ref/image/v2/metadefs-index.html
