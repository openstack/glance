=======================
Useful image properties
=======================

You can set image properties that can be consumed by other services to affect
the behavior of those other services.  For example:

* Image properties can be used to override specific behaviors defined for
  Nova flavors

* Image properties can be used to affect the behavior of the Nova scheduler

* Image properties can be used to affect the behavior of particular Nova
  hypervisors

Using image properties
~~~~~~~~~~~~~~~~~~~~~~

Some important points to keep in mind:

* In order to allow custom image properties, Glance must be configured with
  the ``glance-api.conf`` setting ``allow_additional_image_properties`` set
  to True.  (This is the default setting.)

* The ``glance-api.conf`` setting ``image_property_quota`` should be
  sufficiently high to allow any additional desired properties.  (The default
  is 128.)

* You can use Glance *property protections* to control access to specific
  image properties, should that be desirable.  See the
  :ref:`property-protections` section of this Guide for more information.

* You can use a plugin to the interoperable image import process to set
  specific properties on non-admin images imported into Glance.  See
  :ref:`iir_plugins` for more information.  See the original spec,
  `Inject metadata properties automatically to non-admin images
  <https://specs.openstack.org/openstack/glance-specs/specs/queens/implemented/glance/inject-automatic-metadata.html>`_
  for a discussion of the use case addressed by this plugin.

* The Nova **ImagePropertiesFilter**, enabled by default in the Compute
  Service, consumes image properties to determine proper scheduling of builds
  to compute hosts.  See the `Compute schedulers
  <https://docs.openstack.org/nova/latest/admin/configuration/schedulers.html>`_
  section of the Nova Configuration Guide for more information.

* Nova has a setting, ``non_inheritable_image_properties``, that allows you
  to specify which image properties from the image a virtual machine
  was booted from will *not* be propagated to a snapshot image of that
  virtual machine.  See the `Configuration Options
  <https://docs.openstack.org/nova/latest/configuration/config.html>`_
  section of the Nova Configuration Guide for more information.

* Some properties recognized by Nova may have no effect unless a corresponding
  property is enabled in the server flavor.  For example, the ``hw_rng_model``
  image property has no effect unless the Nova flavor has been configured to
  have ``hw_rng:allowed`` set to True in the flavor's extra_specs.

* In a mixed hypervisor environment, the Compute Service uses the
  ``hypervisor_type`` image property to match images to the correct hypervisor
  type.

  Depending upon what hypervisors are in use in your Nova installation, there
  may be other image properties that these hypervisors can consume to affect
  their behavior.  Read through the configuration information for your
  hypervisors in the `Hypervisors
  <https://docs.openstack.org/nova/latest/admin/configuration/hypervisors.html>`_
  section of the Nova Configuration Guide for more information.

  In particular, the VMware hypervisor driver requires that particular
  image properties be set for optimal functioning.  See the `VMware vSphere
  <https://docs.openstack.org/nova/latest/admin/configuration/hypervisor-vmware.html>`_
  section of the Nova Configuration Guide for more information.

.. _image_property_keys_and_values:

Image property keys and values
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Here is a list of useful image properties and the values they expect.

