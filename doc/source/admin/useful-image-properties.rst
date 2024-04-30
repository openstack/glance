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

* Image properties can be used to provide additional information to Ironic
  (even when Nova is not used)

Using image properties
----------------------

Some important points to keep in mind:

* The ``glance-api.conf`` setting ``image_property_quota`` should be
  sufficiently high to allow any additional desired properties.  (The default
  is 128.)

* You can use Glance *property protections* to control access to specific
  image properties, should that be desirable.  See the
  :ref:`property-protections` section of this Guide for more information.

* Glance reserves properties namespaced with the ``os_glance`` prefix
  for its own use and will refuse attempts by API users to set or
  change them.

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
------------------------------

Here is a list of useful image properties and the values they expect.

``architecture``
  :Type: str

  The CPU architecture that must be supported by the hypervisor. For
  example, ``x86_64``, ``arm``, or ``ppc64``. Run :command:`uname -m`
  to get the architecture of a machine. We strongly recommend using
  the architecture data vocabulary defined by the `libosinfo project
  <http://libosinfo.org/>`_ for this purpose.

  One of:

  * ``aarch64`` - `ARM 64-bit <https://en.wikipedia.org/wiki/AArch64>`_
  * ``alpha`` - `DEC 64-bit RISC <https://en.wikipedia.org/wiki/DEC_Alpha>`_
  * ``armv7l`` - `ARM Cortex-A7 MPCore <https://en.wikipedia.org/wiki/ARM_architecture>`_
  * ``cris`` - `Ethernet, Token Ring, AXis—Code Reduced Instruction Set <https://en.wikipedia.org/wiki/ETRAX_CRIS>`_
  * ``i686`` - `Intel sixth-generation x86 (P6 micro architecture) <https://en.wikipedia.org/wiki/X86>`_
  * ``ia64`` - `Itanium <https://en.wikipedia.org/wiki/Itanium>`_
  * ``lm32`` - `Lattice Micro32 <https://en.wikipedia.org/wiki/Milkymist>`_
  * ``m68k`` - `Motorola 68000 <https://en.wikipedia.org/wiki/Motorola_68000_family>`_
  * ``microblaze`` - `Xilinx 32-bit FPGA (Big Endian) <https://en.wikipedia.org/wiki/MicroBlaze>`_
  * ``microblazeel`` - `Xilinx 32-bit FPGA (Little Endian) <https://en.wikipedia.org/wiki/MicroBlaze>`_
  * ``mips`` - `MIPS 32-bit RISC (Big Endian) <https://en.wikipedia.org/wiki/MIPS_architecture>`_
  * ``mipsel`` - `MIPS 32-bit RISC (Little Endian) <https://en.wikipedia.org/wiki/MIPS_architecture>`_
  * ``mips64`` - `MIPS 64-bit RISC (Big Endian) <https://en.wikipedia.org/wiki/MIPS_architecture>`_
  * ``mips64el`` - `MIPS 64-bit RISC (Little Endian) <https://en.wikipedia.org/wiki/MIPS_architecture>`_
  * ``openrisc`` - `OpenCores RISC <https://en.wikipedia.org/wiki/OpenRISC#QEMU_support>`_
  * ``parisc`` - `HP Precision Architecture RISC <https://en.wikipedia.org/wiki/PA-RISC>`_
  * ``parisc64`` - `HP Precision Architecture 64-bit RISC <https://en.wikipedia.org/wiki/PA-RISC>`_
  * ``ppc`` - `PowerPC 32-bit <https://en.wikipedia.org/wiki/PowerPC>`_
  * ``ppc64`` - `PowerPC 64-bit <https://en.wikipedia.org/wiki/PowerPC>`_
  * ``ppcemb`` - `PowerPC (Embedded 32-bit) <https://en.wikipedia.org/wiki/PowerPC>`_
  * ``s390`` - `IBM Enterprise Systems Architecture/390 <https://en.wikipedia.org/wiki/S390>`_
  * ``s390x`` - `S/390 64-bit <https://en.wikipedia.org/wiki/S390x>`_
  * ``sh4`` - `SuperH SH-4 (Little Endian) <https://en.wikipedia.org/wiki/SuperH>`_
  * ``sh4eb`` - `SuperH SH-4 (Big Endian) <https://en.wikipedia.org/wiki/SuperH>`_
  * ``sparc`` - `Scalable Processor Architecture, 32-bit <https://en.wikipedia.org/wiki/Sparc>`_
  * ``sparc64`` - `Scalable Processor Architecture, 64-bit <https://en.wikipedia.org/wiki/Sparc>`_
  * ``unicore32`` - `Microprocessor Research and Development Center RISC Unicore32 <https://en.wikipedia.org/wiki/Unicore>`_
  * ``x86_64`` - `64-bit extension of IA-32 <https://en.wikipedia.org/wiki/X86>`_
  * ``xtensa`` - `Tensilica Xtensa configurable microprocessor core <https://en.wikipedia.org/wiki/Xtensa#Processor_Cores>`_
  * ``xtensaeb`` - `Tensilica Xtensa configurable microprocessor core <https://en.wikipedia.org/wiki/Xtensa#Processor_Cores>`_ (Big Endian)

