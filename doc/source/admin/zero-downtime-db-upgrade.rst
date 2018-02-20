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

.. _zero-downtime:

Zero-Downtime Database Upgrades
===============================

.. warning::
   This feature is EXPERIMENTAL in the Ocata, Pike and Queens releases.
   We encourage operators to try it out, but its use in production
   environments is currently NOT SUPPORTED.

A *zero-downtime database upgrade* enables true rolling upgrades of the Glance
nodes in your cloud's control plane.  At the appropriate point in the upgrade,
you can have a mixed deployment of release *n* (for example, Ocata) and release
*n-1* (for example, Newton) Glance nodes, take the *n-1* release nodes out of
rotation, allow them to drain, and then take them out of service permanently,
leaving all Glance nodes in your cloud at release *n*.

That's a rough sketch of how a rolling upgrade would work.  For full details,
see :ref:`rolling-upgrades`.

.. note::
   When we speak of a "database upgrade", we are simply talking about changing
   the database schema and its data from the version used in OpenStack release
   *n* (say, Pike) to the version used in OpenStack release *n+1* (say,
   Queens).  We are **not** talking about upgrading the database management
   software.

.. note::
   Downgrading a database is not supported.  See :ref:`downgrades` for more
   information.

The Expand-Migrate-Contract Cycle
---------------------------------

It's possible to characterize three phases of a database upgrade:

1. **Expand**: in this phase, new columns, tables, indexes, are added to the
   database.

2. **Migrate**: in this phase, data is migrated to the new columns or tables.

3. **Contract**: in this phase, the "old" tables or columns (which are no
   longer in use) are removed from the database.

The "legacy" Glance database migrations performed these phases as part of a
single monolithic upgrade script.  Currently, the Glance project creates a
separate script for each the three parts of the cycle.  We call such an
upgrade an **E-M-C** database migration.

Zero-Downtime Database Upgrade
------------------------------

The E-M-C strategy can be performed offline when Glance is not using the
database.  With some adjustments, however, the E-M-C strategy can be applied
online when the database is in use, making true rolling upgrades possible.

.. note::
   Don't forget that zero-downtime database upgrades are currently considered
   experimental and their use in production environments is NOT SUPPORTED.

A zero-downtime database upgrade takes place as part of a :ref:`rolling upgrade
strategy <rolling-upgrades>` for upgrading your entire Glance installation.  In
such a situation, you want to upgrade to release *n* of Glance (say, Queens)
while your release *n-1* API nodes are still running Pike.  To make this
possible, in the **Expand** phase, database triggers can be added to the
database to keep the data in "old" and "new" columns synchronized.  Likewise,
after all data has been migrated and all Glance nodes have been updated to
release *n* code, these triggers are deleted in the **Contract** phase.

.. note::
   Unlike the E-M-C scripts, database triggers are particular to each database
   technology.  That's why the Glance project currently provides experimental
   support only for MySQL.

New Database Version Identifiers
--------------------------------

In order to perform zero-downtime upgrades, the version identifier of a
database becomes more complicated since it must reflect knowledge of what point
in the E-M-C cycle the upgrade has reached.  To make this evident, the
identifier explicitly contains 'expand' or 'contract' as part of its name.

Thus the Ocata cycle migration has two identifiers associated with it:
``ocata_expand01`` and ``ocata_contract01``.

During the upgrade process, the database is initially marked with
``ocata_expand01``.  Eventually, after completing the full upgrade process, the
database will be marked with ``ocata_contract01``. So, instead of one database
version, an operator will see a composite database version that will have both
expand and contract versions.  A database will be considered at Ocata version
only when both expand and contract revisions are at the latest revisions.  For
a successful Ocata zero-downtime upgrade, for example, the database will be
marked with both ``ocata_expand01``, ``ocata_contract01``.

In the case in which there are multiple changes in a cycle, the database
version record would go through the following progression:

+-------+--------------------------------------+-------------------------+
| stage | database identifier                  |     comment             |
+=======+======================================+=========================+
|   E   | ``bexar_expand01``                   | upgrade begins          |
+-------+--------------------------------------+-------------------------+
|   E   | ``bexar_expand02``                   |                         |
+-------+--------------------------------------+-------------------------+
|   E   | ``bexar_expand03``                   |                         |
+-------+--------------------------------------+-------------------------+
|   M   | ``bexar_expand03``                   | bexar_migrate01 occurs  |
+-------+--------------------------------------+-------------------------+
|   M   | ``bexar_expand03``                   | bexar_migrate02 occurs  |
+-------+--------------------------------------+-------------------------+
|   M   | ``bexar_expand03``                   | bexar_migrate03 occurs  |
+-------+--------------------------------------+-------------------------+
|   C   | ``bexar_expand03, bexar_contract01`` |                         |
+-------+--------------------------------------+-------------------------+
|   C   | ``bexar_expand03, bexar_contract02`` |                         |
+-------+--------------------------------------+-------------------------+
|   C   | ``bexar_expand03, bexar_contract03`` | upgrade completed       |
+-------+--------------------------------------+-------------------------+

Database Upgrade
----------------

For offline database upgrades, the ``glance-manage`` tool still has the
``glance-manage db sync`` command.  This command will execute the expand,
migrate, and contract scripts for you, just as if they were contained in
a single script.

In order to enable zero-downtime database upgrades, the ``glance-manage`` tool
has been augmented to include the following operations so that you can
explicitly manage the upgrade.

.. warning::

     For MySQL, using the ``glance-manage db expand`` or
     ``glance-manage db contract`` command requires that
     you either grant your glance user ``SUPER`` privileges, or run
     ``set global log_bin_trust_function_creators=1;`` in mysql beforehand.

Expanding the Database
~~~~~~~~~~~~~~~~~~~~~~
::

    glance-manage db expand

This will run the expansion phase of a rolling upgrade process.  Database
expansion should be run as the first step in the rolling upgrade process before
any new services are started.


Migrating the Data
~~~~~~~~~~~~~~~~~~
::

    glance-manage db migrate

This will run the data migrate phase of a rolling upgrade process.  Database
migration should be run after database expansion but before any new services
are started.


Contracting the Database
~~~~~~~~~~~~~~~~~~~~~~~~
::

    glance-manage db contract

This will run the contraction phase of a rolling upgrade process.
Database contraction should be run as the last step of the rolling upgrade
process after all old services are upgraded to new ones.
