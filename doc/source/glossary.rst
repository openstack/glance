========
Glossary
========

0-9
~~~

.. glossary::

   6to4

      A mechanism that allows IPv6 packets to be transmitted
      over an IPv4 network, providing a strategy for migrating to
      IPv6.

A
~

.. glossary::

   absolute limit

      Impassable limits for guest VMs. Settings include total RAM
      size, maximum number of vCPUs, and maximum disk size.

   access control list (ACL)

      A list of permissions attached to an object. An ACL specifies
      which users or system processes have access to objects. It also
      defines which operations can be performed on specified objects. Each
      entry in a typical ACL specifies a subject and an operation. For
      instance, the ACL entry ``(Alice, delete)`` for a file gives
      Alice permission to delete the file.

   access key

      Alternative term for an Amazon EC2 access key. See EC2 access
      key.

   account

      The Object Storage context of an account. Do not confuse with a
      user account from an authentication service, such as Active Directory,
      /etc/passwd, OpenLDAP, OpenStack Identity, and so on.

   account auditor

      Checks for missing replicas and incorrect or corrupted objects
      in a specified Object Storage account by running queries against the
      back-end SQLite database.

   account database

      A SQLite database that contains Object Storage accounts and
      related metadata and that the accounts server accesses.

   account reaper

      An Object Storage worker that scans for and deletes account
      databases and that the account server has marked for deletion.

   account server

      Lists containers in Object Storage and stores container
      information in the account database.

   account service

      An Object Storage component that provides account services such
      as list, create, modify, and audit. Do not confuse with OpenStack
      Identity service, OpenLDAP, or similar user-account services.

   accounting

      The Compute service provides accounting information through the
      event notification and system usage data facilities.

   Active Directory

      Authentication and identity service by Microsoft, based on LDAP.
      Supported in OpenStack.

   active/active configuration

      In a high-availability setup with an active/active
      configuration, several systems share the load together and if one
      fails, the load is distributed to the remaining systems.

   active/passive configuration

      In a high-availability setup with an active/passive
      configuration, systems are set up to bring additional resources online
      to replace those that have failed.

   address pool

      A group of fixed and/or floating IP addresses that are assigned
      to a project and can be used by or assigned to the VM instances in a
      project.

   Address Resolution Protocol (ARP)

      The protocol by which layer-3 IP addresses are resolved into
      layer-2 link local addresses.

   admin API

      A subset of API calls that are accessible to authorized
      administrators and are generally not accessible to end users or the
      public Internet. They can exist as a separate service (keystone) or
      can be a subset of another API (nova).

   admin server

      In the context of the Identity service, the worker process that
      provides access to the admin API.

   administrator

      The person responsible for installing, configuring,
      and managing an OpenStack cloud.

   Advanced Message Queuing Protocol (AMQP)

      The open standard messaging protocol used by OpenStack
      components for intra-service communications, provided by RabbitMQ,
      Qpid, or ZeroMQ.

   Advanced RISC Machine (ARM)

      Lower power consumption CPU often found in mobile and embedded
      devices. Supported by OpenStack.

   alert

      The Compute service can send alerts through its notification
      system, which includes a facility to create custom notification
      drivers. Alerts can be sent to and displayed on the dashboard.

   allocate

      The process of taking a floating IP address from the address
      pool so it can be associated with a fixed IP on a guest VM
      instance.

   Amazon Kernel Image (AKI)

      Both a VM container format and disk format. Supported by Image
      service.

   Amazon Machine Image (AMI)

      Both a VM container format and disk format. Supported by Image
      service.

   Amazon Ramdisk Image (ARI)

      Both a VM container format and disk format. Supported by Image
      service.

   Anvil

      A project that ports the shell script-based project named
      DevStack to Python.

   aodh

      Part of the OpenStack :term:`Telemetry service <Telemetry
      service (telemetry)>`; provides alarming functionality.

   Apache

      The Apache Software Foundation supports the Apache community of
      open-source software projects. These projects provide software
      products for the public good.

   Apache License 2.0

      All OpenStack core projects are provided under the terms of the
      Apache License 2.0 license.

   Apache Web Server

      The most common web server software currently used on the
      Internet.

   API endpoint

      The daemon, worker, or service that a client communicates with
      to access an API. API endpoints can provide any number of services,
      such as authentication, sales data, performance meters, Compute VM
      commands, census data, and so on.

   API extension

      Custom modules that extend some OpenStack core APIs.

   API extension plug-in

      Alternative term for a Networking plug-in or Networking API
      extension.

   API key

      Alternative term for an API token.

   API server

      Any node running a daemon or worker that provides an API
      endpoint.

   API token

      Passed to API requests and used by OpenStack to verify that the
      client is authorized to run the requested operation.

   API version

      In OpenStack, the API version for a project is part of the URL.
      For example, ``example.com/nova/v1/foobar``.

   applet

      A Java program that can be embedded into a web page.

   Application Catalog service (murano)

      The project that provides an application catalog service so that users
      can compose and deploy composite environments on an application
      abstraction level while managing the application lifecycle.

   Application Programming Interface (API)

      A collection of specifications used to access a service,
      application, or program. Includes service calls, required parameters
      for each call, and the expected return values.

   application server

      A piece of software that makes available another piece of
      software over a network.

   Application Service Provider (ASP)

      Companies that rent specialized applications that help
      businesses and organizations provide additional services
      with lower cost.

   arptables

      Tool used for maintaining Address Resolution Protocol packet
      filter rules in the Linux kernel firewall modules. Used along with
      iptables, ebtables, and ip6tables in Compute to provide firewall
      services for VMs.

   associate

      The process associating a Compute floating IP address with a
      fixed IP address.

   Asynchronous JavaScript and XML (AJAX)

      A group of interrelated web development techniques used on the
      client-side to create asynchronous web applications. Used extensively
      in horizon.

   ATA over Ethernet (AoE)

      A disk storage protocol tunneled within Ethernet.

   attach

      The process of connecting a VIF or vNIC to a L2 network in
      Networking. In the context of Compute, this process connects a storage
      volume to an instance.

   attachment (network)

      Association of an interface ID to a logical port. Plugs an
      interface into a port.

   auditing

      Provided in Compute through the system usage data
      facility.

   auditor

      A worker process that verifies the integrity of Object Storage
      objects, containers, and accounts. Auditors is the collective term for
      the Object Storage account auditor, container auditor, and object
      auditor.

   Austin

      The code name for the initial release of
      OpenStack. The first design summit took place in
      Austin, Texas, US.

   auth node

      Alternative term for an Object Storage authorization
      node.

   authentication

      The process that confirms that the user, process, or client is
      really who they say they are through private key, secret token,
      password, fingerprint, or similar method.

   authentication token

      A string of text provided to the client after authentication.
      Must be provided by the user or process in subsequent requests to the
      API endpoint.

   AuthN

      The Identity service component that provides authentication
      services.

   authorization

      The act of verifying that a user, process, or client is
      authorized to perform an action.

   authorization node

      An Object Storage node that provides authorization
      services.

   AuthZ

      The Identity component that provides high-level
      authorization services.

   Auto ACK

      Configuration setting within RabbitMQ that enables or disables
      message acknowledgment. Enabled by default.

   auto declare

      A Compute RabbitMQ setting that determines whether a message
      exchange is automatically created when the program starts.

   availability zone

      An Amazon EC2 concept of an isolated area that is used for fault
      tolerance. Do not confuse with an OpenStack Compute zone or
      cell.

   AWS CloudFormation template

      AWS CloudFormation allows Amazon Web Services (AWS) users to create and manage a
      collection of related resources. The Orchestration service
      supports a CloudFormation-compatible format (CFN).

B
~

.. glossary::

   back end

      Interactions and processes that are obfuscated from the user,
      such as Compute volume mount, data transmission to an iSCSI target by
      a daemon, or Object Storage object integrity checks.

   back-end catalog

      The storage method used by the Identity service catalog service
      to store and retrieve information about API endpoints that are
      available to the client. Examples include an SQL database, LDAP
      database, or KVS back end.

   back-end store

      The persistent data store used to save and retrieve information
      for a service, such as lists of Object Storage objects, current state
      of guest VMs, lists of user names, and so on. Also, the method that the
      Image service uses to get and store VM images. Options include Object
      Storage, locally mounted file system, RADOS block devices, VMware
      datastore, and HTTP.

   Backup, Restore, and Disaster Recovery service (freezer)

      The project that provides integrated tooling for backing up, restoring,
      and recovering file systems, instances, or database backups.

   bandwidth

      The amount of available data used by communication resources,
      such as the Internet. Represents the amount of data that is used to
      download things or the amount of data available to download.

   barbican

      Code name of the :term:`Key Manager service
      <Key Manager service (barbican)>`.

   bare

      An Image service container format that indicates that no
      container exists for the VM image.

   Bare Metal service (ironic)

      The OpenStack service that provides a service and associated libraries
      capable of managing and provisioning physical machines in a
      security-aware and fault-tolerant manner.

   base image

      An OpenStack-provided image.

   Bell-LaPadula model

      A security model that focuses on data confidentiality
      and controlled access to classified information.
      This model divides the entities into subjects and objects.
      The clearance of a subject is compared to the classification of the
      object to determine if the subject is authorized for the specific access mode.
      The clearance or classification scheme is expressed in terms of a lattice.

   Benchmark service (rally)

      OpenStack project that provides a framework for
      performance analysis and benchmarking of individual
      OpenStack components as well as full production OpenStack
      cloud deployments.

   Bexar

      A grouped release of projects related to
      OpenStack that came out in February of 2011. It
      included only Compute (nova) and Object Storage (swift).
      Bexar is the code name for the second release of
      OpenStack. The design summit took place in
      San Antonio, Texas, US, which is the county seat for Bexar county.

   binary

      Information that consists solely of ones and zeroes, which is
      the language of computers.

   bit

      A bit is a single digit number that is in base of 2 (either a
      zero or one). Bandwidth usage is measured in bits per second.

   bits per second (BPS)

      The universal measurement of how quickly data is transferred
      from place to place.

   block device

      A device that moves data in the form of blocks. These device
      nodes interface the devices, such as hard disks, CD-ROM drives, flash
      drives, and other addressable regions of memory.

   block migration

      A method of VM live migration used by KVM to evacuate instances
      from one host to another with very little downtime during a
      user-initiated switchover. Does not require shared storage. Supported
      by Compute.

   Block Storage API

      An API on a separate endpoint for attaching,
      detaching, and creating block storage for compute
      VMs.

   Block Storage service (cinder)

      The OpenStack service that implement services and libraries to provide
      on-demand, self-service access to Block Storage resources via abstraction
      and automation on top of other block storage devices.

   BMC (Baseboard Management Controller)

      The intelligence in the IPMI architecture, which is a specialized
      micro-controller that is embedded on the motherboard of a computer
      and acts as a server. Manages the interface between system management
      software and platform hardware.

   bootable disk image

      A type of VM image that exists as a single, bootable
      file.

   Bootstrap Protocol (BOOTP)

      A network protocol used by a network client to obtain an IP
      address from a configuration server. Provided in Compute through the
      dnsmasq daemon when using either the FlatDHCP manager or VLAN manager
      network manager.

   Border Gateway Protocol (BGP)

      The Border Gateway Protocol is a dynamic routing protocol
      that connects autonomous systems.  Considered the
      backbone of the Internet, this protocol connects disparate
      networks to form a larger network.

   browser

      Any client software that enables a computer or device to access
      the Internet.

   builder file

      Contains configuration information that Object Storage uses to
      reconfigure a ring or to re-create it from scratch after a serious
      failure.

   bursting

      The practice of utilizing a secondary environment to
      elastically build instances on-demand when the primary
      environment is resource constrained.

   button class

      A group of related button types within horizon. Buttons to
      start, stop, and suspend VMs are in one class. Buttons to associate
      and disassociate floating IP addresses are in another class, and so
      on.

   byte

      Set of bits that make up a single character; there are usually 8
      bits to a byte.