``hypervisor_type``
  :Type: str

  The hypervisor type. Note that ``qemu`` is used for both QEMU and KVM
  hypervisor types.

  One of:

  - ``hyperv``
  - ``ironic``
  - ``lxc``
  - ``qemu``
  - ``uml``
  - ``vmware``
  - ``xen``

``instance_uuid``
  :Type: str

  For snapshot images, this is the UUID of the server used to create this
  image. The value must be a valid server UUID.

``img_config_drive``
  :Type: str

  Specifies whether the image needs a config drive.

  One of:

  - ``mandatory``
  - ``optional`` (default if property is not used)

``img_type``
  :Type: str

  Specifies the partitioning type of the image. The default value is
  ``partition`` if the ``kernel_id``/``ramdisk_id`` properties are present,
  otherwise ``whole-disk``.

  One of:

  - ``whole-disk`` - an image with a partition table embedded.
  - ``partition`` - an image with only the root partition without a partition
    table.

  .. note::
     This property is currently only recognized by Ironic.

``kernel_id``
  :Type: str

  The ID of an image stored in the Image service that should be used as
  the kernel when booting an AMI-style image. The value must be a valid image
  ID

``os_admin_user``
  :Type: str

  The name of the user with admin privileges.
  The value must be a valid username (defaults to ``root`` for Linux guests and
  ``Administrator`` for Windows guests).

``os_distro``
  :Type: str

  The common name of the operating system distribution in lowercase
  (uses the same data vocabulary as the `libosinfo project`_). Specify only a
  recognized value for this field. Deprecated values are listed to assist you
  in searching for the recognized value.

  One of:

  * ``arch`` - Arch Linux. Do not use ``archlinux`` or ``org.archlinux``.
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
  * ``rocky`` - Rocky Linux. Do not use ``Rocky`` or ``rockylinux``.
  * ``rhel`` - Red Hat Enterprise Linux. Do not use ``redhat``, ``RedHat``,
    or ``com.redhat``.
  * ``sled`` - SUSE Linux Enterprise Desktop. Do not use ``com.suse``.
  * ``ubuntu`` - Ubuntu. Do not use ``Ubuntu``, ``com.ubuntu``,
    ``org.ubuntu``, or ``canonical``.
  * ``windows`` - Microsoft Windows. Do not use ``com.microsoft.server``
    or ``windoze``.

``os_version``
  :Type: str

  The operating system version as specified by the distributor.

  The value must be a valid version number (for example, ``11.10``).

``os_secure_boot``
  :Type: str

  Secure Boot is a security standard. When the instance starts,
  Secure Boot first examines software such as firmware and OS by their
  signature and only allows them to run if the signatures are valid.

  For Hyper-V: Images must be prepared as Generation 2 VMs. Instance must
  also contain ``hw_machine_type=hyperv-gen2`` image property. Linux
  guests will also require bootloader's digital signature provided as
  ``os_secure_boot_signature`` and
  ``hypervisor_version_requires'>=10.0'`` image properties.

  One of:

  * ``required`` - Enable the Secure Boot feature.
  * ``disabled`` or ``optional`` - (default if property not used) Disable the
    Secure Boot feature.

``os_shutdown_timeout``
  :Type: int

  By default, guests will be given 60 seconds to perform a graceful
  shutdown. After that, the VM is powered off. This property allows
  overriding the amount of time (unit: seconds) to allow a guest OS to
  cleanly shut down before power off. A value of 0 (zero) means the guest
  will be powered off immediately with no opportunity for guest OS
  clean-up.

``ramdisk_id``
  The ID of image stored in the Image service that should be used as the
  ramdisk when booting an AMI-style image.

  The value must be a valid image ID.

``rootfs_uuid``
  For whole-disk images (see ``img_type`` above), the UUID of the root
  partition.

  This property is used by Ironic when configuring software RAID.

