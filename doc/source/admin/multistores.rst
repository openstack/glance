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

.. note:: The Multi Store feature is introduced as EXPERIMENTAL in Rocky and
          its use in production systems is currently **not supported**.
          However we encourage people to use this feature for testing
          purposes and report the issues so that we can make it stable and
          fully supported in Stein release.

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
    ``swift``, ``cinder``, ``sheepdog`` or ``vmware``. In order to have
    multiple stores operator can specify multiple key:value separated by comma.

    .. code-block:: ini

         [DEFAULT]
         enabled_backends = fast:rbd, cheap:rbd, shared:file, reliable:file

    .. note:: Due to the special read only nature and characteristics of the
              http store we do not encourage nor support configuring multiple
              instances of http store even though it's possible.

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
       operator can add meaningful description about that store. This description
       is displayed in the GET /v2/info/stores response.

* For new image import workflow glance will reserve a ``os_staging`` file
  store identifier for staging the images data during staging operation. This
  should be added by default in ``glance-api.conf`` as shown below:

  .. code-block:: ini

        [os_staging]
        filesystem_store_datadir = /opt/stack/data/glance/os_staging/
        store_description = "Filesystem store for staging purpose"