C
~

.. glossary::

   cache pruner

      A program that keeps the Image service VM image cache at or
      below its configured maximum size.

   Cactus

      An OpenStack grouped release of projects that came out in the
      spring of 2011. It included Compute (nova), Object Storage (swift),
      and the Image service (glance).
      Cactus is a city in Texas, US and is the code name for
      the third release of OpenStack. When OpenStack releases went
      from three to six months long, the code name of the release
      changed to match a geography nearest the previous
      summit.

   CALL

      One of the RPC primitives used by the OpenStack message queue
      software. Sends a message and waits for a response.

   capability

      Defines resources for a cell, including CPU, storage, and
      networking. Can apply to the specific services within a cell or a
      whole cell.

   capacity cache

      A Compute back-end database table that contains the current
      workload, amount of free RAM, and number of VMs running on each host.
      Used to determine on which host a VM starts.

   capacity updater

      A notification driver that monitors VM instances and updates the
      capacity cache as needed.

   CAST

      One of the RPC primitives used by the OpenStack message queue
      software. Sends a message and does not wait for a response.

   catalog

      A list of API endpoints that are available to a user after
      authentication with the Identity service.

   catalog service

      An Identity service that lists API endpoints that are available
      to a user after authentication with the Identity service.

   ceilometer

      Part of the OpenStack :term:`Telemetry service <Telemetry
      service (telemetry)>`; gathers and stores metrics from other
      OpenStack services.

   cell

      Provides logical partitioning of Compute resources in a child
      and parent relationship. Requests are passed from parent cells to
      child cells if the parent cannot provide the requested
      resource.

   cell forwarding

      A Compute option that enables parent cells to pass resource
      requests to child cells if the parent cannot provide the requested
      resource.

   cell manager

      The Compute component that contains a list of the current
      capabilities of each host within the cell and routes requests as
      appropriate.

   CentOS

      A Linux distribution that is compatible with OpenStack.

   Ceph

      Massively scalable distributed storage system that consists of
      an object store, block store, and POSIX-compatible distributed file
      system. Compatible with OpenStack.

   CephFS

      The POSIX-compliant file system provided by Ceph.

   certificate authority (CA)

      In cryptography, an entity that issues digital certificates. The digital
      certificate certifies the ownership of a public key by the named
      subject of the certificate. This enables others (relying parties) to
      rely upon signatures or assertions made by the private key that
      corresponds to the certified public key. In this model of trust
      relationships, a CA is a trusted third party for both the subject
      (owner) of the certificate and the party relying upon the certificate.
      CAs are characteristic of many public key infrastructure (PKI)
      schemes.
      In OpenStack, a simple certificate authority is provided by Compute for
      cloudpipe VPNs and VM image decryption.

   Challenge-Handshake Authentication Protocol (CHAP)

      An iSCSI authentication method supported by Compute.

   chance scheduler

      A scheduling method used by Compute that randomly chooses an
      available host from the pool.

   changes since

      A Compute API parameter that downloads changes to the requested
      item since your last request, instead of downloading a new, fresh set
      of data and comparing it against the old data.

   Chef

      An operating system configuration management tool supporting
      OpenStack deployments.

   child cell

      If a requested resource such as CPU time, disk storage, or
      memory is not available in the parent cell, the request is forwarded
      to its associated child cells. If the child cell can fulfill the
      request, it does. Otherwise, it attempts to pass the request to any of
      its children.

   cinder

      Codename for :term:`Block Storage service
      <Block Storage service (cinder)>`.

   CirrOS

      A minimal Linux distribution designed for use as a test
      image on clouds such as OpenStack.

   Cisco neutron plug-in

      A Networking plug-in for Cisco devices and technologies,
      including UCS and Nexus.

   cloud architect

      A person who plans, designs, and oversees the creation of
      clouds.

   Cloud Auditing Data Federation (CADF)

      Cloud Auditing Data Federation (CADF) is a
      specification for audit event data. CADF is
      supported by OpenStack Identity.

   cloud computing

      A model that enables access to a shared pool of configurable
      computing resources, such as networks, servers, storage, applications,
      and services, that can be rapidly provisioned and released with
      minimal management effort or service provider interaction.

   cloud controller

      Collection of Compute components that represent the global state
      of the cloud; talks to services, such as Identity authentication,
      Object Storage, and node/storage workers through a
      queue.

   cloud controller node

      A node that runs network, volume, API, scheduler, and image
      services. Each service may be broken out into separate nodes for
      scalability or availability.

   Cloud Data Management Interface (CDMI)

      SINA standard that defines a RESTful API for managing objects in
      the cloud, currently unsupported in OpenStack.

   Cloud Infrastructure Management Interface (CIMI)

      An in-progress specification for cloud management. Currently
      unsupported in OpenStack.

   cloud-init

      A package commonly installed in VM images that performs
      initialization of an instance after boot using information that it
      retrieves from the metadata service, such as the SSH public key and
      user data.

   cloudadmin

      One of the default roles in the Compute RBAC system. Grants
      complete system access.

   Cloudbase-Init

      A Windows project providing guest initialization features,
      similar to cloud-init.

   cloudpipe

      A compute service that creates VPNs on a per-project
      basis.

   cloudpipe image

      A pre-made VM image that serves as a cloudpipe server.
      Essentially, OpenVPN running on Linux.

   Clustering service (senlin)

      The project that implements clustering services and libraries
      for the management of groups of homogeneous objects exposed
      by other OpenStack services.

   command filter

      Lists allowed commands within the Compute rootwrap
      facility.

   Common Internet File System (CIFS)

      A file sharing protocol. It is a public or open variation of the
      original Server Message Block (SMB) protocol developed and used by
      Microsoft. Like the SMB protocol, CIFS runs at a higher level and uses
      the TCP/IP protocol.

   Common Libraries (oslo)

      The project that produces a set of python libraries containing code
      shared by OpenStack projects. The APIs provided by these libraries
      should be high quality, stable, consistent, documented and generally
      applicable.

   community project

      A project that is not officially endorsed by the OpenStack
      Foundation. If the project is successful enough, it might be elevated
      to an incubated project and then to a core project, or it might be
      merged with the main code trunk.

   compression

      Reducing the size of files by special encoding, the file can be
      decompressed again to its original content. OpenStack supports
      compression at the Linux file system level but does not support
      compression for things such as Object Storage objects or Image service
      VM images.

   Compute API (Nova API)

      The nova-api daemon provides access to nova services. Can communicate with
      other APIs, such as the Amazon EC2 API.

   compute controller

      The Compute component that chooses suitable hosts on which to
      start VM instances.

   compute host

      Physical host dedicated to running compute nodes.

   compute node

      A node that runs the nova-compute daemon that manages VM
      instances that provide a wide
      range of services, such as web applications and analytics.

   Compute service (nova)

      The OpenStack core project that implements services and associated
      libraries to provide massively-scalable, on-demand, self-service
      access to compute resources, including bare metal, virtual machines,
      and containers.

   compute worker

      The Compute component that runs on each compute node and manages
      the VM instance lifecycle, including run, reboot, terminate,
      attach/detach volumes, and so on. Provided by the nova-compute daemon.

   concatenated object

      A set of segment objects that Object Storage combines and sends
      to the client.

   conductor

      In Compute, conductor is the process that proxies database
      requests from the compute process. Using conductor improves security
      because compute nodes do not need direct access to the
      database.

   congress

      Code name for the :term:`Governance service
      <Governance service (congress)>`.

   consistency window

      The amount of time it takes for a new Object Storage object to
      become accessible to all clients.

   console log

      Contains the output from a Linux VM console in Compute.

   container

      Organizes and stores objects in Object Storage. Similar to the
      concept of a Linux directory but cannot be nested. Alternative term
      for an Image service container format.

   container auditor

      Checks for missing replicas or incorrect objects in specified
      Object Storage containers through queries to the SQLite back-end
      database.

   container database

      A SQLite database that stores Object Storage containers and
      container metadata. The container server accesses this
      database.

   container format

      A wrapper used by the Image service that contains a VM image and
      its associated metadata, such as machine state, OS disk size, and so
      on.

   Container Infrastructure Management service (magnum)

      The project which provides a set of services for provisioning, scaling,
      and managing container orchestration engines.

   container server

      An Object Storage server that manages containers.

   container service

      The Object Storage component that provides container services,
      such as create, delete, list, and so on.

   content delivery network (CDN)

      A content delivery network is a specialized network that is
      used to distribute content to clients, typically located
      close to the client for increased performance.

   controller node

      Alternative term for a cloud controller node.

   core API

      Depending on context, the core API is either the OpenStack API
      or the main API of a specific core project, such as Compute,
      Networking, Image service, and so on.

   core service

      An official OpenStack service defined as core by
      DefCore Committee. Currently, consists of
      Block Storage service (cinder), Compute service (nova),
      Identity service (keystone), Image service (glance),
      Networking service (neutron), and Object Storage service (swift).

   cost

      Under the Compute distributed scheduler, this is calculated by
      looking at the capabilities of each host relative to the flavor of the
      VM instance being requested.

   credentials

      Data that is only known to or accessible by a user and
      used to verify that the user is who he says he is.
      Credentials are presented to the server during
      authentication. Examples include a password, secret key,
      digital certificate, and fingerprint.

   CRL

      A Certificate Revocation List (CRL) in a PKI model is a list of
      certificates that have been revoked. End entities presenting
      these certificates should not be trusted.

   Cross-Origin Resource Sharing (CORS)

      A mechanism that allows many resources (for example,
      fonts, JavaScript) on a web page to be requested from
      another domain outside the domain from which the resource
      originated. In particular, JavaScript's AJAX calls can use
      the XMLHttpRequest mechanism.

   Crowbar

      An open source community project by SUSE that aims to provide
      all necessary services to quickly deploy and manage clouds.

   current workload

      An element of the Compute capacity cache that is calculated
      based on the number of build, snapshot, migrate, and resize operations
      currently in progress on a given host.

   customer

      Alternative term for project.

   customization module

      A user-created Python module that is loaded by horizon to change
      the look and feel of the dashboard.

D
~