``trait:<trait_name>``
  :Type: str

  Added in the Rocky release. Functionality is similar to traits specified
  in `flavor extra specs <https://docs.openstack.org/nova/latest/user/flavors.html#extra-specs>`_.

  Traits allow specifying a server to build on a compute node with the set
  of traits specified in the image. The traits are associated with the
  resource provider that represents the compute node in the Placement API.

  The syntax of specifying traits is **trait:<trait_name>=value**, for
  example:

  * ``trait:HW_CPU_X86_AVX2=required``
  * ``trait:STORAGE_DISK_SSD=required``

  The nova scheduler will pass required traits specified on the image to
  the Placement API to include only resource providers that can satisfy
  the required traits. Traits for the resource providers can be managed
  using the `osc-placement plugin. <https://docs.openstack.org/osc-placement/latest/index.html>`_

  Image traits are used by the nova scheduler even in cases of volume
  backed instances, if the volume source is an image with traits.

  The only valid value is ``required``. Any other value is invalid.

  One of:

  * ``required`` - <trait_name> is required on the resource provider that
    represents the compute node on which the image is launched.

``vm_mode``
  :Type: str

  The virtual machine mode. This represents the host/guest ABI
  (application binary interface) used for the virtual machine.

  One of:

  * ``hvm`` - Fully virtualized. This is the mode used by QEMU and KVM.
  * ``xen`` - Xen 3.0 paravirtualized.
  * ``uml`` - User Mode Linux paravirtualized.
  * ``exe`` - Executables in containers. This is the mode used by LXC.

``hw_cpu_sockets``
  :Type: int

  The preferred number of sockets to expose to the guest.

  Only supported by the libvirt driver.

``hw_cpu_cores``
  :Type: int

  The preferred number of cores to expose to the guest.

  Only supported by the libvirt driver.

``hw_cpu_threads``
  :Type: int

  The preferred number of threads to expose to the guest.

  Only supported by the libvirt driver.

``hw_cpu_policy``
  :Type: str

  Used to pin the virtual CPUs (vCPUs) of instances to the host’s
  physical CPU cores (pCPUs). Host aggregates should be used to separate
  these pinned instances from unpinned instances as the latter will not
  respect the resourcing requirements of the former.

  Only supported by the libvirt driver.

  One of:

  * ``shared`` - (default if property not specified) The guest vCPUs will be
    allowed to freely float across host pCPUs, albeit potentially constrained
    by NUMA policy.
  * ``dedicated`` - The guest vCPUs will be strictly pinned to a set of
    host pCPUs. In the absence of an explicit vCPU topology request, the
    drivers typically expose all vCPUs as sockets with one core and one
    thread. When strict CPU pinning is in effect the guest CPU topology
    will be setup to match the topology of the CPUs to which it is pinned.
    This option implies an overcommit ratio of 1.0. For example, if a two
    vCPU guest is pinned to a single host core with two threads, then the
    guest will get a topology of one socket, one core, two threads.

``hw_cpu_thread_policy``
  :Type: str

  Further refine ``hw_cpu_policy=dedicated`` by stating how hardware CPU
  threads in a simultaneous multithreading-based (SMT) architecture be
  used. SMT-based architectures include Intel processors with
  Hyper-Threading technology. In these architectures, processor cores
  share a number of components with one or more other cores. Cores in
  such architectures are commonly referred to as hardware threads, while
  the cores that a given core share components with are known as thread
  siblings.

  Only supported by the libvirt driver.

  One of:

  * ``prefer`` - (default if property not specified) The host may or may not
    have an SMT architecture. Where an SMT architecture is present, thread
    siblings are preferred.
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

``hw_cdrom_bus``
  :Type: str

  Specifies the type of disk controller to attach CD-ROM devices to.
  As for ``hw_disk_bus``.

  Only supported by the libvirt driver.

``hw_disk_bus``
  :Type: str

  Specifies the type of disk controller to attach disk devices to.

  Only supported by the libvirt driver.

  Options depend on the value of `nova's virt_type config option
  <https://docs.openstack.org/nova/latest/configuration/config.html#libvirt.virt_type>`_:

  * For ``qemu`` and ``kvm``: one of ``scsi``, ``virtio``,
    ``uml``, ``xen``, ``ide``, ``usb``, or ``lxc``.
  * For ``xen``: one of ``xen`` or ``ide``.
  * For ``uml``: must be ``uml``.
  * For ``lxc``: must be ``lxc``.
  * For ``parallels``: one of ``ide`` or ``scsi``.

