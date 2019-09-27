=============
Manage images
=============

The cloud operator assigns roles to users. Roles determine who can
upload and manage images. The operator might restrict image upload and
management to only cloud administrators or operators.

You can upload images through the :command:`glance image-create` or
:command:`glance image-create-via-import` command or the Image service API.
You can use the ``glance`` client for the image management. It provides
mechanisms to do all operations supported by the Images API v2.

After you upload an image, you cannot change the content, but you can update
the metadata.

For details about image creation, see the `Virtual Machine Image
Guide <https://docs.openstack.org/image-guide/>`__.

List or get details for images (glance)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To get a list of images and to get further details about a single
image, use :command:`glance image-list` and :command:`glance image-show`
commands.

.. code-block:: console

   $ glance image-list
   +--------------------------------------+---------------------------------+
   | ID                                   | Name                            |
   +--------------------------------------+---------------------------------+
   | dfc1dfb0-d7bf-4fff-8994-319dd6f703d7 | cirros-0.3.5-x86_64-uec         |
   | a3867e29-c7a1-44b0-9e7f-10db587cad20 | cirros-0.3.5-x86_64-uec-kernel  |
   | 4b916fba-6775-4092-92df-f41df7246a6b | cirros-0.3.5-x86_64-uec-ramdisk |
   | d07831df-edc3-4817-9881-89141f9134c3 | myCirrosImage                   |
   +--------------------------------------+---------------------------------+
.. code-block:: console

   $ glance image-show d07831df-edc3-4817-9881-89141f9134c3
   +------------------+------------------------------------------------------+
   | Field            | Value                                                |
   +------------------+------------------------------------------------------+
   | checksum         | 443b7623e27ecf03dc9e01ee93f67afe                     |
   | container_format | ami                                                  |
   | created_at       | 2016-08-11T15:07:26Z                                 |
   | disk_format      | ami                                                  |
   | file             | /v2/images/d07831df-edc3-4817-9881-89141f9134c3/file |
   | id               | d07831df-edc3-4817-9881-89141f9134c3                 |
   | min_disk         | 0                                                    |
   | min_ram          | 0                                                    |
   | name             | myCirrosImage                                        |
   | os_hash_algo     | sha512                                               |
   | os_hash_value    | 6513f21e44aa3da349f248188a44bc304a3653a04122d8fb4535 |
   |                  | 423c8e1d14cd6a153f735bb0982e2161b5b5186106570c17a9e5 |
   |                  | 8b64dd39390617cd5a350f78                             |
   | os_hidden        | False                                                |
   | owner            | d88310717a8e4ebcae84ed075f82c51e                     |
   | protected        | False                                                |
   | schema           | /v2/schemas/image                                    |
   | size             | 13287936                                             |
   | status           | active                                               |
   | tags             |                                                      |
   | updated_at       | 2016-08-11T15:20:02Z                                 |
   | virtual_size     | None                                                 |
   | visibility       | private                                              |
   +------------------+------------------------------------------------------+

When viewing a list of images, you can also use ``grep`` to filter the
list, as follows:

.. code-block:: console

   $ glance image-list | grep 'cirros'
   | dfc1dfb0-d7bf-4fff-8994-319dd6f703d7 | cirros-0.3.5-x86_64-uec         |
   | a3867e29-c7a1-44b0-9e7f-10db587cad20 | cirros-0.3.5-x86_64-uec-kernel  |
   | 4b916fba-6775-4092-92df-f41df7246a6b | cirros-0.3.5-x86_64-uec-ramdisk |

Create or update an image (glance)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To create an image, use :command:`glance image-create`:

.. code-block:: console

   $ glance image-create --name imageName

To update an image, you must specify its ID and use
:command:`glance image-update`:

.. code-block:: console

   $ glance image-update --property x="y" <IMAGE_ID>

The following list explains the commonly used properties that you can set or
modify when using the ``image-create`` and ``image-update`` commands.
For more information, refer to the `OpenStack Useful Image Properties
<https://docs.openstack.org/glance/latest/admin/useful-image-properties.html>`_.

``--architecture <ARCHITECTURE>``
    Operating system architecture as specified in
    https://docs.openstack.org/glance/latest/admin/useful-image-properties.html

``--protected [True|False]``
    If true, image will not be deletable.

``--name <NAME>``
    Descriptive name for the image

``--instance-uuid <INSTANCE_UUID>``
    Metadata which can be used to record which instance this image is
    associated with. (Informational only, does not create an instance
    snapshot.)

``--min-disk <MIN_DISK>``
    Amount of disk space (in GB) required to boot image.

``--visibility <VISIBILITY>``
    Scope of image accessibility.  Valid values: ``public``, ``private``,
    ``community``, ``shared``

``--kernel-id <KERNEL_ID>``
    ID of image stored in Glance that should be used as the kernel when
    booting an AMI-style image.

``--os-version <OS_VERSION>``
    Operating system version as specified by the distributor

``--disk-format <DISK_FORMAT>``
    Format of the disk.  May not be modified once an image has gone
    to ``active`` status.  Valid values: ``ami``, ``ari``, ``aki``, ``vhd``,
    ``vhdx``, ``vmdk``, ``raw``, ``qcow2``, ``vdi``, ``iso``, ``ploop``

``--os-distro <OS_DISTRO>``
    Common name of operating system distribution as specified in
    https://docs.openstack.org/glance/latest/admin/useful-image-properties.html

``--owner <OWNER>``
    Owner of the image.  Usually, may be set by an admin only.