.. glossary::

   daemon

      A process that runs in the background and waits for requests.
      May or may not listen on a TCP or UDP port. Do not confuse with a
      worker.

   Dashboard (horizon)

      OpenStack project which provides an extensible, unified, web-based
      user interface for all OpenStack services.

   data encryption

      Both Image service and Compute support encrypted virtual machine
      (VM) images (but not instances). In-transit data encryption is
      supported in OpenStack using technologies such as HTTPS, SSL, TLS, and
      SSH. Object Storage does not support object encryption at the
      application level but may support storage that uses disk encryption.

   Data loss prevention (DLP) software

      Software programs used to protect sensitive information
      and prevent it from leaking outside a network boundary
      through the detection and denying of the data transportation.

   Data Processing service (sahara)

      OpenStack project that provides a scalable
      data-processing stack and associated management
      interfaces.

   data store

      A database engine supported by the Database service.

   database ID

      A unique ID given to each replica of an Object Storage
      database.

   database replicator

      An Object Storage component that copies changes in the account,
      container, and object databases to other nodes.

   Database service (trove)

      An integrated project that provides scalable and reliable
      Cloud Database-as-a-Service functionality for both
      relational and non-relational database engines.

   deallocate

      The process of removing the association between a floating IP
      address and a fixed IP address. Once this association is removed, the
      floating IP returns to the address pool.

   Debian

      A Linux distribution that is compatible with OpenStack.

   deduplication

      The process of finding duplicate data at the disk block, file,
      and/or object level to minimize storage use—currently unsupported
      within OpenStack.

   default panel

      The default panel that is displayed when a user accesses the
      dashboard.

   default project

      New users are assigned to this project if no project is specified
      when a user is created.

   default token

      An Identity service token that is not associated with a specific
      project and is exchanged for a scoped token.

   delayed delete

      An option within Image service so that an image is deleted after
      a predefined number of seconds instead of immediately.

   delivery mode

      Setting for the Compute RabbitMQ message delivery mode; can be
      set to either transient or persistent.

   denial of service (DoS)

      Denial of service (DoS) is a short form for
      denial-of-service attack. This is a malicious attempt to
      prevent legitimate users from using a service.

   deprecated auth

      An option within Compute that enables administrators to create
      and manage users through the ``nova-manage`` command as
      opposed to using the Identity service.

   designate

      Code name for the :term:`DNS service <DNS service (designate)>`.

   Desktop-as-a-Service

      A platform that provides a suite of desktop environments
      that users access to receive a desktop experience from
      any location. This may provide general use, development, or
      even homogeneous testing environments.

   developer

      One of the default roles in the Compute RBAC system and the
      default role assigned to a new user.

   device ID

      Maps Object Storage partitions to physical storage
      devices.

   device weight

      Distributes partitions proportionately across Object Storage
      devices based on the storage capacity of each device.

   DevStack

      Community project that uses shell scripts to quickly build
      complete OpenStack development environments.

   DHCP agent

      OpenStack Networking agent that provides DHCP services
      for virtual networks.

   Diablo

      A grouped release of projects related to OpenStack that came out
      in the fall of 2011, the fourth release of OpenStack. It included
      Compute (nova 2011.3), Object Storage (swift 1.4.3), and the Image
      service (glance).
      Diablo is the code name for the fourth release of
      OpenStack. The design summit took place in
      the Bay Area near Santa Clara,
      California, US and Diablo is a nearby city.

   direct consumer

      An element of the Compute RabbitMQ that comes to life when a RPC
      call is executed. It connects to a direct exchange through a unique
      exclusive queue, sends the message, and terminates.

   direct exchange

      A routing table that is created within the Compute RabbitMQ
      during RPC calls; one is created for each RPC call that is
      invoked.

   direct publisher

      Element of RabbitMQ that provides a response to an incoming MQ
      message.

   disassociate

      The process of removing the association between a floating IP
      address and fixed IP and thus returning the floating IP address to the
      address pool.

   Discretionary Access Control (DAC)

      Governs the ability of subjects to access objects, while enabling
      users to make policy decisions and assign security attributes.
      The traditional UNIX system of users, groups, and read-write-execute
      permissions is an example of DAC.

   disk encryption

      The ability to encrypt data at the file system, disk partition,
      or whole-disk level. Supported within Compute VMs.

   disk format

      The underlying format that a disk image for a VM is stored as
      within the Image service back-end store. For example, AMI, ISO, QCOW2,
      VMDK, and so on.

   dispersion

      In Object Storage, tools to test and ensure dispersion of
      objects and containers to ensure fault tolerance.

   distributed virtual router (DVR)

      Mechanism for highly available multi-host routing when using
      OpenStack Networking (neutron).

   Django

      A web framework used extensively in horizon.

   DNS record

      A record that specifies information about a particular domain
      and belongs to the domain.

   DNS service (designate)

      OpenStack project that provides scalable, on demand, self
      service access to authoritative DNS services, in a
      technology-agnostic manner.

   dnsmasq

      Daemon that provides DNS, DHCP, BOOTP, and TFTP services for
      virtual networks.

   domain

      An Identity API v3 entity. Represents a collection of
      projects, groups and users that defines administrative boundaries for
      managing OpenStack Identity entities.
      On the Internet, separates a website from other sites. Often,
      the domain name has two or more parts that are separated by dots.
      For example, yahoo.com, usa.gov, harvard.edu, or
      mail.yahoo.com.
      Also, a domain is an entity or container of all DNS-related
      information containing one or more records.

   Domain Name System (DNS)

      A system by which Internet domain name-to-address and
      address-to-name resolutions are determined.
      DNS helps navigate the Internet by translating the IP address
      into an address that is easier to remember. For example, translating
      111.111.111.1 into www.yahoo.com.
      All domains and their components, such as mail servers, utilize
      DNS to resolve to the appropriate locations. DNS servers are usually
      set up in a master-slave relationship such that failure of the master
      invokes the slave. DNS servers might also be clustered or replicated
      such that changes made to one DNS server are automatically propagated
      to other active servers.
      In Compute, the support that enables associating DNS entries
      with floating IP addresses, nodes, or cells so that hostnames are
      consistent across reboots.

   download

      The transfer of data, usually in the form of files, from one
      computer to another.

   durable exchange

      The Compute RabbitMQ message exchange that remains active when
      the server restarts.

   durable queue

      A Compute RabbitMQ message queue that remains active when the
      server restarts.

   Dynamic Host Configuration Protocol (DHCP)

      A network protocol that configures devices that are connected to a
      network so that they can communicate on that network by using the
      Internet Protocol (IP). The protocol is implemented in a client-server
      model where DHCP clients request configuration data, such as an IP
      address, a default route, and one or more DNS server addresses from a
      DHCP server.
      A method to automatically configure networking for a host at
      boot time. Provided by both Networking and Compute.

   Dynamic HyperText Markup Language (DHTML)

      Pages that use HTML, JavaScript, and Cascading Style Sheets to
      enable users to interact with a web page or show simple
      animation.

E
~

.. glossary::

   east-west traffic

      Network traffic between servers in the same cloud or data center.
      See also north-south traffic.

   EBS boot volume

      An Amazon EBS storage volume that contains a bootable VM image,
      currently unsupported in OpenStack.

   ebtables

      Filtering tool for a Linux bridging firewall, enabling
      filtering of network traffic passing through a Linux bridge.
      Used in Compute along with arptables, iptables, and ip6tables
      to ensure isolation of network communications.

   EC2

      The Amazon commercial compute product, similar to
      Compute.

   EC2 access key

      Used along with an EC2 secret key to access the Compute EC2
      API.

   EC2 API

      OpenStack supports accessing the Amazon EC2 API through
      Compute.

   EC2 Compatibility API

      A Compute component that enables OpenStack to communicate with
      Amazon EC2.

   EC2 secret key

      Used along with an EC2 access key when communicating with the
      Compute EC2 API; used to digitally sign each request.

   Elastic Block Storage (EBS)

      The Amazon commercial block storage product.

   encapsulation

      The practice of placing one packet type within another for
      the purposes of abstracting or securing data. Examples
      include GRE, MPLS, or IPsec.

   encryption

      OpenStack supports encryption technologies such as HTTPS, SSH,
      SSL, TLS, digital certificates, and data encryption.

   endpoint

      See API endpoint.

   endpoint registry

      Alternative term for an Identity service catalog.

   endpoint template

      A list of URL and port number endpoints that indicate where a
      service, such as Object Storage, Compute, Identity, and so on, can be
      accessed.

   entity

      Any piece of hardware or software that wants to connect to the
      network services provided by Networking, the network connectivity
      service. An entity can make use of Networking by implementing a
      VIF.

   ephemeral image

      A VM image that does not save changes made to its volumes and
      reverts them to their original state after the instance is
      terminated.

   ephemeral volume

      Volume that does not save the changes made to it and reverts to
      its original state when the current user relinquishes control.

   Essex

      A grouped release of projects related to OpenStack that came out
      in April 2012, the fifth release of OpenStack. It included Compute
      (nova 2012.1), Object Storage (swift 1.4.8), Image (glance), Identity
      (keystone), and Dashboard (horizon).
      Essex is the code name for the fifth release of
      OpenStack. The design summit took place in
      Boston, Massachusetts, US and Essex is a nearby city.

   ESXi

      An OpenStack-supported hypervisor.

   ETag

      MD5 hash of an object within Object Storage, used to ensure data
      integrity.

   euca2ools

      A collection of command-line tools for administering VMs; most
      are compatible with OpenStack.

   Eucalyptus Kernel Image (EKI)

      Used along with an ERI to create an EMI.

   Eucalyptus Machine Image (EMI)

      VM image container format supported by Image service.

   Eucalyptus Ramdisk Image (ERI)

      Used along with an EKI to create an EMI.

   evacuate

      The process of migrating one or all virtual machine (VM)
      instances from one host to another, compatible with both shared
      storage live migration and block migration.

   exchange

      Alternative term for a RabbitMQ message exchange.

   exchange type

      A routing algorithm in the Compute RabbitMQ.

   exclusive queue

      Connected to by a direct consumer in RabbitMQ—Compute, the
      message can be consumed only by the current connection.

   extended attributes (xattr)

      File system option that enables storage of additional
      information beyond owner, group, permissions, modification time, and
      so on. The underlying Object Storage file system must support extended
      attributes.

   extension

      Alternative term for an API extension or plug-in. In the context
      of Identity service, this is a call that is specific to the
      implementation, such as adding support for OpenID.

   external network

      A network segment typically used for instance Internet
      access.

   extra specs

      Specifies additional requirements when Compute determines where
      to start a new instance. Examples include a minimum amount of network
      bandwidth or a GPU.

F
~

.. glossary::

   FakeLDAP

      An easy method to create a local LDAP directory for testing
      Identity and Compute. Requires Redis.

   fan-out exchange

      Within RabbitMQ and Compute, it is the messaging interface that
      is used by the scheduler service to receive capability messages from
      the compute, volume, and network nodes.

   federated identity

      A method to establish trusts between identity providers and the
      OpenStack cloud.

   Fedora

      A Linux distribution compatible with OpenStack.

   Fibre Channel

      Storage protocol similar in concept to TCP/IP; encapsulates SCSI
      commands and data.

   Fibre Channel over Ethernet (FCoE)

      The fibre channel protocol tunneled within Ethernet.

   fill-first scheduler

      The Compute scheduling method that attempts to fill a host with
      VMs rather than starting new VMs on a variety of hosts.

   filter

      The step in the Compute scheduling process when hosts that
      cannot run VMs are eliminated and not chosen.

   firewall

      Used to restrict communications between hosts and/or nodes,
      implemented in Compute using iptables, arptables, ip6tables, and
      ebtables.

   FireWall-as-a-Service (FWaaS)

      A Networking extension that provides perimeter firewall
      functionality.

   fixed IP address

      An IP address that is associated with the same instance each
      time that instance boots, is generally not accessible to end users or
      the public Internet, and is used for management of the
      instance.

   Flat Manager

      The Compute component that gives IP addresses to authorized
      nodes and assumes DHCP, DNS, and routing configuration and services
      are provided by something else.

   flat mode injection

      A Compute networking method where the OS network configuration
      information is injected into the VM image before the instance
      starts.

   flat network

      Virtual network type that uses neither VLANs nor tunnels to
      segregate project traffic. Each flat network typically requires
      a separate underlying physical interface defined by bridge
      mappings. However, a flat network can contain multiple
      subnets.

   FlatDHCP Manager

      The Compute component that provides dnsmasq (DHCP, DNS, BOOTP,
      TFTP) and radvd (routing) services.

   flavor

      Alternative term for a VM instance type.

   flavor ID

      UUID for each Compute or Image service VM flavor or instance
      type.

   floating IP address

      An IP address that a project can associate with a VM so that the
      instance has the same public IP address each time that it boots. You
      create a pool of floating IP addresses and assign them to instances as
      they are launched to maintain a consistent IP address for maintaining
      DNS assignment.

   Folsom

      A grouped release of projects related to OpenStack that came out
      in the fall of 2012, the sixth release of OpenStack. It includes
      Compute (nova), Object Storage (swift), Identity (keystone),
      Networking (neutron), Image service (glance), and Volumes or Block
      Storage (cinder).
      Folsom is the code name for the sixth release of
      OpenStack. The design summit took place in
      San Francisco, California, US and Folsom is a nearby city.

   FormPost

      Object Storage middleware that uploads (posts) an image through
      a form on a web page.

   freezer

      Code name for the :term:`Backup, Restore, and Disaster Recovery service
      <Backup, Restore, and Disaster Recovery service (freezer)>`.

   front end

      The point where a user interacts with a service; can be an API
      endpoint, the dashboard, or a command-line tool.