``hw_firmware_type``
  Specifies the type of firmware with which to boot the guest.

  Only supported by the libvirt driver.

  One of:

  * ``bios``
  * ``uefi``

``hw_mem_encryption``
  :Type: bool

  Enables encryption of guest memory at the hardware level, if
  there are compute hosts available which support this. See
  `nova's documentation on configuration of the KVM hypervisor
  <https://docs.openstack.org/nova/latest/admin/configuration/hypervisor-kvm.html#amd-sev-secure-encrypted-virtualization>`_
  for more details.

  Only supported by the libvirt driver.

``hw_virtio_packed_ring``
  :Type: bool

  Enables Packed VIRT-IO Queue feature. When set to true, instance will be
  scheduled to hosts that support negotiating the packed virt queue format.
  This feature may or may not be enabled depending on the guest driver.
  When used it will improve the small packet performance of network io.
  Only supported by the libvirt driver.

``hw_pointer_model``
  :Type: str

  Input devices that allow interaction with a graphical framebuffer,
  for example to provide a graphic tablet for absolute cursor movement.
  Currently only supported by the KVM/QEMU hypervisor configuration
  and VNC or SPICE consoles must be enabled.

  Only supported by the libvirt driver.

  One of:

  - ``usbtablet``

``hw_rng_model``
  :Type: str

  Adds a random-number generator device to the image's instances. This
  image property by itself does not guarantee that a hardware RNG will be
  used; it expresses a preference that may or may not be satisfied
  depending upon Nova configuration.

  The cloud administrator can enable and control device behavior by
  configuring the instance's flavor. By default:

  * The generator device is disabled.
  * ``/dev/urandom`` is used as the default entropy source. To
    specify a physical hardwre RNG device, use the following option in
    the ``nova.conf`` file:

    .. code-block:: ini

       rng_dev_path=/dev/hwrng

  * The use of a hardware random number generator must be configured in a
    flavor's extra_specs by setting ``hw_rng:allowed`` to True in the
    flavor definition.

  Only supported by the libvirt driver.

  One of:

  - ``virtio``
  - Other supported device.

``hw_time_hpet``
  :Type: bool

  Adds support for the High Precision Event Timer (HPET) for x86 guests
  in the libvirt driver when ``hypervisor_type=qemu`` and
  ``architecture=i686`` or ``architecture=x86_64``. The timer can be
  enabled by setting ``hw_time_hpet=true``. By default HPET remains
  disabled.

  Only supported by the libvirt driver.

``hw_machine_type``
  :Type: str

  For libvirt: Enables booting an ARM system using the specified
  machine type. If an ARM image is used and its machine type is
  not explicitly specified, then Compute uses the ``virt`` machine
  type as the default for ARMv7 and AArch64.

  For Hyper-V: Specifies whether the Hyper-V instance will be a generation
  1 or generation 2 VM. By default, if the property is not provided, the
  instances will be generation 1 VMs. If the image is specific for
  generation 2 VMs but the property is not provided accordingly, the
  instance will fail to boot.

  For libvirt: Valid types can be viewed by using the
  :command:`virsh capabilities` command (machine types are displayed in
  the ``machine`` tag).

  For hyper-V: Acceptable values are either ``hyperv-gen1`` or
  ``hyperv-gen2``.

  Only supported by the libvirt and Hyper-V drivers.

``os_type``
  :Type: str

  The operating system installed on the image. The ``libvirt`` API driver
  contains logic that takes different actions
  depending on the value of the ``os_type`` parameter of the image.
  For example, for ``os_type=windows`` images, it creates a FAT32-based
  swap partition instead of a Linux swap partition, and it limits the
  injected host name to less than 16 characters.

  Only supported by the libvirt driver.

  One of:

  * ``linux``
  * ``windows``

``hw_scsi_model``
  :Type: str

  Enables the use of VirtIO SCSI (``virtio-scsi``) to provide block
  device access for compute instances; by default, instances use VirtIO
  Block (``virtio-blk``). VirtIO SCSI is a para-virtualized SCSI
  controller device that provides improved scalability and performance,
  and supports advanced SCSI hardware.

  Only supported by the libvirt driver.

  One of:

  * ``virtio-scsi``

``hw_serial_port_count``
  :Type: int

  Specifies the count of serial ports that should be provided. If
  ``hw:serial_port_count`` is not set in the flavor's extra_specs, then
  any count is permitted. If ``hw:serial_port_count`` is set, then this
  provides the default serial port count. It is permitted to override the
  default serial port count, but only with a lower value.

  Only supported by the libvirt driver.