.. list-table::
   :widths: 15 35 50 90
   :header-rows: 1

   * - Specific to
     - Key
     - Description
     - Supported values
   * - All
     - ``architecture``
     - The CPU architecture that must be supported by the hypervisor. For
       example, ``x86_64``, ``arm``, or ``ppc64``. Run :command:`uname -m`
       to get the architecture of a machine. We strongly recommend using
       the architecture data vocabulary defined by the `libosinfo project
       <http://libosinfo.org/>`_ for this purpose.
     - * ``alpha`` - `DEC 64-bit RISC
         <https://en.wikipedia.org/wiki/DEC_Alpha>`_
       * ``armv7l`` - `ARM Cortex-A7 MPCore
         <https://en.wikipedia.org/wiki/ARM_architecture>`_
       * ``cris`` - `Ethernet, Token Ring, AXis—Code Reduced Instruction
         Set <https://en.wikipedia.org/wiki/ETRAX_CRIS>`_
       * ``i686`` - `Intel sixth-generation x86 (P6 micro architecture)
         <https://en.wikipedia.org/wiki/X86>`_
       * ``ia64`` - `Itanium <https://en.wikipedia.org/wiki/Itanium>`_
       * ``lm32`` - `Lattice Micro32
         <https://en.wikipedia.org/wiki/Milkymist>`_
       * ``m68k`` - `Motorola 68000
         <https://en.wikipedia.org/wiki/Motorola_68000_family>`_
       * ``microblaze`` - `Xilinx 32-bit FPGA (Big Endian)
         <https://en.wikipedia.org/wiki/MicroBlaze>`_
       * ``microblazeel`` - `Xilinx 32-bit FPGA (Little Endian)
         <https://en.wikipedia.org/wiki/MicroBlaze>`_
       * ``mips`` - `MIPS 32-bit RISC (Big Endian)
         <https://en.wikipedia.org/wiki/MIPS_architecture>`_
       * ``mipsel`` - `MIPS 32-bit RISC (Little Endian)
         <https://en.wikipedia.org/wiki/MIPS_architecture>`_
       * ``mips64`` - `MIPS 64-bit RISC (Big Endian)
         <https://en.wikipedia.org/wiki/MIPS_architecture>`_
       * ``mips64el`` - `MIPS 64-bit RISC (Little Endian)
         <https://en.wikipedia.org/wiki/MIPS_architecture>`_
       * ``openrisc`` - `OpenCores RISC
         <https://en.wikipedia.org/wiki/OpenRISC#QEMU_support>`_
       * ``parisc`` - `HP Precision Architecture RISC
         <https://en.wikipedia.org/wiki/PA-RISC>`_
       * parisc64 - `HP Precision Architecture 64-bit RISC
         <https://en.wikipedia.org/wiki/PA-RISC>`_
       * ppc - `PowerPC 32-bit <https://en.wikipedia.org/wiki/PowerPC>`_
       * ppc64 - `PowerPC 64-bit <https://en.wikipedia.org/wiki/PowerPC>`_
       * ppcemb - `PowerPC (Embedded 32-bit)
         <https://en.wikipedia.org/wiki/PowerPC>`_
       * s390 - `IBM Enterprise Systems Architecture/390
         <https://en.wikipedia.org/wiki/S390>`_
       * s390x - `S/390 64-bit <https://en.wikipedia.org/wiki/S390x>`_
       * sh4 - `SuperH SH-4 (Little Endian)
         <https://en.wikipedia.org/wiki/SuperH>`_
       * sh4eb - `SuperH SH-4 (Big Endian)
         <https://en.wikipedia.org/wiki/SuperH>`_
       * sparc - `Scalable Processor Architecture, 32-bit
         <https://en.wikipedia.org/wiki/Sparc>`_
       * sparc64 - `Scalable Processor Architecture, 64-bit
         <https://en.wikipedia.org/wiki/Sparc>`_
       * unicore32 - `Microprocessor Research and Development Center RISC
         Unicore32 <https://en.wikipedia.org/wiki/Unicore>`_
       * x86_64 - `64-bit extension of IA-32
         <https://en.wikipedia.org/wiki/X86>`_
       * xtensa - `Tensilica Xtensa configurable microprocessor core
         <https://en.wikipedia.org/wiki/Xtensa#Processor_Cores>`_
       * xtensaeb - `Tensilica Xtensa configurable microprocessor core
         <https://en.wikipedia.org/wiki/Xtensa#Processor_Cores>`_ (Big Endian)
   * - All
     - ``hypervisor_type``
     - The hypervisor type. Note that ``qemu`` is used for both QEMU and KVM
       hypervisor types.
     - ``hyperv``, ``ironic``, ``lxc``, ``qemu``, ``uml``, ``vmware``, or
       ``xen``.
   * - All
     - ``instance_type_rxtx_factor``
     - Optional property allows created servers to have a different bandwidth
       cap than that defined in the network they are attached to. This factor
       is multiplied by the ``rxtx_base`` property of the network. The
       ``rxtx_base`` property defaults to ``1.0``, which is the same as the
       attached network. This parameter is only available for Xen or NSX based
       systems.
     - Float (default value is ``1.0``)
   * - All
     - ``instance_uuid``
     - For snapshot images, this is the UUID of the server used to create this
       image.
     - Valid server UUID
   * - All
     - ``img_config_drive``
     - Specifies whether the image needs a config drive.
     - ``mandatory`` or ``optional`` (default if property is not used).
   * - All
     - ``kernel_id``
     - The ID of an image stored in the Image service that should be used as
       the kernel when booting an AMI-style image.
     - Valid image ID
   * - All
     - ``os_distro``
     - The common name of the operating system distribution in lowercase
       (uses the same data vocabulary as the
       `libosinfo project`_). Specify only a recognized
       value for this field. Deprecated values are listed to assist you in
       searching for the recognized value.
     - * ``arch`` - Arch Linux. Do not use ``archlinux`` or ``org.archlinux``.
       * ``centos`` - Community Enterprise Operating System. Do not use
         ``org.centos`` or ``CentOS``.
       * ``debian`` - Debian. Do not use ``Debian` or ``org.debian``.
       * ``fedora`` - Fedora. Do not use ``Fedora``, ``org.fedora``, or
         ``org.fedoraproject``.
       * ``freebsd`` - FreeBSD. Do not use ``org.freebsd``, ``freeBSD``, or
         ``FreeBSD``.
       * ``gentoo`` - Gentoo Linux. Do not use ``Gentoo`` or ``org.gentoo``.
       * ``mandrake`` - Mandrakelinux (MandrakeSoft) distribution. Do not use
         ``mandrakelinux`` or ``MandrakeLinux``.
       * ``mandriva`` - Mandriva Linux. Do not use ``mandrivalinux``.
       * ``mes`` - Mandriva Enterprise Server. Do not use ``mandrivaent`` or
         ``mandrivaES``.
       * ``msdos`` - Microsoft Disc Operating System. Do not use ``ms-dos``.
       * ``netbsd`` - NetBSD. Do not use ``NetBSD`` or ``org.netbsd``.
       * ``netware`` - Novell NetWare. Do not use ``novell`` or ``NetWare``.
       * ``openbsd`` - OpenBSD. Do not use ``OpenBSD`` or ``org.openbsd``.
       * ``opensolaris`` - OpenSolaris. Do not use ``OpenSolaris`` or
         ``org.opensolaris``.
       * ``opensuse`` - openSUSE. Do not use ``suse``, ``SuSE``, or
         `` org.opensuse``.
       * ``rhel`` - Red Hat Enterprise Linux. Do not use ``redhat``, ``RedHat``,
         or ``com.redhat``.
       * ``sled`` - SUSE Linux Enterprise Desktop. Do not use ``com.suse``.
       * ``ubuntu`` - Ubuntu. Do not use ``Ubuntu``, ``com.ubuntu``,
         ``org.ubuntu``, or ``canonical``.
       * ``windows`` - Microsoft Windows. Do not use ``com.microsoft.server``
         or ``windoze``.
   * - All
     - ``os_version``
     - The operating system version as specified by the distributor.
     - Valid version number (for example, ``11.10``).
   * - All
     - ``os_secure_boot``
     - Secure Boot is a security standard. When the instance starts,
       Secure Boot first examines software such as firmware and OS by their
       signature and only allows them to run if the signatures are valid.

       For Hyper-V: Images must be prepared as Generation 2 VMs. Instance must
       also contain ``hw_machine_type=hyperv-gen2`` image property. Linux
       guests will also require bootloader's digital signature provided as
       ``os_secure_boot_signature`` and
       ``hypervisor_version_requires'>=10.0'`` image properties.
     - * ``required`` - Enable the Secure Boot feature.
       * ``disabled`` or ``optional`` - (default) Disable the Secure Boot
         feature.
   * - All
     - ``os_shutdown_timeout``
     - By default, guests will be given 60 seconds to perform a graceful
       shutdown. After that, the VM is powered off. This property allows
       overriding the amount of time (unit: seconds) to allow a guest OS to
       cleanly shut down before power off. A value of 0 (zero) means the guest
       will be powered off immediately with no opportunity for guest OS
       clean-up.
     - Integer value (in seconds) with a minimum of 0 (zero). Default is 60.
   * - All
     - ``ramdisk_id``
     - The ID of image stored in the Image service that should be used as the
       ramdisk when booting an AMI-style image.
     - Valid image ID.
   * - All
     - ``trait:<trait_name>``
     - Added in the Rocky release. Functionality is similar to traits specified
       in `flavor extra specs <https://docs.openstack.org/nova/latest/user/flavors.html#extra-specs>`_.

       Traits allow specifying a server to build on a compute node with the set
       of traits specified in the image. The traits are associated with the
       resource provider that represents the compute node in the Placement API.

       The syntax of specifying traits is **trait:<trait_name>=value**, for
       example:

       * trait:HW_CPU_X86_AVX2=required
       * trait:STORAGE_DISK_SSD=required

       The nova scheduler will pass required traits specified on the image to
       the Placement API to include only resource providers that can satisfy
       the required traits. Traits for the resource providers can be managed
       using the `osc-placement plugin. <https://docs.openstack.org/osc-placement/latest/index.html>`_

       Image traits are used by the nova scheduler even in cases of volume
       backed instances, if the volume source is an image with traits.
     - Only valid value is ``required``, any other value is invalid.

       * ``required`` - <trait_name> is required on the resource provider that
         represents the compute node on which the image is launched.
   * - All
     - ``vm_mode``
     - The virtual machine mode. This represents the host/guest ABI
       (application binary interface) used for the virtual machine.
     - * ``hvm`` - Fully virtualized. This is the mode used by QEMU and KVM.
       * ``xen`` - Xen 3.0 paravirtualized.
       * ``uml`` - User Mode Linux paravirtualized.
       * ``exe`` - Executables in containers. This is the mode used by LXC.
   * - libvirt API driver
     - ``hw_cpu_sockets``
     - The preferred number of sockets to expose to the guest.
     - Integer.
   * - libvirt API driver
     - ``hw_cpu_cores``
     - The preferred number of cores to expose to the guest.
     - Integer.
   * - libvirt API driver
     - ``hw_cpu_threads``
     - The preferred number of threads to expose to the guest.
     - Integer.
   * - libvirt API driver
     - ``hw_cpu_policy``
     - Used to pin the virtual CPUs (vCPUs) of instances to the host’s
       physical CPU cores (pCPUs). Host aggregates should be used to separate
       these pinned instances from unpinned instances as the latter will not
       respect the resourcing requirements of the former.
     - * ``shared`` - (default) The guest vCPUs will be allowed to freely float
         across host pCPUs, albeit potentially constrained by NUMA policy.
       * ``dedicated`` - The guest vCPUs will be strictly pinned to a set of
         host pCPUs. In the absence of an explicit vCPU topology request, the
         drivers typically expose all vCPUs as sockets with one core and one
         thread. When strict CPU pinning is in effect the guest CPU topology
         will be setup to match the topology of the CPUs to which it is pinned.
         This option implies an overcommit ratio of 1.0. For example, if a two
         vCPU guest is pinned to a single host core with two threads, then the
         guest will get a topology of one socket, one core, two threads.
   * - libvirt API driver
     - ``hw_cpu_thread_policy``
     - Further refine ``hw_cpu_policy=dedicated`` by stating how hardware CPU
       threads in a simultaneous multithreading-based (SMT) architecture be
       used. SMT-based architectures include Intel processors with
       Hyper-Threading technology. In these architectures, processor cores
       share a number of components with one or more other cores. Cores in
       such architectures are commonly referred to as hardware threads, while
       the cores that a given core share components with are known as thread
       siblings.
     - * ``prefer`` - (default) The host may or may not have an SMT
         architecture. Where an SMT architecture is present, thread siblings
         are preferred.
       * ``isolate`` - The host must not have an SMT architecture or must
         emulate a non-SMT architecture. If the host does not have an SMT
         architecture, each vCPU is placed on a different core as expected. If
         the host does have an SMT architecture - that is, one or more cores
         have thread siblings - then each vCPU is placed on a different
         physical core. No vCPUs from other guests are placed on the same core.
         All but one thread sibling on each utilized core is therefore
         guaranteed to be unusable.
       * ``require`` - The host must have an SMT architecture. Each vCPU is
         allocated on thread siblings. If the host does not have an SMT
         architecture, then it is not used. If the host has an SMT
         architecture, but not enough cores with free thread siblings are
         available, then scheduling fails.
   * - libvirt API driver
     - ``hw_cdrom_bus``
     - Specifies the type of disk controller to attach CD-ROM devices to.
     - As for ``hw_disk_bus``.
   * - libvirt API driver
     - ``hw_disk_bus``
     - Specifies the type of disk controller to attach disk devices to.
     - Options depend on the value of `nova's virt_type config option
       <https://docs.openstack.org/nova/latest/configuration/config.html#libvirt.virt_type>`_:

       * For ``qemu`` and ``kvm``: one of ``scsi``, ``virtio``,
         ``uml``, ``xen``, ``ide``, ``usb``, or ``lxc``.
       * For ``xen``: one of ``xen`` or ``ide``.
       * For ``uml``: must be ``uml``.
       * For ``lxc``: must be ``lxc``.
       * For ``parallels``: one of ``ide`` or ``scsi``.
   * - libvirt API driver
     - ``hw_firmware_type``
     - Specifies the type of firmware with which to boot the guest.
     - One of ``bios`` or ``uefi``.
   * - libvirt API driver
     - ``hw_mem_encryption``
     - Enables encryption of guest memory at the hardware level, if
       there are compute hosts available which support this. See
       `nova's documentation on configuration of the KVM hypervisor
       <https://docs.openstack.org/nova/latest/admin/configuration/hypervisor-kvm.html#amd-sev-secure-encrypted-virtualization>`_
       for more details.
     - ``true`` or ``false`` (default).
   * - libvirt API driver
     - ``hw_pointer_model``
     - Input devices that allow interaction with a graphical framebuffer,
       for example to provide a graphic tablet for absolute cursor movement.
       Currently only supported by the KVM/QEMU hypervisor configuration
       and VNC or SPICE consoles must be enabled.
     - ``usbtablet``
   * - libvirt API driver
     - ``hw_rng_model``
     - Adds a random-number generator device to the image's instances.  This
       image property by itself does not guarantee that a hardware RNG will be
       used; it expresses a preference that may or may not be satisfied
       depending upon Nova configuration.

       The cloud administrator can enable and control device behavior by
       configuring the instance's flavor. By default:

       * The generator device is disabled.
       * ``/dev/urandom`` is used as the default entropy source. To
         specify a physical HW RNG device, use the following option in
         the nova.conf file:

       .. code-block:: ini

          rng_dev_path=/dev/hwrng

       * The use of a hardware random number generator must be configured in a
         flavor's extra_specs by setting ``hw_rng:allowed`` to True in the
         flavor definition.
     - ``virtio``, or other supported device.
   * - libvirt API driver
     - ``hw_time_hpet``
     - Adds support for the High Precision Event Timer (HPET) for x86 guests
       in the libvirt driver when ``hypervisor_type=qemu`` and
       ``architecture=i686`` or ``architecture=x86_64``. The timer can be
       enabled by setting ``hw_time_hpet=true``. By default HPET remains
       disabled.
     - ``true`` or ``false`` (default)
   * - libvirt API driver, Hyper-V driver
     - ``hw_machine_type``
     - For libvirt: Enables booting an ARM system using the specified machine
       type. By default, if an ARM image is used and its type is not specified,
       Compute uses ``vexpress-a15`` (for ARMv7) or ``virt`` (for AArch64)
       machine types.

       For Hyper-V: Specifies whether the Hyper-V instance will be a generation
       1 or generation 2 VM. By default, if the property is not provided, the
       instances will be generation 1 VMs. If the image is specific for
       generation 2 VMs but the property is not provided accordingly, the
       instance will fail to boot.
     - For libvirt: Valid types can be viewed by using the
       :command:`virsh capabilities` command (machine types are displayed in
       the ``machine`` tag).

       For hyper-V: Acceptable values are either ``hyperv-gen1`` or
       ``hyperv-gen2``.
   * - libvirt API driver, XenAPI driver
     - ``os_type``
     - The operating system installed on the image. The ``libvirt`` API driver
       and ``XenAPI`` driver contains logic that takes different actions
       depending on the value of the ``os_type`` parameter of the image.
       For example, for ``os_type=windows`` images, it creates a FAT32-based
       swap partition instead of a Linux swap partition, and it limits the
       injected host name to less than 16 characters.
     - ``linux`` or ``windows``.

   * - libvirt API driver
     - ``hw_scsi_model``
     - Enables the use of VirtIO SCSI (``virtio-scsi``) to provide block
       device access for compute instances; by default, instances use VirtIO
       Block (``virtio-blk``). VirtIO SCSI is a para-virtualized SCSI
       controller device that provides improved scalability and performance,
       and supports advanced SCSI hardware.
     - ``virtio-scsi``
   * - libvirt API driver
     - ``hw_serial_port_count``
     - Specifies the count of serial ports that should be provided. If
       ``hw:serial_port_count`` is not set in the flavor's extra_specs, then
       any count is permitted. If ``hw:serial_port_count`` is set, then this
       provides the default serial port count. It is permitted to override the
       default serial port count, but only with a lower value.
     - Integer
   * - libvirt API driver
     - ``hw_video_model``
     - The graphic device model presented to the guest.
       hw_video_model=none disables the graphics device in the guest and should
       generally be used when using gpu passthrough.
     - ``vga``, ``cirrus``, ``vmvga``, ``xen``, ``qxl``, ``virtio``, ``gop`` or ``none``.
   * - libvirt API driver
     - ``hw_video_ram``
     - Maximum RAM for the video image. Used only if a ``hw_video:ram_max_mb``
       value has been set in the flavor's extra_specs and that value is higher
       than the value set in ``hw_video_ram``.
     - Integer in MB (for example, ``64``).
   * - libvirt API driver
     - ``hw_watchdog_action``
     - Enables a virtual hardware watchdog device that carries out the
       specified action if the server hangs. The watchdog uses the
       ``i6300esb`` device (emulating a PCI Intel 6300ESB). If
       ``hw_watchdog_action`` is not specified, the watchdog is disabled.
     - * ``disabled`` - (default) The device is not attached. Allows the user to
         disable the watchdog for the image, even if it has been enabled using
         the image's flavor.
       * ``reset`` - Forcefully reset the guest.
       * ``poweroff`` - Forcefully power off the guest.
       * ``pause`` - Pause the guest.
       * ``none`` - Only enable the watchdog; do nothing if the server hangs.
   * - libvirt API driver
     - ``os_command_line``
     - The kernel command line to be used by the ``libvirt`` driver, instead
       of the default. For Linux Containers (LXC), the value is used as
       arguments for initialization. This key is valid only for Amazon kernel,
       ``ramdisk``, or machine images (``aki``, ``ari``, or ``ami``).
     -
   * - libvirt API driver and VMware API driver
     - ``hw_vif_model``
     - Specifies the model of virtual network interface device to use.
     - The valid options depend on the configured hypervisor.
        * ``KVM`` and ``QEMU``: ``e1000``, ``ne2k_pci``, ``pcnet``,
          ``rtl8139``, and ``virtio``.
        * VMware: ``e1000``, ``e1000e``, ``VirtualE1000``, ``VirtualE1000e``,
          ``VirtualPCNet32``, ``VirtualSriovEthernetCard``, and
          ``VirtualVmxnet``.
        * Xen: ``e1000``, ``netfront``, ``ne2k_pci``, ``pcnet``, and
          ``rtl8139``.
   * - libvirt API driver
     - ``hw_vif_multiqueue_enabled``
     - If ``true``, this enables the ``virtio-net multiqueue`` feature. In
       this case, the driver sets the number of queues equal to the number
       of guest vCPUs. This makes the network performance scale across a
       number of vCPUs.
     - ``true`` | ``false``
   * - libvirt API driver
     - ``hw_boot_menu``
     - If ``true``, enables the BIOS bootmenu. In cases where both the image
       metadata and Extra Spec are set, the Extra Spec setting is used. This
       allows for flexibility in setting/overriding the default behavior as
       needed.
     - ``true`` or ``false``
   * - libvirt API driver
     - ``hw_pmu``
     - Controls emulation of a virtual performance monitoring unit (vPMU) in the guest.
       To reduce latency in realtime workloads disable the vPMU by setting hw_pmu=false.
     - ``true`` or ``false``
   * - libvirt API driver
     - ``img_hide_hypervisor_id``
     - Some hypervisors add a signature to their guests.  While the presence
       of the signature can enable some paravirtualization features on the
       guest, it can also have the effect of preventing some drivers from
       loading.  Hiding the signature by setting this property to ``true``
       may allow such drivers to load and work.
     - ``true`` or ``false``
   * - VMware API driver
     - ``vmware_adaptertype``
     - The virtual SCSI or IDE controller used by the hypervisor.
     - ``lsiLogic``, ``lsiLogicsas``, ``busLogic``, ``ide``, or
       ``paraVirtual``.
   * - VMware API driver
     - ``vmware_ostype``
     - A VMware GuestID which describes the operating system installed in
       the image. This value is passed to the hypervisor when creating a
       virtual machine. If not specified, the key defaults to ``otherGuest``.
     - See `thinkvirt.com <http://www.thinkvirt.com/?q=node/181>`_.
   * - VMware API driver
     - ``vmware_image_version``
     - Currently unused.
     - ``1``
   * - XenAPI driver
     - ``auto_disk_config``
     - If ``true``, the root partition on the disk is automatically resized
       before the instance boots. This value is only taken into account by
       the Compute service when using a Xen-based hypervisor with the
       ``XenAPI`` driver. The Compute service will only attempt to resize if
       there is a single partition on the image, and only if the partition
       is in ``ext3`` or ``ext4`` format.
     - ``true`` or ``false``
