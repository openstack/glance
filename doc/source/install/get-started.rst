======================
Image service overview
======================

The Image service (glance) enables users to discover,
register, and retrieve virtual machine images. It offers a
:term:`REST <RESTful>` API that enables you to query virtual
machine image metadata and retrieve an actual image.
You can store virtual machine images made available through
the Image service in a variety of locations, from simple file
systems to object-storage systems like OpenStack Object Storage.

.. important::

   For simplicity, this guide describes configuring the Image service to
   use the ``file`` back end, which uploads and stores in a
   directory on the controller node hosting the Image service. By
   default, this directory is ``/var/lib/glance/images/``.

   Before you proceed, ensure that the controller node has at least
   several gigabytes of space available in this directory. Keep in
   mind that since the ``file`` back end is often local to a controller
   node, it is not typically suitable for a multi-node glance deployment.

   For information on requirements for other back ends, see
   `Configuration Reference <../configuration/index.html>`__.

The OpenStack Image service is central to Infrastructure-as-a-Service
(IaaS). It accepts API requests for disk or server images, and
metadata definitions from end users or OpenStack Compute
components. It also supports the storage of disk or server images on
various repository types, including OpenStack Object Storage.

A number of periodic processes run on the OpenStack Image service to
support caching. Replication services ensure consistency and
availability through the cluster. Other periodic processes include
auditors, updaters, and reapers.

The OpenStack Image service includes the following components:

glance-api
  Accepts Image API calls for image discovery, retrieval, and storage.

glance-registry
  Stores, processes, and retrieves metadata about images. Metadata
  includes items such as size and type.

  .. warning::

     The registry is a private internal service meant for use by
     OpenStack Image service. Do not expose this service to users.

  .. include:: ../deprecate-registry.inc

Database
  Stores image metadata and you can choose your database depending on
  your preference. Most deployments use MySQL or SQLite.

Storage repository for image files
  Various repository types are supported including normal file
  systems (or any filesystem mounted on the glance-api controller
  node), Object Storage, RADOS block devices, VMware datastore,
  and HTTP. Note that some repositories will only support read-only
  usage.

Metadata definition service
  A common API for vendors, admins, services, and users to meaningfully
  define their own custom metadata. This metadata can be used on
  different types of resources like images, artifacts, volumes,
  flavors, and aggregates. A definition includes the new property's key,
  description, constraints, and the resource types which it can be
  associated with.