``hw_video_model``
  :Type: str

  The graphic device model presented to the guest. ``none`` disables the
  graphics device in the guest and should generally be used when using GPU
  passthrough.

  One of:

  * ``vga``
  * ``cirrus``
  * ``vmvga``
  * ``xen``
  * ``qxl``
  * ``virtio``
  * ``gop``
  * ``none``
  * ``bochs``

  Only supported by the libvirt driver.

``hw_video_ram``
  :Type: int

  Maximum RAM in MB for the video image. Used only if a ``hw_video:ram_max_mb``
  value has been set in the flavor's extra_specs and that value is higher
  than the value set in ``hw_video_ram``.

  Only supported by the libvirt driver.

``hw_watchdog_action``
  :Type: str

  Enables a virtual hardware watchdog device that carries out the
  specified action if the server hangs. The watchdog uses the
  ``i6300esb`` device (emulating a PCI Intel 6300ESB). If
  ``hw_watchdog_action`` is not specified, the watchdog is disabled.

  Only supported by the libvirt driver.

  One of:

  * ``disabled`` - (default) The device is not attached. Allows the user to
    disable the watchdog for the image, even if it has been enabled using
    the image's flavor.
  * ``reset`` - Forcefully reset the guest.
  * ``poweroff`` - Forcefully power off the guest.
  * ``pause`` - Pause the guest.
  * ``none`` - Only enable the watchdog; do nothing if the server hangs.

``os_command_line``
  :Type: str

  The kernel command line to be used by the ``libvirt`` driver, instead
  of the default. For Linux Containers (LXC), the value is used as
  arguments for initialization. This key is valid only for Amazon kernel,
  ``ramdisk``, or machine images (``aki``, ``ari``, or ``ami``).

  Only supported by the libvirt driver.

``hw_vif_model``
  :Type: str

  Specifies the model of virtual network interface device to use.

  Only supported by the libvirt driver and VMware API drivers.

  The valid options depend on the configured hypervisor.

  * ``KVM`` and ``QEMU``: ``e1000``, ``e1000e``, ``ne2k_pci``, ``pcnet``,
    ``rtl8139``, ``virtio`` and ``vmxnet3``.
  * VMware: ``e1000``, ``e1000e``, ``VirtualE1000``, ``VirtualE1000e``,
    ``VirtualPCNet32``, ``VirtualVmxnet`` and ``VirtualVmxnet3``.
  * Xen: ``e1000``, ``netfront``, ``ne2k_pci``, ``pcnet``, and
    ``rtl8139``.

``hw_vif_multiqueue_enabled``
  :Type: bool

  If ``true``, this enables the ``virtio-net multiqueue`` feature. In
  this case, the driver sets the number of queues equal to the number
  of guest vCPUs. This makes the network performance scale across a
  number of vCPUs.

  Only supported by the libvirt driver.

``hw_boot_menu``
  :Type: bool

  If ``true``, enables the BIOS bootmenu. In cases where both the image
  metadata and Extra Spec are set, the Extra Spec setting is used. This
  allows for flexibility in setting/overriding the default behavior as
  needed.

  Only supported by the libvirt driver.

``hw_pmu``
  :Type: bool

  Controls emulation of a virtual performance monitoring unit (vPMU) in the
  guest.  To reduce latency in realtime workloads disable the vPMU by setting
  ``hw_pmu=false``.

  Only supported by the libvirt driver.

``img_hide_hypervisor_id``
  :Type: bool

  Some hypervisors add a signature to their guests.  While the presence
  of the signature can enable some paravirtualization features on the
  guest, it can also have the effect of preventing some drivers from
  loading.  Hiding the signature by setting this property to ``true``
  may allow such drivers to load and work.

  Only supported by the libvirt driver.

``vmware_adaptertype``
  :Type: str

  The virtual SCSI or IDE controller used by the hypervisor.

  Only supported by the VMWare API driver.

  One of:

  * ``lsiLogic``
  * ``lsiLogicsas``
  * ``busLogic``
  * ``ide``
  * ``paraVirtual``

``vmware_ostype``
  A VMware GuestID which describes the operating system installed in
  the image. This value is passed to the hypervisor when creating a
  virtual machine. If not specified, the key defaults to ``otherGuest``.
  See `thinkvirt.com <http://www.thinkvirt.com/?q=node/181>`_ for supported
  values.

  Only supported by the VMWare API driver.

``vmware_image_version``
  :Type: int

  Currently unused.

``instance_type_rxtx_factor``
  :Type: float

  Deprecated and currently unused.

``auto_disk_config``
  :Type: bool

  Deprecated and currently unused.