G
~

.. glossary::

   gateway

      An IP address, typically assigned to a router, that
      passes network traffic between different networks.

   generic receive offload (GRO)

      Feature of certain network interface drivers that
      combines many smaller received packets into a large packet
      before delivery to the kernel IP stack.

   generic routing encapsulation (GRE)

      Protocol that encapsulates a wide variety of network
      layer protocols inside virtual point-to-point links.

   glance

      Codename for the :term:`Image service<Image service (glance)>`.

   glance API server

      Alternative name for the :term:`Image API`.

   glance registry

      Alternative term for the Image service :term:`image registry`.

   global endpoint template

      The Identity service endpoint template that contains services
      available to all projects.

   GlusterFS

      A file system designed to aggregate NAS hosts, compatible with
      OpenStack.

   gnocchi

      Part of the OpenStack :term:`Telemetry service <Telemetry
      service (telemetry)>`; provides an indexer and time-series
      database.

   golden image

      A method of operating system installation where a finalized disk
      image is created and then used by all nodes without
      modification.

   Governance service (congress)

      The project that provides Governance-as-a-Service across
      any collection of cloud services in order to monitor,
      enforce, and audit policy over dynamic infrastructure.

   Graphic Interchange Format (GIF)

      A type of image file that is commonly used for animated images
      on web pages.

   Graphics Processing Unit (GPU)

      Choosing a host based on the existence of a GPU is currently
      unsupported in OpenStack.

   Green Threads

      The cooperative threading model used by Python; reduces race
      conditions and only context switches when specific library calls are
      made. Each OpenStack service is its own thread.

   Grizzly

      The code name for the seventh release of
      OpenStack. The design summit took place in
      San Diego, California, US and Grizzly is an element of the state flag of
      California.

   Group

      An Identity v3 API entity. Represents a collection of users that is
      owned by a specific domain.

   guest OS

      An operating system instance running under the control of a
      hypervisor.

H
~

.. glossary::

   Hadoop

      Apache Hadoop is an open source software framework that supports
      data-intensive distributed applications.

   Hadoop Distributed File System (HDFS)

      A distributed, highly fault-tolerant file system designed to run
      on low-cost commodity hardware.

   handover

      An object state in Object Storage where a new replica of the
      object is automatically created due to a drive failure.

   HAProxy

      Provides a load balancer for TCP and HTTP-based applications that
      spreads requests across multiple servers.

   hard reboot

      A type of reboot where a physical or virtual power button is
      pressed as opposed to a graceful, proper shutdown of the operating
      system.

   Havana

      The code name for the eighth release of OpenStack. The
      design summit took place in Portland, Oregon, US and Havana is
      an unincorporated community in Oregon.

   health monitor

      Determines whether back-end members of a VIP pool can
      process a request. A pool can have several health monitors
      associated with it. When a pool has several monitors
      associated with it, all monitors check each member of the
      pool. All monitors must declare a member to be healthy for
      it to stay active.

   heat
      Codename for the :term:`Orchestration service
      <Orchestration service (heat)>`.

   Heat Orchestration Template (HOT)

      Heat input in the format native to OpenStack.

   high availability (HA)

      A high availability system design approach and associated
      service implementation ensures that a prearranged level of
      operational performance will be met during a contractual
      measurement period. High availability systems seek to
      minimize system downtime and data loss.

   horizon

      Codename for the :term:`Dashboard <Dashboard (horizon)>`.

   horizon plug-in

      A plug-in for the OpenStack Dashboard (horizon).

   host

      A physical computer, not a VM instance (node).

   host aggregate

      A method to further subdivide availability zones into hypervisor
      pools, a collection of common hosts.

   Host Bus Adapter (HBA)

      Device plugged into a PCI slot, such as a fibre channel or
      network card.

   hybrid cloud

      A hybrid cloud is a composition of two or more clouds
      (private, community or public) that remain distinct entities
      but are bound together, offering the benefits of multiple
      deployment models.  Hybrid cloud can also mean the ability
      to connect colocation, managed and/or dedicated services
      with cloud resources.

   Hyper-V

      One of the hypervisors supported by OpenStack.

   hyperlink

      Any kind of text that contains a link to some other site,
      commonly found in documents where clicking on a word or words opens up
      a different website.

   Hypertext Transfer Protocol (HTTP)

      An application protocol for distributed, collaborative,
      hypermedia information systems. It is the foundation of data
      communication for the World Wide Web. Hypertext is structured
      text that uses logical links (hyperlinks) between nodes containing
      text. HTTP is the protocol to exchange or transfer hypertext.

   Hypertext Transfer Protocol Secure (HTTPS)

      An encrypted communications protocol for secure communication
      over a computer network, with especially wide deployment on the
      Internet. Technically, it is not a protocol in and of itself;
      rather, it is the result of simply layering the Hypertext Transfer
      Protocol (HTTP) on top of the TLS or SSL protocol, thus adding the
      security capabilities of TLS or SSL to standard HTTP communications.
      Most OpenStack API endpoints and many inter-component communications
      support HTTPS communication.

   hypervisor

      Software that arbitrates and controls VM access to the actual
      underlying hardware.

   hypervisor pool

      A collection of hypervisors grouped together through host
      aggregates.

I
~

.. glossary::

   Icehouse

      The code name for the ninth release of OpenStack. The
      design summit took place in Hong Kong and Ice House is a
      street in that city.

   ID number

      Unique numeric ID associated with each user in Identity,
      conceptually similar to a Linux or LDAP UID.

   Identity API

      Alternative term for the Identity service API.

   Identity back end

      The source used by Identity service to retrieve user
      information; an OpenLDAP server, for example.

   identity provider

      A directory service, which allows users to login with a user
      name and password. It is a typical source of authentication
      tokens.

   Identity service (keystone)

      The project that facilitates API client authentication, service
      discovery, distributed multi-project authorization, and auditing.
      It provides a central directory of users mapped to the OpenStack
      services they can access. It also registers endpoints for OpenStack
      services and acts as a common authentication system.

   Identity service API

      The API used to access the OpenStack Identity service provided
      through keystone.

   IETF

     Internet Engineering Task Force (IETF) is an open standards
     organization that develops Internet standards, particularly the
     standards pertaining to TCP/IP.

   image

      A collection of files for a specific operating system (OS) that
      you use to create or rebuild a server. OpenStack provides pre-built
      images. You can also create custom images, or snapshots, from servers
      that you have launched. Custom images can be used for data backups or
      as "gold" images for additional servers.

   Image API

      The Image service API endpoint for management of VM
      images.
      Processes client requests for VMs, updates Image service
      metadata on the registry server, and communicates with the store
      adapter to upload VM images from the back-end store.

   image cache

      Used by Image service to obtain images on the local host rather
      than re-downloading them from the image server each time one is
      requested.

   image ID

      Combination of a URI and UUID used to access Image service VM
      images through the image API.

   image membership

      A list of projects that can access a given VM image within Image
      service.

   image owner

      The project who owns an Image service virtual machine
      image.

   image registry

      A list of VM images that are available through Image
      service.

   Image service (glance)

      The OpenStack service that provide services and associated libraries
      to store, browse, share, distribute and manage bootable disk images,
      other data closely associated with initializing compute resources,
      and metadata definitions.

   image status

      The current status of a VM image in Image service, not to be
      confused with the status of a running instance.

   image store

      The back-end store used by Image service to store VM images,
      options include Object Storage, locally mounted file system,
      RADOS block devices, VMware datastore, or HTTP.

   image UUID

      UUID used by Image service to uniquely identify each VM
      image.

   incubated project

      A community project may be elevated to this status and is then
      promoted to a core project.

   Infrastructure Optimization service (watcher)

      OpenStack project that aims to provide a flexible and scalable resource
      optimization service for multi-project OpenStack-based clouds.

   Infrastructure-as-a-Service (IaaS)

      IaaS is a provisioning model in which an organization outsources
      physical components of a data center, such as storage, hardware,
      servers, and networking components. A service provider owns the
      equipment and is responsible for housing, operating and maintaining
      it. The client typically pays on a per-use basis.
      IaaS is a model for providing cloud services.

   ingress filtering

      The process of filtering incoming network traffic. Supported by
      Compute.

   INI format

      The OpenStack configuration files use an INI format to
      describe options and their values. It consists of sections
      and key value pairs.

   injection

      The process of putting a file into a virtual machine image
      before the instance is started.

   Input/Output Operations Per Second (IOPS)

      IOPS are a common performance measurement used to benchmark computer
      storage devices like hard disk drives, solid state drives, and
      storage area networks.

   instance

      A running VM, or a VM in a known state such as suspended, that
      can be used like a hardware server.

   instance ID

      Alternative term for instance UUID.

   instance state

      The current state of a guest VM image.

   instance tunnels network

      A network segment used for instance traffic tunnels
      between compute nodes and the network node.

   instance type

      Describes the parameters of the various virtual machine images
      that are available to users; includes parameters such as CPU, storage,
      and memory. Alternative term for flavor.

   instance type ID

      Alternative term for a flavor ID.

   instance UUID

      Unique ID assigned to each guest VM instance.

   Intelligent Platform Management Interface (IPMI)

      IPMI is a standardized computer system interface used by system
      administrators for out-of-band management of computer systems and
      monitoring of their operation. In layman's terms, it is a way to
      manage a computer using a direct network connection, whether it is
      turned on or not; connecting to the hardware rather than an operating
      system or login shell.

   interface

      A physical or virtual device that provides connectivity
      to another device or medium.

   interface ID

      Unique ID for a Networking VIF or vNIC in the form of a
      UUID.

   Internet Control Message Protocol (ICMP)

      A network protocol used by network devices for control messages.
      For example, :command:`ping` uses ICMP to test
      connectivity.

   Internet protocol (IP)

      Principal communications protocol in the internet protocol
      suite for relaying datagrams across network boundaries.

   Internet Service Provider (ISP)

      Any business that provides Internet access to individuals or
      businesses.

   Internet Small Computer System Interface (iSCSI)

      Storage protocol that encapsulates SCSI frames for transport
      over IP networks.
      Supported by Compute, Object Storage, and Image service.

   IP address

      Number that is unique to every computer system on the Internet.
      Two versions of the Internet Protocol (IP) are in use for addresses:
      IPv4 and IPv6.

   IP Address Management (IPAM)

      The process of automating IP address allocation, deallocation,
      and management. Currently provided by Compute, melange, and
      Networking.

   ip6tables

      Tool used to set up, maintain, and inspect the tables of IPv6
      packet filter rules in the Linux kernel. In OpenStack Compute,
      ip6tables is used along with arptables, ebtables, and iptables to
      create firewalls for both nodes and VMs.

   ipset

      Extension to iptables that allows creation of firewall rules
      that match entire "sets" of IP addresses simultaneously. These
      sets reside in indexed data structures to increase efficiency,
      particularly on systems with a large quantity of rules.

   iptables

      Used along with arptables and ebtables, iptables create
      firewalls in Compute. iptables are the tables provided by the Linux
      kernel firewall (implemented as different Netfilter modules) and the
      chains and rules it stores. Different kernel modules and programs are
      currently used for different protocols: iptables applies to IPv4,
      ip6tables to IPv6, arptables to ARP, and ebtables to Ethernet frames.
      Requires root privilege to manipulate.

   ironic

      Codename for the :term:`Bare Metal service <Bare Metal service
      (ironic)>`.

   iSCSI Qualified Name (IQN)

      IQN is the format most commonly used for iSCSI names, which uniquely
      identify nodes in an iSCSI network.
      All IQNs follow the pattern iqn.yyyy-mm.domain:identifier, where
      'yyyy-mm' is the year and month in which the domain was registered,
      'domain' is the reversed domain name of the issuing organization, and
      'identifier' is an optional string which makes each IQN under the same
      domain unique. For example, 'iqn.2015-10.org.openstack.408ae959bce1'.

   ISO9660

      One of the VM image disk formats supported by Image
      service.

   itsec

      A default role in the Compute RBAC system that can quarantine an
      instance in any project.

