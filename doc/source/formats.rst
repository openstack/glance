..
      Copyright 2011 OpenStack, LLC
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

Disk and Container Formats
==========================

When adding an image to Glance, you are may specify what the virtual
machine image's *disk format* and *container format* are.

This document explains exactly what these formats are.

Disk Format
-----------

The disk format of a virtual machine image is the format of the underlying
disk image. Virtual appliance vendors have different formats for laying out
the information contained in a virtual machine disk image.

You can set your image's container format to one of the following:

* **raw**

  This is an unstructured disk image format

* **vhd**

  This is the VHD disk format, a common disk format used by virtual machine
  monitors from VMWare, Xen, Microsoft, VirtualBox, and others

* **vmdk**

  Another common disk format supported by many common virtual machine monitors

* **vdi**

  A disk format supported by VirtualBox virtual machine monitor and the QEMU
  emulator

* **iso**

  An archive format for the data contents of an optical disc (e.g. CDROM). 

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

There are two main types of container formats: OVF and Amazon's AMI. In
addition, a virtual machine image may have no container format at all --
basically, it's just a blob of unstructured data...

You can set your image's container format to one of the following:

* **ovf**

  This is the OVF container format

* **bare**

  This indicates there is no container or metadata envelope for the image

* **aki**

  This indicates what is stored in Glance is an Amazon kernel image

* **ari**

  This indicates what is stored in Glance is an Amazon ramdisk image

* **ami**

  This indicates what is stored in Glance is an Amazon machine image
