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

Database Management
===================

The default metadata driver for Glance uses sqlalchemy, which implies there
exists a backend database which must be managed. The ``glance-manage`` binary
provides a set of commands for making this easier.

The commands should be executed as a subcommand of 'db':

    glance-manage db <cmd> <args>


Sync the Database
-----------------

    glance-manage db sync [VERSION]

Place an existing database under migration control and upgrade it to the
specified VERSION or to the latest migration level if VERSION is not specified.

.. note:: Prior to Ocata release the database version was a numeric value.
    For example: for the Newton release, the latest migration level was ``44``.
    Starting with Ocata, database version will be a revision name
    corresponding to the latest migration included in the release. For the
    Ocata release, there is only one database migration and it is identified
    by revision ``ocata01``. So, the database version for Ocata release would
    be ``ocata01``.

    However, with the introduction of zero-downtime upgrades, database version
    will be a composite version including both expand and contract revisions.
    To achieve zero-downtime upgrades, we split the ``ocata01`` migration into
    ``ocata_expand01`` and ``ocata_contract01``. During the upgrade process,
    the database would initially be marked with ``ocata_expand01`` and
    eventually after completing the full upgrade process, the database will be
    marked with ``ocata_contract01``. So, instead of one database version, an
    operator will see a composite database version that will have both expand
    and contract versions. A database will be considered at Ocata version only
    when both expand and contract revisions are at the latest revisions
    possible. For a successful Ocata rolling upgrade, the database should be
    marked with both ``ocata_expand01``, ``ocata_contract01``.

Determining the Database Version
--------------------------------

    glance-manage db version

This will print the current migration level of a Glance database.


Upgrading an Existing Database
------------------------------

    glance-manage db upgrade [VERSION]

This will take an existing database and upgrade it to the specified VERSION.


Expanding the Database
----------------------

    glance-manage db expand

This will run the expansion phase of a rolling upgrade process.
Database expansion should be run as the first step in the rolling upgrade
process before any new services are started.


Migrating the Data
------------------

    glance-manage db migrate

This will run the data migrate phase of a rolling upgrade process.
Database migration should be run after database expansion and before
database contraction has been performed.


Contracting the Database
------------------------

    glance-manage db contract

This will run the contraction phase of a rolling upgrade process.
Database contraction should be run as the last step of the rolling upgrade
process after all old services are upgraded to new ones.

Downgrading an Existing Database
--------------------------------

Upgrades involve complex operations and can fail. Before attempting any
upgrade, you should make a full database backup of your production data. As of
Kilo, database downgrades are not supported, and the only method available to
get back to a prior database version is to restore from backup[1].

[1]: http://docs.openstack.org/ops-guide/ops-upgrades.html#perform-a-backup
