..
      Copyright 2012 OpenStack Foundation
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

.. _legacy-database-management:

Legacy Database Management
==========================

.. note::
   This page applies only to Glance releases prior to Ocata.  From Ocata
   onward, please see :ref:`database-management`.

The default metadata driver for Glance uses sqlalchemy, which implies there
exists a backend database which must be managed. The ``glance-manage`` binary
provides a set of commands for making this easier.

The commands should be executed as a subcommand of 'db'::

    glance-manage db <cmd> <args>


Sync the Database
-----------------
::

    glance-manage db sync <version> <current_version>

Place a database under migration control and upgrade,
creating it first if necessary.


Determining the Database Version
--------------------------------
::

    glance-manage db version

This will print the current migration level of a Glance database.


Upgrading an Existing Database
------------------------------
::

    glance-manage db upgrade <VERSION>

This will take an existing database and upgrade it to the specified VERSION.


Downgrading an Existing Database
--------------------------------

Upgrades involve complex operations and can fail. Before attempting any
upgrade, you should make a full database backup of your production data. As of
Kilo, database downgrades are not supported, and the only method available to
get back to a prior database version is to restore from backup[1].

[1]: https://wiki.openstack.org/wiki/OpsGuide/Operational_Upgrades#perform-a-backup