``--ramdisk-id <RAMDISK_ID>``
    ID of image stored in Glance that should be used as the ramdisk when
    booting an AMI-style image.

``--min-ram <MIN_RAM>``
    Amount of ram (in MB) required to boot image.

``--container-format <CONTAINER_FORMAT>``
    Format of the container.  May not be modified once an image has gone
    to ``active`` status.  Valid values: ``ami``, ``ari``, ``aki``,
    ``bare``, ``ovf``, ``ova``, ``docker``, ``compressed``

``--hidden [True|False]``
    If true, image will not appear in default image list response.

``--property <key=value>``
    Arbitrary property to associate with image. May be used multiple times.

``--remove-property key``
    Name of arbitrary property to remove from the image.

The following example shows the command that you would use to upload a
CentOS 6.3 image in qcow2 format and configure it for public access:

.. code-block:: console

   $ glance image-create --disk-format qcow2 --container-format bare \
     --visibility public --file ./centos63.qcow2 --name centos63-image

The following example shows how to update an existing image with a
properties that describe the disk bus, the CD-ROM bus, and the VIF
model:

.. note::

   When you use OpenStack with VMware vCenter Server, you need to specify
   the ``vmware_disktype`` and ``vmware_adaptertype`` properties with
   :command:`glance image-create`.
   Also, we recommend that you set the ``hypervisor_type="vmware"`` property.
   For more information, see `Images with VMware vSphere
   <https://docs.openstack.org/ocata/config-reference/compute/hypervisor-vmware.html#images-with-vmware-vsphere>`_
   in the OpenStack Configuration Reference.

.. code-block:: console

   $ glance image-update \
       --property hw_disk_bus=scsi \
       --property hw_cdrom_bus=ide \
       --property hw_vif_model=e1000 \
       <Image-ID>

Currently the libvirt virtualization tool determines the disk, CD-ROM,
and VIF device models based on the configured hypervisor type
(``libvirt_type`` in ``/etc/nova/nova.conf`` file). For the sake of optimal
performance, libvirt defaults to using virtio for both disk and VIF
(NIC) models. The disadvantage of this approach is that it is not
possible to run operating systems that lack virtio drivers, for example,
BSD, Solaris, and older versions of Linux and Windows.

If you specify a disk or CD-ROM bus model that is not supported, see
the Disk_and_CD-ROM_bus_model_values_table_.
If you specify a VIF model that is not supported, the instance fails to
launch. See the VIF_model_values_table_.

The valid model values depend on the ``libvirt_type`` setting, as shown
in the following tables.

.. _Disk_and_CD-ROM_bus_model_values_table:

**Disk and CD-ROM bus model values**

+-------------------------+--------------------------+
| libvirt\_type setting   | Supported model values   |
+=========================+==========================+
| qemu or kvm             | *  fdc                   |
|                         |                          |
|                         | *  ide                   |
|                         |                          |
|                         | *  scsi                  |
|                         |                          |
|                         | *  sata                  |
|                         |                          |
|                         | *  virtio                |
|                         |                          |
|                         | *  usb                   |
+-------------------------+--------------------------+
| xen                     | *  ide                   |
|                         |                          |
|                         | *  xen                   |
+-------------------------+--------------------------+


.. _VIF_model_values_table:

**VIF model values**

+-------------------------+--------------------------+
| libvirt\_type setting   | Supported model values   |
+=========================+==========================+
| qemu or kvm             | *  e1000                 |
|                         |                          |
|                         | *  ne2k\_pci             |
|                         |                          |
|                         | *  pcnet                 |
|                         |                          |
|                         | *  rtl8139               |
|                         |                          |
|                         | *  virtio                |
+-------------------------+--------------------------+
| xen                     | *  e1000                 |
|                         |                          |
|                         | *  netfront              |
|                         |                          |
|                         | *  ne2k\_pci             |
|                         |                          |
|                         | *  pcnet                 |
|                         |                          |
|                         | *  rtl8139               |
+-------------------------+--------------------------+
| vmware                  | *  VirtualE1000          |
|                         |                          |
|                         | *  VirtualPCNet32        |
|                         |                          |
|                         | *  VirtualVmxnet         |
+-------------------------+--------------------------+

.. note::

   By default, hardware properties are retrieved from the image
   properties. However, if this information is not available, the
   ``libosinfo`` database provides an alternative source for these
   values.

   If the guest operating system is not in the database, or if the use
   of ``libosinfo`` is disabled, the default system values are used.

   Users can set the operating system ID or a ``short-id`` in image
   properties. For example:

   .. code-block:: console

      $ glance image-update --property short-id=fedora23 \
        <Image-ID>

Create an image from ISO image
------------------------------

You can upload ISO images to the Image service (glance).
You can subsequently boot an ISO image using Compute.

In the Image service, run the following command:

.. code-block:: console

   $ glance image-create --name ISO_IMAGE --file IMAGE.iso \
     --disk-format iso --container-format bare

Optionally, to confirm the upload in Image service, run:

.. code-block:: console

   $ glance image-list

Troubleshoot image creation
~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you encounter problems in creating an image in the Image service or
Compute, the following information may help you troubleshoot the
creation process.

*  Ensure that the version of qemu you are using is version 0.14 or
   later. Earlier versions of qemu result in an ``unknown option -s``
   error message in the ``/var/log/nova/nova-compute.log`` file.

*  Examine the ``/var/log/nova/nova-api.log`` and
   ``/var/log/nova/nova-compute.log`` log files for error messages.
