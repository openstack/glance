..
      Copyright 2011 OpenStack Foundation
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

.. _formats:

Disk and Container Formats
==========================

When adding an image to Glance, you must specify what the virtual
machine image's *disk format* and *container format* are. Disk and container
formats are configurable on a per-deployment basis. This document intends to
establish a global convention for what specific values of *disk_format* and
*container_format* mean.

Disk Format
-----------

The disk format of a virtual machine image is the format of the underlying
disk image. Virtual appliance vendors have different formats for laying out
the information contained in a virtual machine disk image.

You can set your image's disk format to one of the following:

* **raw**

  This is an unstructured disk image format

* **vhd**

  This is the VHD disk format, a common disk format used by virtual machine
  monitors from VMware, Xen, Microsoft, VirtualBox, and others

* **vhdx**

  This is the VHDX disk format, an enhanced version of the vhd format which
  supports larger disk sizes among other features.

* **vmdk**

  Another common disk format supported by many common virtual machine monitors

* **vdi**

  A disk format supported by VirtualBox virtual machine monitor and the QEMU
  emulator

* **iso**

  An archive format for the data contents of an optical disc (e.g. CDROM).

* **ploop**

  A disk format supported and used by Virtuozzo to run OS Containers

* **qcow2**

  A disk format supported by the QEMU emulator that can expand dynamically and
  supports Copy on Write

* **aki**

  This indicates what is stored in Glance is an Amazon kernel image

* **ari**

  This indicates what is stored in Glance is an Amazon ramdisk image

* **ami**

  This indicates what is stored in Glance is an Amazon machine image

Container Format
----------------

The container format refers to whether the virtual machine image is in a
file format that also contains metadata about the actual virtual machine.

Note the following:

1. Glance does not verify that the ``container_format`` image property
   accurately describes the image data payload.

2. Do not assume that all OpenStack services can handle all the container
   formats defined by Glance.

   Consult the documentation for the service consuming your image to see
   what container formats the service supports.

You can set your image's container format to one of the following:

* **bare**

  This indicates there is no container or metadata envelope for the image

* **ovf**

  This is the OVF container format

* **aki**

  This indicates what is stored in Glance is an Amazon kernel image

* **ari**

  This indicates what is stored in Glance is an Amazon ramdisk image

* **ami**

  This indicates what is stored in Glance is an Amazon machine image

* **ova**

  This indicates what is stored in Glance is an OVA tar archive file

* **docker**

  This indicates what is stored in Glance is a Docker tar archive of
  the container filesystem

* **compressed**

  The exact format of the compressed file is not specified. It is the
  responsibility of the consuming service to analyze the data payload
  and determine the specific compression format. A particular
  OpenStack service may only support specific formats.

  You may assume that any OpenStack service that creates an image with
  a 'compressed' container format will be able to consume that image.

  Consult the documentation for the service that will consume your
  image for details.