J
~

.. glossary::

   Java

      A programming language that is used to create systems that
      involve more than one computer by way of a network.

   JavaScript

      A scripting language that is used to build web pages.

   JavaScript Object Notation (JSON)

      One of the supported response formats in OpenStack.

   jumbo frame

      Feature in modern Ethernet networks that supports frames up to
      approximately 9000 bytes.

   Juno

      The code name for the tenth release of OpenStack. The
      design summit took place in Atlanta, Georgia, US and Juno is
      an unincorporated community in Georgia.

K
~

.. glossary::

   Kerberos

      A network authentication protocol which works on the basis of
      tickets. Kerberos allows nodes communication over a non-secure
      network, and allows nodes to prove their identity to one another in a
      secure manner.

   kernel-based VM (KVM)

      An OpenStack-supported hypervisor. KVM is a full
      virtualization solution for Linux on x86 hardware containing
      virtualization extensions (Intel VT or AMD-V), ARM, IBM
      Power, and IBM zSeries. It consists of a loadable kernel
      module, that provides the core virtualization infrastructure
      and a processor specific module.

   Key Manager service (barbican)

      The project that produces a secret storage and
      generation system capable of providing key management for
      services wishing to enable encryption features.

   keystone

      Codename of the :term:`Identity service <Identity service (keystone)>`.

   Kickstart

      A tool to automate system configuration and installation on Red
      Hat, Fedora, and CentOS-based Linux distributions.

   Kilo

      The code name for the eleventh release of OpenStack. The
      design summit took place in Paris, France. Due to delays in the name
      selection, the release was known only as K. Because ``k`` is the
      unit symbol for kilo and the kilogram reference artifact is stored
      near Paris in the Pavillon de Breteuil in Sèvres, the community
      chose Kilo as the release name.

L
~

.. glossary::

   large object

      An object within Object Storage that is larger than 5 GB.

   Launchpad

      The collaboration site for OpenStack.

   Layer-2 (L2) agent

      OpenStack Networking agent that provides layer-2
      connectivity for virtual networks.

   Layer-2 network

      Term used in the OSI network architecture for the data link
      layer. The data link layer is responsible for media access
      control, flow control and detecting and possibly correcting
      errors that may occur in the physical layer.

   Layer-3 (L3) agent

      OpenStack Networking agent that provides layer-3
      (routing) services for virtual networks.

   Layer-3 network

      Term used in the OSI network architecture for the network
      layer. The network layer is responsible for packet
      forwarding including routing from one node to another.

   Liberty

      The code name for the twelfth release of OpenStack. The
      design summit took place in Vancouver, Canada and Liberty is
      the name of a village in the Canadian province of
      Saskatchewan.

   libvirt

      Virtualization API library used by OpenStack to interact with
      many of its supported hypervisors.

   Lightweight Directory Access Protocol (LDAP)

      An application protocol for accessing and maintaining distributed
      directory information services over an IP network.

   Linux

      Unix-like computer operating system assembled under the model of
      free and open-source software development and distribution.

   Linux bridge

      Software that enables multiple VMs to share a single physical
      NIC within Compute.

   Linux Bridge neutron plug-in

      Enables a Linux bridge to understand a Networking port,
      interface attachment, and other abstractions.

   Linux containers (LXC)

      An OpenStack-supported hypervisor.

   live migration

      The ability within Compute to move running virtual machine
      instances from one host to another with only a small service
      interruption during switchover.

   load balancer

      A load balancer is a logical device that belongs to a cloud
      account. It is used to distribute workloads between multiple back-end
      systems or services, based on the criteria defined as part of its
      configuration.

   load balancing

      The process of spreading client requests between two or more
      nodes to improve performance and availability.

   Load-Balancer-as-a-Service (LBaaS)

      Enables Networking to distribute incoming requests evenly
      between designated instances.

   Load-balancing service (octavia)

      The project that aims to provide scalable, on demand, self service
      access to load-balancer services, in technology-agnostic manner.

   Logical Volume Manager (LVM)

      Provides a method of allocating space on mass-storage
      devices that is more flexible than conventional partitioning
      schemes.

M
~

.. glossary::

   magnum

      Code name for the :term:`Containers Infrastructure Management
      service<Container Infrastructure Management service (magnum)>`.

   management API

      Alternative term for an admin API.

   management network

      A network segment used for administration, not accessible to the
      public Internet.

   manager

      Logical groupings of related code, such as the Block Storage
      volume manager or network manager.

   manifest

      Used to track segments of a large object within Object
      Storage.

   manifest object

      A special Object Storage object that contains the manifest for a
      large object.

   manila

      Codename for OpenStack :term:`Shared File Systems service<Shared
      File Systems service (manila)>`.

   manila-share

      Responsible for managing Shared File System Service devices, specifically
      the back-end devices.

   maximum transmission unit (MTU)

      Maximum frame or packet size for a particular network
      medium. Typically 1500 bytes for Ethernet networks.

   mechanism driver

      A driver for the Modular Layer 2 (ML2) neutron plug-in that
      provides layer-2 connectivity for virtual instances. A
      single OpenStack installation can use multiple mechanism
      drivers.

   melange

      Project name for OpenStack Network Information Service. To be
      merged with Networking.

   membership

      The association between an Image service VM image and a project.
      Enables images to be shared with specified projects.

   membership list

      A list of projects that can access a given VM image within Image
      service.

   memcached

      A distributed memory object caching system that is used by
      Object Storage for caching.

   memory overcommit

      The ability to start new VM instances based on the actual memory
      usage of a host, as opposed to basing the decision on the amount of
      RAM each running instance thinks it has available. Also known as RAM
      overcommit.

   message broker

      The software package used to provide AMQP messaging capabilities
      within Compute. Default package is RabbitMQ.

   message bus

      The main virtual communication line used by all AMQP messages
      for inter-cloud communications within Compute.

   message queue

      Passes requests from clients to the appropriate workers and
      returns the output to the client after the job completes.

   Message service (zaqar)

      The project that provides a messaging service that affords a
      variety of distributed application patterns in an efficient,
      scalable and highly available manner, and to create and maintain
      associated Python libraries and documentation.

   Meta-Data Server (MDS)

      Stores CephFS metadata.

   Metadata agent

      OpenStack Networking agent that provides metadata
      services for instances.

   migration

      The process of moving a VM instance from one host to
      another.

   mistral

      Code name for :term:`Workflow service <Workflow service (mistral)>`.

   Mitaka

      The code name for the thirteenth release of OpenStack.
      The design summit took place in Tokyo, Japan. Mitaka
      is a city in Tokyo.

   Modular Layer 2 (ML2) neutron plug-in

      Can concurrently use multiple layer-2 networking technologies,
      such as 802.1Q and VXLAN, in Networking.

   monasca

      Codename for OpenStack :term:`Monitoring <Monitoring (monasca)>`.

   Monitor (LBaaS)

      LBaaS feature that provides availability monitoring using the
      ``ping`` command, TCP, and HTTP/HTTPS GET.

   Monitor (Mon)

      A Ceph component that communicates with external clients, checks
      data state and consistency, and performs quorum functions.

   Monitoring (monasca)

      The OpenStack service that provides a multi-project, highly scalable,
      performant, fault-tolerant monitoring-as-a-service solution for metrics,
      complex event processing and logging. To build an extensible platform for
      advanced monitoring services that can be used by both operators and
      projects to gain operational insight and visibility, ensuring availability
      and stability.

   multi-factor authentication

      Authentication method that uses two or more credentials, such as
      a password and a private key. Currently not supported in
      Identity.

   multi-host

      High-availability mode for legacy (nova) networking.
      Each compute node handles NAT and DHCP and acts as a gateway
      for all of the VMs on it. A networking failure on one compute
      node doesn't affect VMs on other compute nodes.

   multinic

      Facility in Compute that allows each virtual machine instance to
      have more than one VIF connected to it.

   murano

      Codename for the :term:`Application Catalog service <Application Catalog
      service (murano)>`.

N
~

.. glossary::

   Nebula

      Released as open source by NASA in 2010 and is the basis for
      Compute.

   netadmin

      One of the default roles in the Compute RBAC system. Enables the
      user to allocate publicly accessible IP addresses to instances and
      change firewall rules.

   NetApp volume driver

      Enables Compute to communicate with NetApp storage devices
      through the NetApp OnCommand
      Provisioning Manager.

   network

      A virtual network that provides connectivity between entities.
      For example, a collection of virtual ports that share network
      connectivity. In Networking terminology, a network is always a layer-2
      network.

   Network Address Translation (NAT)

      Process of modifying IP address information while in transit.
      Supported by Compute and Networking.

   network controller

      A Compute daemon that orchestrates the network configuration of
      nodes, including IP addresses, VLANs, and bridging. Also manages
      routing for both public and private networks.

   Network File System (NFS)

      A method for making file systems available over the network.
      Supported by OpenStack.

   network ID

      Unique ID assigned to each network segment within Networking.
      Same as network UUID.

   network manager

      The Compute component that manages various network components,
      such as firewall rules, IP address allocation, and so on.

   network namespace

      Linux kernel feature that provides independent virtual
      networking instances on a single host with separate routing
      tables and interfaces. Similar to virtual routing and forwarding
      (VRF) services on physical network equipment.

   network node

      Any compute node that runs the network worker daemon.

   network segment

      Represents a virtual, isolated OSI layer-2 subnet in
      Networking.

   Network Service Header (NSH)

      Provides a mechanism for metadata exchange along the
      instantiated service path.

   Network Time Protocol (NTP)

      Method of keeping a clock for a host or node correct via
      communication with a trusted, accurate time source.

   network UUID

      Unique ID for a Networking network segment.

   network worker

      The ``nova-network`` worker daemon; provides
      services such as giving an IP address to a booting nova
      instance.

   Networking API (Neutron API)

      API used to access OpenStack Networking. Provides an extensible
      architecture to enable custom plug-in creation.

   Networking service (neutron)

      The OpenStack project which implements services and associated
      libraries to provide on-demand, scalable, and technology-agnostic
      network abstraction.

   neutron

      Codename for OpenStack :term:`Networking service <Networking service
      (neutron)>`.

   neutron API

      An alternative name for :term:`Networking API <Networking API
      (Neutron API)>`.

   neutron manager

      Enables Compute and Networking integration, which enables
      Networking to perform network management for guest VMs.

   neutron plug-in

      Interface within Networking that enables organizations to create
      custom plug-ins for advanced features, such as QoS, ACLs, or
      IDS.

   Newton

      The code name for the fourteenth release of OpenStack. The
      design summit took place in Austin, Texas, US. The
      release is named after "Newton House" which is located at
      1013 E. Ninth St., Austin, TX. which is listed on the
      National Register of Historic Places.

   Nexenta volume driver

      Provides support for NexentaStor devices in Compute.

   NFV Orchestration service (tacker)

      OpenStack service that aims to implement Network Function Virtualization
      (NFV) orchestration services and libraries for end-to-end life-cycle
      management of network services and Virtual Network Functions (VNFs).

   Nginx

      An HTTP and reverse proxy server, a mail proxy server, and a generic
      TCP/UDP proxy server.

   No ACK

      Disables server-side message acknowledgment in the Compute
      RabbitMQ. Increases performance but decreases reliability.

   node

      A VM instance that runs on a host.

   non-durable exchange

      Message exchange that is cleared when the service restarts. Its
      data is not written to persistent storage.

   non-durable queue

      Message queue that is cleared when the service restarts. Its
      data is not written to persistent storage.

   non-persistent volume

      Alternative term for an ephemeral volume.

   north-south traffic

      Network traffic between a user or client (north) and a
      server (south), or traffic into the cloud (south) and
      out of the cloud (north). See also east-west traffic.

   nova

      Codename for OpenStack :term:`Compute service <Compute service (nova)>`.

   Nova API

      Alternative term for the :term:`Compute API <Compute API (Nova API)>`.

   nova-network

      A Compute component that manages IP address allocation,
      firewalls, and other network-related tasks. This is the legacy
      networking option and an alternative to Networking.

