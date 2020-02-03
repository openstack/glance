..
      Licensed under the Apache License, Version 2.0 (the "License"); you may
      not use this file except in compliance with the License. You may obtain
      a copy of the License at

          http://www.apache.org/licenses/LICENSE-2.0

      Unless required by applicable law or agreed to in writing, software
      distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
      WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
      License for the specific language governing permissions and limitations
      under the License.

.. _multi_stores:

Multi Store Support
===================

.. note:: The Multi Store feature was introduced as EXPERIMENTAL in Rocky
          and is now fully supported in the Train release.

Scope of this document
----------------------

This page describes how to enable multiple stores in glance.

Prerequisites
-------------

* Glance version 17.0.0 or Later

* Glance Store Library 0.25.0 or Later

* Glance not using the Glance Registry

* Available backends

Procedure
---------

In this section, we discuss what configuration options are available to
operators to enable multiple stores support.

* in the ``[DEFAULT]`` options group:

  * ``enabled_backends`` must be set as a key:value pair where key
    represents the identifier for the store and value will be the type
    of the store. Valid values are one of ``file``, ``http``, ``rbd``,
    ``swift``, ``cinder`` or ``vmware``. In order to have multiple stores
    operator can specify multiple key:value separated by comma.

    .. warning::
       The store identifier prefix ``os_glance_`` is reserved.  If you
       define a store identifier with this prefix, the glance service will
       refuse to start.

    The http store type is always treated by Glance as a read-only
    store.  This is indicated in the response to the ``/v2/stores/info``
    call, where an http type store will have the attribute ``read-only:
    True`` in addition to the usual ``id`` and ``description`` fields.

    .. code-block:: ini

         [DEFAULT]
         enabled_backends = fast:rbd, cheap:rbd, shared:file, reliable:file

* in the ``[glance_store]`` options group:

  * ``default_backend`` must be set to one of the identifier which are defined
    using ``enabled_backends`` option. If ``default_backend`` is not set or if
    it is not representing one of the valid store drivers then it will prevent
    glance api service from starting.

    .. code-block:: ini

         [glance_store]
         default_backend = fast

* For each of the store identifier defined in ``enabled_backends`` section
  operator needs to add a new config group which will define config options
  related to that particular store.

  .. code-block:: ini

        [shared]
        filesystem_store_datadir = /opt/stack/data/glance/shared_images/
        store_description = "Shared filesystem store"

        [reliable]
        filesystem_store_datadir = /opt/stack/data/glance/reliable
        store_description = "Reliable filesystem backend"

        [fast]
        store_description = "Fast rbd backend"
        rbd_store_chunk_size = 8
        rbd_store_pool = images
        rbd_store_user = admin
        rbd_store_ceph_conf = /etc/ceph/ceph.conf
        rados_connect_timeout = 0

        [cheap]
        store_description = "Cheap rbd backend"
        rbd_store_chunk_size = 8
        rbd_store_pool = images
        rbd_store_user = admin
        rbd_store_ceph_conf = /etc/ceph/ceph1.conf
        rados_connect_timeout = 0

  .. note ::
       ``store_description`` is a new config option added to each store where
       operator can add meaningful description about that store. This
       description is displayed in the GET /v2/info/stores response.

Store Configuration Issues
~~~~~~~~~~~~~~~~~~~~~~~~~~

Please keep the following points in mind.

* Due to the special read only nature and characteristics of the
  http store type, configuring multiple instances of the http type
  store **is not supported**.  (This constraint is not currently
  enforced in the code.)

* Each instance of the filesystem store **must** have a different value
  for the ``filesystem_store_datadir``.  (This constraint is not currently
  enforced in the code.)


Reserved Stores
---------------

With the Train release, Glance is beginning a transition from its former
reliance upon local directories for temporary data storage to the ability
to use backend stores accessed via the glance_store library.

In the Train release, the use of backend stores for this purpose is optional
**unless you are using the multi store support feature**.  Since you are
reading this document, this situation most likely applies to you.

.. note::
   Currently, only the filesystem store type is supported as a Glance
   reserved store.

The reserved stores are not intended to be exposed to end users.  Thus
they will not appear in the response to the store discovery call, GET
/v2/info/stores, or as values in the ``OpenStack-image-store-ids``
response header of the image-create call.

You do not get to select the name of a reserved store; these are defined
by Glance and begin with the prefix ``os_glance_``.  In the Train release,
you do not get to select the store type: all reserved stores must be of
type filesystem.

Currently, there are two reserved stores:

``os_glance_tasks_store``
    This store is used for the tasks engine.  It replaces the use of the
    DEPRECATED configuration option ``[task]/work_dir``.

``os_glance_staging_store``
    This store is used for the staging area for the interoperable image
    import process.  It replaces  the use of the DEPRECATED configuration
    option ``[DEFAULT]/node_staging_uri``.

.. note::
   If end user wants to retrieve all the available stores using
   ``CONF.enabled_backeds`` then he needs to remove reserved
   stores from that list explicitly.

Configuration
~~~~~~~~~~~~~

As mentioned above, you do not get to select the name or the type of
a reserved store (though we anticipate that you will be able configure
the store type in a future release).

The reserved stores *must* be of type filesystem.  Hence, you must
provide configuration for them in your ``glance-api.conf`` file.  You
do this by introducing a section in ``glance-api.conf`` for each reserved
store as follows:

.. code-block:: ini

    [os_glance_tasks_store]
    filesystem_store_datadir = /var/lib/glance/tasks_work_dir

    [os_glance_staging_store]
    filesystem_store_datadir = /var/lib/glance/staging

Since these are both filesystem stores (remember, you do not get a choice)
the only option you must configure for each is the
``filesystem_store_datadir``.  Please keep the following points in mind:

* The path for ``filesystem_store_datadir`` used for the reserved
  stores must be **different** from the path you are using for
  any filesystem store you have listed in ``enabled_backends``.
  Using the same data directory for multiple filesystem stores is
  **unsupported** and may lead to data loss.

* The identifiers for reserved stores, that is, ``os_glance_tasks_store``
  and ``os_glance_staging_store``, must **not** be included in the
  ``enabled_backends`` list.

* The reserved stores will **not** appear in the store discovery response
  or as values in the ``OpenStack-image-store-ids`` response header of
  the image-create call.

* The reserved stores will **not** be accepted as the value of the
  ``X-Image-Meta-Store`` header on the image-data-upload call or
  the image-import call.
