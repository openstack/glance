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
etc/schema-image.json in the Glance source code.

**architecture**
----------------

Operating system architecture as specified in
http://docs.openstack.org/cli-reference/content/chapter_cli-glance-property.html


**instance_uuid**
-----------------

The ID of the instance used to create this image.

**kernel_id**
-------------

The ID of image stored in Glance that should be used as the kernel when booting
an AMI-style image.

**ramdisk_id**
--------------

The ID of image stored in Glance that should be used as the ramdisk when
booting an AMI-style image.

**os_distro**
-------------

The common name of the operating system distribution as specified in
http://docs.openstack.org/cli-reference/content/chapter_cli-glance-property.html

**os_version**
--------------

The operating system version as specified by the distributor.