O
~

.. glossary::

   object

      A BLOB of data held by Object Storage; can be in any
      format.

   object auditor

      Opens all objects for an object server and verifies the MD5
      hash, size, and metadata for each object.

   object expiration

      A configurable option within Object Storage to automatically
      delete objects after a specified amount of time has passed or a
      certain date is reached.

   object hash

      Unique ID for an Object Storage object.

   object path hash

      Used by Object Storage to determine the location of an object in
      the ring. Maps objects to partitions.

   object replicator

      An Object Storage component that copies an object to remote
      partitions for fault tolerance.

   object server

      An Object Storage component that is responsible for managing
      objects.

   Object Storage API

      API used to access OpenStack :term:`Object Storage<Object Storage
      service (swift)>`.

   Object Storage Device (OSD)

      The Ceph storage daemon.

   Object Storage service (swift)

      The OpenStack core project that provides eventually consistent
      and redundant storage and retrieval of fixed digital content.

   object versioning

      Allows a user to set a flag on an :term:`Object Storage<Object Storage
      service (swift)>` container so that all objects within the container are
      versioned.

   Ocata

      The code name for the fifteenth release of OpenStack. The
      design summit will take place in Barcelona, Spain. Ocata is
      a beach north of Barcelona.

   Octavia

      Code name for the :term:`Load-balancing service
      <Load-balancing service (octavia)>`.

   Oldie

      Term for an :term:`Object Storage<Object Storage service (swift)>`
      process that runs for a long time.  Can indicate a hung process.

   Open Cloud Computing Interface (OCCI)

      A standardized interface for managing compute, data, and network
      resources, currently unsupported in OpenStack.

   Open Virtualization Format (OVF)

      Standard for packaging VM images. Supported in OpenStack.

   Open vSwitch

      Open vSwitch is a production quality, multilayer virtual
      switch licensed under the open source Apache 2.0 license. It
      is designed to enable massive network automation through
      programmatic extension, while still supporting standard
      management interfaces and protocols (for example NetFlow,
      sFlow, SPAN, RSPAN, CLI, LACP, 802.1ag).

   Open vSwitch (OVS) agent

      Provides an interface to the underlying Open vSwitch service for
      the Networking plug-in.

   Open vSwitch neutron plug-in

      Provides support for Open vSwitch in Networking.

   OpenLDAP

      An open source LDAP server. Supported by both Compute and
      Identity.

   OpenStack

      OpenStack is a cloud operating system that controls large pools
      of compute, storage, and networking resources throughout a data
      center, all managed through a dashboard that gives administrators
      control while empowering their users to provision resources through a
      web interface. OpenStack is an open source project licensed under the
      Apache License 2.0.

   OpenStack code name

      Each OpenStack release has a code name. Code names ascend in
      alphabetical order: Austin, Bexar, Cactus, Diablo, Essex,
      Folsom, Grizzly, Havana, Icehouse, Juno, Kilo, Liberty,
      Mitaka, Newton, Ocata, Pike, Queens, and Rocky.
      Code names are cities or counties near where the
      corresponding OpenStack design summit took place. An
      exception, called the Waldon exception, is granted to
      elements of the state flag that sound especially cool. Code
      names are chosen by popular vote.

   openSUSE

      A Linux distribution that is compatible with OpenStack.

   operator

      The person responsible for planning and maintaining an OpenStack
      installation.

   optional service

      An official OpenStack service defined as optional by
      DefCore Committee. Currently, consists of
      Dashboard (horizon), Telemetry service (Telemetry),
      Orchestration service (heat), Database service (trove),
      Bare Metal service (ironic), and so on.

   Orchestration service (heat)

      The OpenStack service which orchestrates composite cloud
      applications using a declarative template format through
      an OpenStack-native REST API.

   orphan

      In the context of Object Storage, this is a process that is not
      terminated after an upgrade, restart, or reload of the service.

   Oslo

      Codename for the :term:`Common Libraries project<Common Libraries
      (oslo)>`.

P
~

.. glossary::

   panko

      Part of the OpenStack :term:`Telemetry service <Telemetry
      service (telemetry)>`; provides event storage.

   parent cell

      If a requested resource, such as CPU time, disk storage, or
      memory, is not available in the parent cell, the request is forwarded
      to associated child cells.

   partition

      A unit of storage within Object Storage used to store objects.
      It exists on top of devices and is replicated for fault
      tolerance.

   partition index

      Contains the locations of all Object Storage partitions within
      the ring.

   partition shift value

      Used by Object Storage to determine which partition data should
      reside on.

   path MTU discovery (PMTUD)

      Mechanism in IP networks to detect end-to-end MTU and adjust
      packet size accordingly.

   pause

      A VM state where no changes occur (no changes in memory, network
      communications stop, etc); the VM is frozen but not shut down.

   PCI passthrough

      Gives guest VMs exclusive access to a PCI device. Currently
      supported in OpenStack Havana and later releases.

   persistent message

      A message that is stored both in memory and on disk. The message
      is not lost after a failure or restart.

   persistent volume

      Changes to these types of disk volumes are saved.

   personality file

      A file used to customize a Compute instance. It can be used to
      inject SSH keys or a specific network configuration.

   Pike

      The code name for the sixteenth release of OpenStack. The design
      summit will take place in Boston, Massachusetts, US. The release
      is named after the Massachusetts Turnpike, abbreviated commonly
      as the Mass Pike, which is the easternmost stretch of
      Interstate 90.

   Platform-as-a-Service (PaaS)

      Provides to the consumer an operating system and, often, a
      language runtime and libraries (collectively, the "platform")
      upon which they can run their own application code, without
      providing any control over the underlying infrastructure.
      Examples of Platform-as-a-Service providers include Cloud Foundry
      and OpenShift.

   plug-in

      Software component providing the actual implementation for
      Networking APIs, or for Compute APIs, depending on the context.

   policy service

      Component of Identity that provides a rule-management
      interface and a rule-based authorization engine.

   policy-based routing (PBR)

      Provides a mechanism to implement packet forwarding and routing
      according to the policies defined by the network administrator.

   pool

      A logical set of devices, such as web servers, that you
      group together to receive and process traffic. The load
      balancing function chooses which member of the pool handles
      the new requests or connections received on the VIP
      address. Each VIP has one pool.

   pool member

      An application that runs on the back-end server in a
      load-balancing system.

   port

      A virtual network port within Networking; VIFs / vNICs are
      connected to a port.

   port UUID

      Unique ID for a Networking port.

   preseed

      A tool to automate system configuration and installation on
      Debian-based Linux distributions.

   private image

      An Image service VM image that is only available to specified
      projects.

   private IP address

      An IP address used for management and administration, not
      available to the public Internet.

   private network

      The Network Controller provides virtual networks to enable
      compute servers to interact with each other and with the public
      network. All machines must have a public and private network
      interface. A private network interface can be a flat or VLAN network
      interface. A flat network interface is controlled by the
      flat_interface with flat managers. A VLAN network interface is
      controlled by the ``vlan_interface`` option with VLAN
      managers.

   project

      Projects represent the base unit of "ownership" in OpenStack,
      in that all resources in OpenStack should be owned by a specific project.
      In OpenStack Identity, a project must be owned by a specific domain.

   project ID

      Unique ID assigned to each project by the Identity service.

   project VPN

      Alternative term for a cloudpipe.

   promiscuous mode

      Causes the network interface to pass all traffic it
      receives to the host rather than passing only the frames
      addressed to it.

   protected property

      Generally, extra properties on an Image service image to
      which only cloud administrators have access. Limits which user
      roles can perform CRUD operations on that property. The cloud
      administrator can configure any image property as
      protected.

   provider

      An administrator who has access to all hosts and
      instances.

   proxy node

      A node that provides the Object Storage proxy service.

   proxy server

      Users of Object Storage interact with the service through the
      proxy server, which in turn looks up the location of the requested
      data within the ring and returns the results to the user.

   public API

      An API endpoint used for both service-to-service communication
      and end-user interactions.

   public image

      An Image service VM image that is available to all
      projects.

   public IP address

      An IP address that is accessible to end-users.

   public key authentication

      Authentication method that uses keys rather than
      passwords.

   public network

      The Network Controller provides virtual networks to enable
      compute servers to interact with each other and with the public
      network. All machines must have a public and private network
      interface. The public network interface is controlled by the
      ``public_interface`` option.

   Puppet

      An operating system configuration-management tool supported by
      OpenStack.

   Python

      Programming language used extensively in OpenStack.

Q
~

.. glossary::

   QEMU Copy On Write 2 (QCOW2)

      One of the VM image disk formats supported by Image
      service.

   Qpid

      Message queue software supported by OpenStack; an alternative to
      RabbitMQ.

   Quality of Service (QoS)

      The ability to guarantee certain network or storage requirements to
      satisfy a Service Level Agreement (SLA) between an application provider
      and end users.
      Typically includes performance requirements like networking bandwidth,
      latency, jitter correction, and reliability as well as storage
      performance in Input/Output Operations Per Second (IOPS), throttling
      agreements, and performance expectations at peak load.

   quarantine

      If Object Storage finds objects, containers, or accounts that
      are corrupt, they are placed in this state, are not replicated, cannot
      be read by clients, and a correct copy is re-replicated.

   Queens

      The code name for the seventeenth release of OpenStack. The
      design summit will take place in Sydney, Australia. The release
      is named after the Queens Pound river in the South Coast region
      of New South Wales.

   Quick EMUlator (QEMU)

      QEMU is a generic and open source machine emulator and
      virtualizer.
      One of the hypervisors supported by OpenStack, generally used
      for development purposes.

   quota

      In Compute and Block Storage, the ability to set resource limits
      on a per-project basis.

R
~

