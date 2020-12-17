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

  .. note::

     An OpenStack Community Goal in the Pike release was `Control Plane API
     endpoints deployment via WSGI`_.  As currently constituted, however,
     glance-api is **not suitable** to be run in such a configuration.  Instead
     we recommend that Glance be run in the traditional manner as a standalone
     server.  See the "Known Issues" section of the `Glance Release Notes`_ for
     the Pike and Queens releases for more information.

     .. _`Control Plane API endpoints deployment via WSGI`: https://governance.openstack.org/tc/goals/pike/deploy-api-in-wsgi.html
     .. _`Glance Release Notes`: https://docs.openstack.org/releasenotes/glance/index.html

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

Running Glance Under Python3
============================

You should always run Glance under whatever version of Python your
distribution of OpenStack specifies.

If you are building OpenStack yourself from source, Glance is currently
supported to run under Python2 (specifically, Python 2.7 or later).

Some deployment configuration is required if you wish to run Glance
under Python3.  Glance is tested with unit and functional tests running
Python 3.5.  The eventlet-based server that Glance runs, however, is
currently affected by a bug that prevents SSL handshakes from completing
(see `Bug #1482633 <https://bugs.launchpad.net/glance/+bug/1482633>`_).
Thus if you wish to run Glance under Python 3.5, you must deploy Glance in
such a way that SSL termination is handled by something like HAProxy before
calls reach Glance.
