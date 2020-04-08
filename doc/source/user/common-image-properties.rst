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
/etc/glance/schema-image.json in the Glance source code.

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