.. glossary::

   RabbitMQ

      The default message queue software used by OpenStack.

   Rackspace Cloud Files

      Released as open source by Rackspace in 2010; the basis for
      Object Storage.

   RADOS Block Device (RBD)

      Ceph component that enables a Linux block device to be striped
      over multiple distributed data stores.

   radvd

      The router advertisement daemon, used by the Compute VLAN
      manager and FlatDHCP manager to provide routing services for VM
      instances.

   rally

      Codename for the :term:`Benchmark service<Benchmark service (rally)>`.

   RAM filter

      The Compute setting that enables or disables RAM
      overcommitment.

   RAM overcommit

      The ability to start new VM instances based on the actual memory
      usage of a host, as opposed to basing the decision on the amount of
      RAM each running instance thinks it has available. Also known as
      memory overcommit.

   rate limit

      Configurable option within Object Storage to limit database
      writes on a per-account and/or per-container basis.

   raw

      One of the VM image disk formats supported by Image service; an
      unstructured disk image.

   rebalance

      The process of distributing Object Storage partitions across all
      drives in the ring; used during initial ring creation and after ring
      reconfiguration.

   reboot

      Either a soft or hard reboot of a server. With a soft reboot,
      the operating system is signaled to restart, which enables a graceful
      shutdown of all processes. A hard reboot is the equivalent of power
      cycling the server. The virtualization platform should ensure that the
      reboot action has completed successfully, even in cases in which the
      underlying domain/VM is paused or halted/stopped.

   rebuild

      Removes all data on the server and replaces it with the
      specified image. Server ID and IP addresses remain the same.

   Recon

      An Object Storage component that collects meters.

   record

      Belongs to a particular domain and is used to specify
      information about the domain.
      There are several types of DNS records. Each record type contains
      particular information used to describe the purpose of that record.
      Examples include mail exchange (MX) records, which specify the mail
      server for a particular domain; and name server (NS) records, which
      specify the authoritative name servers for a domain.

   record ID

      A number within a database that is incremented each time a
      change is made. Used by Object Storage when replicating.

   Red Hat Enterprise Linux (RHEL)

      A Linux distribution that is compatible with OpenStack.

   reference architecture

      A recommended architecture for an OpenStack cloud.

   region

      A discrete OpenStack environment with dedicated API endpoints
      that typically shares only the Identity (keystone) with other
      regions.

   registry

      Alternative term for the Image service registry.

   registry server

      An Image service that provides VM image metadata information to
      clients.

   Reliable, Autonomic Distributed Object Store
      (RADOS)

      A collection of components that provides object storage within
      Ceph. Similar to OpenStack Object Storage.

   Remote Procedure Call (RPC)

      The method used by the Compute RabbitMQ for intra-service
      communications.

   replica

      Provides data redundancy and fault tolerance by creating copies
      of Object Storage objects, accounts, and containers so that they are
      not lost when the underlying storage fails.

   replica count

      The number of replicas of the data in an Object Storage
      ring.

   replication

      The process of copying data to a separate physical device for
      fault tolerance and performance.

   replicator

      The Object Storage back-end process that creates and manages
      object replicas.

   request ID

      Unique ID assigned to each request sent to Compute.

   rescue image

      A special type of VM image that is booted when an instance is
      placed into rescue mode. Allows an administrator to mount the file
      systems for an instance to correct the problem.

   resize

      Converts an existing server to a different flavor, which scales
      the server up or down. The original server is saved to enable rollback
      if a problem occurs. All resizes must be tested and explicitly
      confirmed, at which time the original server is removed.

   RESTful

      A kind of web service API that uses REST, or Representational
      State Transfer. REST is the style of architecture for hypermedia
      systems that is used for the World Wide Web.

   ring

      An entity that maps Object Storage data to partitions. A
      separate ring exists for each service, such as account, object, and
      container.

   ring builder

      Builds and manages rings within Object Storage, assigns
      partitions to devices, and pushes the configuration to other storage
      nodes.

   Rocky

      The code name for the eightteenth release of OpenStack. The
      design summit will take place in Vancouver, Kanada. The release
      is named after the Rocky Mountains.

   role

      A personality that a user assumes to perform a specific set of
      operations. A role includes a set of rights and privileges. A user
      assuming that role inherits those rights and privileges.

   Role Based Access Control (RBAC)

      Provides a predefined list of actions that the user can perform,
      such as start or stop VMs, reset passwords, and so on. Supported in
      both Identity and Compute and can be configured using the dashboard.

   role ID

      Alphanumeric ID assigned to each Identity service role.

   Root Cause Analysis (RCA) service (Vitrage)

      OpenStack project that aims to organize, analyze and visualize OpenStack
      alarms and events, yield insights regarding the root cause of problems
      and deduce their existence before they are directly detected.

   rootwrap

      A feature of Compute that allows the unprivileged "nova" user to
      run a specified list of commands as the Linux root user.

   round-robin scheduler

      Type of Compute scheduler that evenly distributes instances
      among available hosts.

   router

      A physical or virtual network device that passes network
      traffic between different networks.

   routing key

      The Compute direct exchanges, fanout exchanges, and topic
      exchanges use this key to determine how to process a message;
      processing varies depending on exchange type.

   RPC driver

      Modular system that allows the underlying message queue software
      of Compute to be changed. For example, from RabbitMQ to ZeroMQ or
      Qpid.

   rsync

      Used by Object Storage to push object replicas.

   RXTX cap

      Absolute limit on the amount of network traffic a Compute VM
      instance can send and receive.

   RXTX quota

      Soft limit on the amount of network traffic a Compute VM
      instance can send and receive.

S
~

.. glossary::

   sahara

      Codename for the :term:`Data Processing service<Data Processing
      service (sahara)>`.

   SAML assertion

      Contains information about a user as provided by the identity
      provider. It is an indication that a user has been authenticated.

   scheduler manager

      A Compute component that determines where VM instances should
      start. Uses modular design to support a variety of scheduler
      types.

   scoped token

      An Identity service API access token that is associated with a
      specific project.

   scrubber

      Checks for and deletes unused VMs; the component of Image
      service that implements delayed delete.

   secret key

      String of text known only by the user; used along with an access
      key to make requests to the Compute API.

   secure boot

      Process whereby the system firmware validates the authenticity of
      the code involved in the boot process.

   secure shell (SSH)

      Open source tool used to access remote hosts through an
      encrypted communications channel, SSH key injection is supported by
      Compute.

   security group

      A set of network traffic filtering rules that are applied to a
      Compute instance.

   segmented object

      An Object Storage large object that has been broken up into
      pieces. The re-assembled object is called a concatenated
      object.

   self-service

      For IaaS, ability for a regular (non-privileged) account to
      manage a virtual infrastructure component such as networks without
      involving an administrator.

   SELinux

      Linux kernel security module that provides the mechanism for
      supporting access control policies.

   senlin

      Code name for the :term:`Clustering service
      <Clustering service (senlin)>`.

   server

      Computer that provides explicit services to the client software
      running on that system, often managing a variety of computer
      operations.
      A server is a VM instance in the Compute system. Flavor and
      image are requisite elements when creating a server.

   server image

      Alternative term for a VM image.

   server UUID

      Unique ID assigned to each guest VM instance.

   service

      An OpenStack service, such as Compute, Object Storage, or Image
      service. Provides one or more endpoints through which users can access
      resources and perform operations.

   service catalog

      Alternative term for the Identity service catalog.

   Service Function Chain (SFC)

      For a given service, SFC is the abstracted view of the required
      service functions and the order in which they are to be applied.

   service ID

      Unique ID assigned to each service that is available in the
      Identity service catalog.

   Service Level Agreement (SLA)

      Contractual obligations that ensure the availability of a
      service.

   service project

      Special project that contains all services that are listed in the
      catalog.

   service provider

      A system that provides services to other system entities. In
      case of federated identity, OpenStack Identity is the service
      provider.

   service registration

      An Identity service feature that enables services, such as
      Compute, to automatically register with the catalog.

   service token

      An administrator-defined token used by Compute to communicate
      securely with the Identity service.

   session back end

      The method of storage used by horizon to track client sessions,
      such as local memory, cookies, a database, or memcached.

   session persistence

      A feature of the load-balancing service. It attempts to force
      subsequent connections to a service to be redirected to the same node
      as long as it is online.

   session storage

      A horizon component that stores and tracks client session
      information. Implemented through the Django sessions framework.

   share

      A remote, mountable file system in the context of the :term:`Shared
      File Systems service<Shared File Systems service (manila)>`. You can
      mount a share to, and access a share from, several hosts by several
      users at a time.

   share network

      An entity in the context of the :term:`Shared File Systems
      service<Shared File Systems service (manila)>` that encapsulates
      interaction with the Networking service. If the driver you selected
      runs in the mode requiring such kind of interaction, you need to
      specify the share network to create a share.

   Shared File Systems API

      A Shared File Systems service that provides a stable RESTful API.
      The service authenticates and routes requests throughout the Shared
      File Systems service. There is python-manilaclient to interact with
      the API.

   Shared File Systems service (manila)

      The service that provides a set of services for
      management of shared file systems in a multi-project cloud
      environment, similar to how OpenStack provides block-based storage
      management through the OpenStack :term:`Block Storage service<Block
      Storage service (cinder)>` project.
      With the Shared File Systems service, you can create a remote file
      system and mount the file system on your instances. You can also
      read and write data from your instances to and from your file system.

   shared IP address

      An IP address that can be assigned to a VM instance within the
      shared IP group. Public IP addresses can be shared across multiple
      servers for use in various high-availability scenarios. When an IP
      address is shared to another server, the cloud network restrictions
      are modified to enable each server to listen to and respond on that IP
      address. You can optionally specify that the target server network
      configuration be modified. Shared IP addresses can be used with many
      standard heartbeat facilities, such as keepalive, that monitor for
      failure and manage IP failover.

   shared IP group

      A collection of servers that can share IPs with other members of
      the group. Any server in a group can share one or more public IPs with
      any other server in the group. With the exception of the first server
      in a shared IP group, servers must be launched into shared IP groups.
      A server may be a member of only one shared IP group.

   shared storage

      Block storage that is simultaneously accessible by multiple
      clients, for example, NFS.

   Sheepdog

      Distributed block storage system for QEMU, supported by
      OpenStack.

   Simple Cloud Identity Management (SCIM)

      Specification for managing identity in the cloud, currently
      unsupported by OpenStack.

   Simple Protocol for Independent Computing Environments (SPICE)

      SPICE provides remote desktop access to guest virtual machines. It
      is an alternative to VNC. SPICE is supported by OpenStack.

   Single-root I/O Virtualization (SR-IOV)

      A specification that, when implemented by a physical PCIe
      device, enables it to appear as multiple separate PCIe devices. This
      enables multiple virtualized guests to share direct access to the
      physical device, offering improved performance over an equivalent
      virtual device. Currently supported in OpenStack Havana and later
      releases.

   SmokeStack

      Runs automated tests against the core OpenStack API; written in
      Rails.

   snapshot

      A point-in-time copy of an OpenStack storage volume or image.
      Use storage volume snapshots to back up volumes. Use image snapshots
      to back up data, or as "gold" images for additional servers.

   soft reboot

      A controlled reboot where a VM instance is properly restarted
      through operating system commands.

   Software Development Lifecycle Automation service (solum)

      OpenStack project that aims to make cloud services easier to
      consume and integrate with application development process
      by automating the source-to-image process, and simplifying
      app-centric deployment.

   Software-defined networking (SDN)

      Provides an approach for network administrators to manage computer
      network services through abstraction of lower-level functionality.

   SolidFire Volume Driver

      The Block Storage driver for the SolidFire iSCSI storage
      appliance.

   solum

      Code name for the :term:`Software Development Lifecycle Automation
      service <Software Development Lifecycle Automation service (solum)>`.

   spread-first scheduler

      The Compute VM scheduling algorithm that attempts to start a new
      VM on the host with the least amount of load.

   SQLAlchemy

      An open source SQL toolkit for Python, used in OpenStack.

   SQLite

      A lightweight SQL database, used as the default persistent
      storage method in many OpenStack services.

   stack

      A set of OpenStack resources created and managed by the
      Orchestration service according to a given template (either an
      AWS CloudFormation template or a Heat Orchestration
      Template (HOT)).

   StackTach

      Community project that captures Compute AMQP communications;
      useful for debugging.

   static IP address

      Alternative term for a fixed IP address.

   StaticWeb

      WSGI middleware component of Object Storage that serves
      container data as a static web page.

   storage back end

      The method that a service uses for persistent storage, such as
      iSCSI, NFS, or local disk.

   storage manager

      A XenAPI component that provides a pluggable interface to
      support a wide variety of persistent storage back ends.

   storage manager back end

      A persistent storage method supported by XenAPI, such as iSCSI
      or NFS.

   storage node

      An Object Storage node that provides container services, account
      services, and object services; controls the account databases,
      container databases, and object storage.

   storage services

      Collective name for the Object Storage object services,
      container services, and account services.

   strategy

      Specifies the authentication source used by Image service or
      Identity. In the Database service, it refers to the extensions
      implemented for a data store.

   subdomain

      A domain within a parent domain. Subdomains cannot be
      registered. Subdomains enable you to delegate domains. Subdomains can
      themselves have subdomains, so third-level, fourth-level, fifth-level,
      and deeper levels of nesting are possible.

   subnet

      Logical subdivision of an IP network.

   SUSE Linux Enterprise Server (SLES)

      A Linux distribution that is compatible with OpenStack.

   suspend

      The VM instance is paused and its state is saved to disk of the host.

   swap

      Disk-based virtual memory used by operating systems to provide
      more memory than is actually available on the system.

   swauth

      An authentication and authorization service for Object Storage,
      implemented through WSGI middleware; uses Object Storage itself as the
      persistent backing store.

   swift

      Codename for OpenStack :term:`Object Storage service<Object
      Storage service (swift)>`.

   swift All in One (SAIO)

      Creates a full Object Storage development environment within a
      single VM.

   swift middleware

      Collective term for Object Storage components that provide
      additional functionality.

   swift proxy server

      Acts as the gatekeeper to Object Storage and is responsible for
      authenticating the user.

   swift storage node

      A node that runs Object Storage account, container, and object
      services.

   sync point

      Point in time since the last container and accounts database
      sync among nodes within Object Storage.

   sysadmin

      One of the default roles in the Compute RBAC system. Enables a
      user to add other users to a project, interact with VM images that are
      associated with the project, and start and stop VM instances.

   system usage

      A Compute component that, along with the notification system,
      collects meters and usage information. This information can be used
      for billing.

