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

raw
  This is an unstructured disk image format.

  The ``raw`` image format is the simplest one, and is natively supported by
  both KVM and Xen hypervisors.  You can think of a raw image as being the
  bit-equivalent of a block device file, created as if somebody had copied,
  say, ``/dev/sda`` to a file using the :command:`dd` command.

vhd
  This is the VHD (Virtual Hard Disk) disk format, a common disk format used by
  virtual machine monitors from VMware, Xen, Microsoft, VirtualBox, and others.

vhdx
  This is the `VHDX
  <http://technet.microsoft.com/en-us/library/hh831446.aspx>`_ format, an
  enhanced version of the ``vhd`` format.  It has support for larger disk sizes
  and protection against data corruption during power failures.

vmdk
  The
  `VMDK <https://developercenter.vmware.com/web/sdk/60/vddk>`_
  (Virtual Machine Disk) format is supported by many common virtual machine
  monitors, for example the VMware ESXi hypervisor.

vdi
  The `VDI <https://forums.virtualbox.org/viewtopic.php?t=8046>`_
  (Virtual Disk Image) format for image files is supported by the VirtualBox
  virtual machine monitor and the QEMU emulator.

iso
  The `ISO
  <http://www.ecma-international.org/publications/standards/Ecma-119.htm>`_
  format is a disk image formatted with the read-only ISO 9660 (also known
  as ECMA-119) filesystem commonly used for CDs and DVDs.

ploop
  A disk format supported and used by Virtuozzo to run OS Containers.

qcow2
  The `QCOW2 <http://en.wikibooks.org/wiki/QEMU/Images>`_
  (QEMU copy-on-write version 2) format is commonly used with the
  KVM hypervisor.  It uses a sparse representation, so the image size
  is smaller than a raw format file of the same virtual disk.  It can
  expand dynamically and supports Copy on Write.

The `AKI/AMI/ARI
<http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/AMIs.html>`_
format was the initial image format supported by Amazon EC2.
The image consists of three files, each of which has its own specific
``disk_format`` identifier:

aki
  This indicates what is stored in Glance is an Amazon Kernel Image (AKI).
  It is a kernel file that the hypervisor will load initially to boot the
  image.  For a Linux machine, this would be a ``vmlinuz`` file.

ari
  This indicates what is stored in Glance is an Amazon Ramdisk Image (ARI).
  It is an optional ramdisk file mounted at boot time.
  For a Linux machine, this would be an ``initrd`` file.

ami
  This indicates what is stored in Glance is an Amazon Machine Image (AMI).
  It is a virtual machine image in raw format.

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

bare
  This indicates there is no container or metadata envelope for the image.

ovf
  `OVF <http://dmtf.org/sites/default/files/OVF_Overview_Document_2010.pdf>`_
  (Open Virtualization Format) is a packaging format for virtual machines,
  defined by the Distributed Management Task Force (DMTF) standards group.
  An OVF package contains one or more image files, a ``.ovf`` XML metadata file
  that contains information about the virtual machine, and possibly other
  files as well.

  An OVF package can be distributed in different ways. For example,
  it could be distributed as a set of discrete files, or as a tar archive
  file with an ``.ova`` (open virtual appliance/application) extension.

aki
  This indicates what is stored in Glance is an Amazon kernel image.

ari
  This indicates what is stored in Glance is an Amazon ramdisk image.

ami
  This indicates what is stored in Glance is an Amazon machine image.

ova
  This indicates what is stored in Glance is an OVA tar archive file,
  that is, an OVF package contained in a single tar archive file.

docker
  This indicates what is stored in Glance is a Docker tar archive of
  the container filesystem.

compressed
  The exact format of the compressed file is not specified. It is the
  responsibility of the consuming service to analyze the data payload
  and determine the specific compression format. A particular
  OpenStack service may only support specific formats.

  You may assume that any OpenStack service that creates an image with
  a 'compressed' container format will be able to consume that image.

  Consult the documentation for the service that will consume your
  image for details.