T
~

.. glossary::

   tacker

      Code name for the :term:`NFV Orchestration service <NFV Orchestration
      service (tacker)>`

   Telemetry service (telemetry)

      The OpenStack project which collects measurements of the utilization
      of the physical and virtual resources comprising deployed clouds,
      persists this data for subsequent retrieval and analysis, and triggers
      actions when defined criteria are met.

   TempAuth

      An authentication facility within Object Storage that enables
      Object Storage itself to perform authentication and authorization.
      Frequently used in testing and development.

   Tempest

      Automated software test suite designed to run against the trunk
      of the OpenStack core project.

   TempURL

      An Object Storage middleware component that enables creation of
      URLs for temporary object access.

   tenant

      A group of users; used to isolate access to Compute resources.
      An alternative term for a project.

   Tenant API

      An API that is accessible to projects.

   tenant endpoint

      An Identity service API endpoint that is associated with one or
      more projects.

   tenant ID

      An alternative term for :term:`project ID`.

   token

      An alpha-numeric string of text used to access OpenStack APIs
      and resources.

   token services

      An Identity service component that manages and validates tokens
      after a user or project has been authenticated.

   tombstone

      Used to mark Object Storage objects that have been
      deleted; ensures that the object is not updated on another node after
      it has been deleted.

   topic publisher

      A process that is created when a RPC call is executed; used to
      push the message to the topic exchange.

   Torpedo

      Community project used to run automated tests against the
      OpenStack API.

   transaction ID

      Unique ID assigned to each Object Storage request; used for
      debugging and tracing.

   transient

      Alternative term for non-durable.

   transient exchange

      Alternative term for a non-durable exchange.

   transient message

      A message that is stored in memory and is lost after the server
      is restarted.

   transient queue

      Alternative term for a non-durable queue.

   TripleO

      OpenStack-on-OpenStack program. The code name for the
      OpenStack Deployment program.

   trove

      Codename for OpenStack :term:`Database service <Database service
      (trove)>`.

   trusted platform module (TPM)

      Specialized microprocessor for incorporating cryptographic keys
      into devices for authenticating and securing a hardware platform.

U
~

.. glossary::

   Ubuntu

      A Debian-based Linux distribution.

   unscoped token

      Alternative term for an Identity service default token.

   updater

      Collective term for a group of Object Storage components that
      processes queued and failed updates for containers and objects.

   user

      In OpenStack Identity,  entities represent individual API
      consumers and are owned by a specific domain. In OpenStack Compute,
      a user can be associated with roles, projects, or both.

   user data

      A blob of data that the user can specify when they launch
      an instance. The instance can access this data through the
      metadata service or config drive.
      Commonly used to pass a shell script that the instance runs on boot.

   User Mode Linux (UML)

      An OpenStack-supported hypervisor.

V
~

.. glossary::

   VIF UUID

      Unique ID assigned to each Networking VIF.

   Virtual Central Processing Unit (vCPU)

      Subdivides physical CPUs. Instances can then use those
      divisions.

   Virtual Disk Image (VDI)

      One of the VM image disk formats supported by Image
      service.

   Virtual Extensible LAN (VXLAN)

      A network virtualization technology that attempts to reduce the
      scalability problems associated with large cloud computing
      deployments. It uses a VLAN-like encapsulation technique to
      encapsulate Ethernet frames within UDP packets.

   Virtual Hard Disk (VHD)

      One of the VM image disk formats supported by Image
      service.

   virtual IP address (VIP)

      An Internet Protocol (IP) address configured on the load
      balancer for use by clients connecting to a service that is load
      balanced. Incoming connections are distributed to back-end nodes based
      on the configuration of the load balancer.

   virtual machine (VM)

      An operating system instance that runs on top of a hypervisor.
      Multiple VMs can run at the same time on the same physical
      host.

   virtual network

      An L2 network segment within Networking.

   Virtual Network Computing (VNC)

      Open source GUI and CLI tools used for remote console access to
      VMs. Supported by Compute.

   Virtual Network InterFace (VIF)

      An interface that is plugged into a port in a Networking
      network. Typically a virtual network interface belonging to a
      VM.

   virtual networking

      A generic term for virtualization of network functions
      such as switching, routing, load balancing, and security using
      a combination of VMs and overlays on physical network
      infrastructure.

   virtual port

      Attachment point where a virtual interface connects to a virtual
      network.

   virtual private network (VPN)

      Provided by Compute in the form of cloudpipes, specialized
      instances that are used to create VPNs on a per-project basis.

   virtual server

      Alternative term for a VM or guest.

   virtual switch (vSwitch)

      Software that runs on a host or node and provides the features
      and functions of a hardware-based network switch.

   virtual VLAN

      Alternative term for a virtual network.

   VirtualBox

      An OpenStack-supported hypervisor.

   Vitrage

      Code name for the :term:`Root Cause Analysis service <Root Cause
      Analysis (RCA) service (Vitrage)>`.

   VLAN manager

      A Compute component that provides dnsmasq and radvd and sets up
      forwarding to and from cloudpipe instances.

   VLAN network

      The Network Controller provides virtual networks to enable
      compute servers to interact with each other and with the public
      network. All machines must have a public and private network
      interface. A VLAN network is a private network interface, which is
      controlled by the ``vlan_interface`` option with VLAN
      managers.

   VM disk (VMDK)

      One of the VM image disk formats supported by Image
      service.

   VM image

      Alternative term for an image.

   VM Remote Control (VMRC)

      Method to access VM instance consoles using a web browser.
      Supported by Compute.

   VMware API

      Supports interaction with VMware products in Compute.

   VMware NSX Neutron plug-in

      Provides support for VMware NSX in Neutron.

   VNC proxy

      A Compute component that provides users access to the consoles
      of their VM instances through VNC or VMRC.

   volume

      Disk-based data storage generally represented as an iSCSI target
      with a file system that supports extended attributes; can be
      persistent or ephemeral.

   Volume API

      Alternative name for the Block Storage API.

   volume controller

      A Block Storage component that oversees and coordinates storage
      volume actions.

   volume driver

      Alternative term for a volume plug-in.

   volume ID

      Unique ID applied to each storage volume under the Block Storage
      control.

   volume manager

      A Block Storage component that creates, attaches, and detaches
      persistent storage volumes.

   volume node

      A Block Storage node that runs the cinder-volume daemon.

   volume plug-in

      Provides support for new and specialized types of back-end
      storage for the Block Storage volume manager.

   volume worker

      A cinder component that interacts with back-end storage to manage
      the creation and deletion of volumes and the creation of compute
      volumes, provided by the cinder-volume daemon.

   vSphere

      An OpenStack-supported hypervisor.

W
~

.. glossary::

   Watcher

      Code name for the :term:`Infrastructure Optimization service
      <Infrastructure Optimization service (watcher)>`.

   weight

      Used by Object Storage devices to determine which storage
      devices are suitable for the job. Devices are weighted by size.

   weighted cost

      The sum of each cost used when deciding where to start a new VM
      instance in Compute.

   weighting

      A Compute process that determines the suitability of the VM
      instances for a job for a particular host. For example, not enough RAM
      on the host, too many CPUs on the host, and so on.

   worker

      A daemon that listens to a queue and carries out tasks in
      response to messages. For example, the cinder-volume worker manages volume
      creation and deletion on storage arrays.

   Workflow service (mistral)

      The OpenStack service that provides a simple YAML-based language to
      write workflows (tasks and transition rules) and a service that
      allows to upload them, modify, run them at scale and in a highly
      available manner, manage and monitor workflow execution state and state
      of individual tasks.

X
~

.. glossary::

   X.509

      X.509 is the most widely used standard for defining digital
      certificates. It is a data structure that contains the subject
      (entity) identifiable information such as its name along with
      its public key. The certificate can contain a few other
      attributes as well depending upon the version. The most recent
      and standard version of X.509 is v3.

   Xen

      Xen is a hypervisor using a microkernel design, providing
      services that allow multiple computer operating systems to
      execute on the same computer hardware concurrently.

   Xen API

      The Xen administrative API, which is supported by
      Compute.

   Xen Cloud Platform (XCP)

      An OpenStack-supported hypervisor.

   Xen Storage Manager Volume Driver

      A Block Storage volume plug-in that enables communication with
      the Xen Storage Manager API.

   XenServer

      An OpenStack-supported hypervisor.

   XFS

      High-performance 64-bit file system created by Silicon
      Graphics. Excels in parallel I/O operations and data
      consistency.

Z
~

.. glossary::

   zaqar

      Codename for the :term:`Message service <Message service (zaqar)>`.

   ZeroMQ

      Message queue software supported by OpenStack. An alternative to
      RabbitMQ. Also spelled 0MQ.

   Zuul

      Tool used in OpenStack development to ensure correctly ordered
      testing of changes in parallel.
