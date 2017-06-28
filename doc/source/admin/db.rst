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

.. _database-management:

Database Management
===================

The default metadata driver for Glance uses `SQLAlchemy`_, which implies there
exists a backend database which must be managed. The ``glance-manage`` binary
provides a set of commands for making this easier.

The commands should be executed as a subcommand of 'db':

    glance-manage db <cmd> <args>

.. note::
   In the Ocata release (14.0.0), the database migration engine was changed
   from *SQLAlchemy Migrate* to *Alembic*.  This necessitated some changes in
   the ``glance-manage`` tool.  While the user interface has been kept as
   similar as possible, the ``glance-manage`` tool included with the Ocata and
   more recent releases is incompatible with the "legacy" tool.  If you are
   consulting these documents for information about the ``glance-manage`` tool
   in the Newton or earlier releases, please see the
   :ref:`legacy-database-management` page.

.. _`SQLAlchemy`: http://www.sqlalchemy.org/


Migration Scripts
-----------------

The migration scripts are stored in the directory:
``glance/db/sqlalchemy/alembic_migrations/versions``

As mentioned above, these scripts utilize the Alembic migration engine, which
was first introduced in the Ocata release.  All database migrations up through
the Liberty release are consolidated into one Alembic migration script named
``liberty_initial``.  Mitaka migrations are retained, but have been rewritten
for Alembic and named using the new naming convention.

A fresh Glance installation will apply the following
migrations:

* ``liberty-initial``
* ``mitaka01``
* ``mitaka02``
* ``ocata01``

.. note::

   The "old-style" migration scripts have been retained in their `current
   directory`_ in the Ocata release so that interested operators can correlate
   them with the new migrations.  This directory will be removed in future
   releases.

   In particular, the "old-style" script for the Ocata migration,
   `045_add_visibility.py`_ is retained for operators who are conversant in
   SQLAlchemy Migrate and are interested in comparing it with a "new-style"
   Alembic migration script.  The Alembic script, which is the one actually
   used to do the upgrade to Ocata, is
   `ocata01_add_visibility_remove_is_public.py`_.

.. _`current directory`: http://git.openstack.org/cgit/openstack/glance/tree/glance/db/sqlalchemy/migrate_repo/versions?h=stable/ocata
.. _`045_add_visibility.py`: http://git.openstack.org/cgit/openstack/glance/tree/glance/db/sqlalchemy/migrate_repo/versions/045_add_visibility.py?h=stable/ocata
.. _`ocata01_add_visibility_remove_is_public.py`: http://git.openstack.org/cgit/openstack/glance/tree/glance/db/sqlalchemy/alembic_migrations/versions/ocata01_add_visibility_remove_is_public.py?h=stable/ocata

Sync the Database
-----------------

    glance-manage db sync [VERSION]

Place an existing database under migration control and upgrade it to the
specified VERSION or to the latest migration level if VERSION is not specified.

.. note::

   Prior to Ocata release the database version was a numeric value.  For
   example: for the Newton release, the latest migration level was ``44``.
   Starting with Ocata, database version is a revision name corresponding to
   the latest migration included in the release. For the Ocata release, there
   is only one database migration and it is identified by revision
   ``ocata01``. So, the database version for Ocata release is ``ocata01``.

   This naming convention will change slightly with the introduction of
   zero-downtime upgrades, which is EXPERIMENTAL in Ocata, but is projected to
   be the official upgrade method beginning with the Pike release.  See
   :ref:`zero-downtime` below for more information.


Determining the Database Version
--------------------------------

    glance-manage db version

This will print the current migration level of a Glance database.


Upgrading an Existing Database
------------------------------

    glance-manage db upgrade [VERSION]

This will take an existing database and upgrade it to the specified VERSION.

.. _downgrades:

Downgrading an Existing Database
--------------------------------

Upgrades involve complex operations and can fail. Before attempting any
upgrade, you should make a full database backup of your production data. As of
Kilo, database downgrades are not supported, and the only method available to
get back to a prior database version is to restore from backup [1].

[1]: http://docs.openstack.org/ops-guide/ops-upgrades.html#perform-a-backup


.. _zero-downtime:

Zero-Downtime Database Upgrades
===============================

.. warning::
   This feature is EXPERIMENTAL in the Ocata release.  We encourage operators
   to try it out, but its use in production environments is currently NOT
   SUPPORTED.

A zero-downtime database upgrade enables true rolling upgrades of the Glance
nodes in your cloud's control plane.  At the appropriate point in the upgrade,
you can have a mixed deployment of release *n* (for example, Ocata) and release
*n-1* (for example, Newton) Glance nodes, take the *n-1* release nodes out of
rotation, allow them to drain, and then take them out of service permanently,
leaving all Glance nodes in your cloud at release *n*.

That's a rough sketch of how a rolling upgrade would work.  For full details,
see :ref:`rolling-upgrades`.

.. note::
   Downgrading a database is not supported.  See :ref:`downgrades` for more
   information.

The Expand-Migrate-Contract Cycle
---------------------------------

For Glance, a zero-downtime database upgrade has three phases:

1. **Expand**: in this phase, new columns, tables, indexes, or triggers are
   added to the database.

2. **Migrate**: in this phase, data is migrated to the new columns or tables.

3. **Contract**: in this phase, the "old" tables or columns (and any database
   triggers used during the migration), which are no longer in use, are removed
   from the database.

The above phases are abbreviated as an **E-M-C** database upgrade.

New Database Version Identifiers
--------------------------------

In order to perform zero-downtime upgrades, the version identifier of a
database becomes more complicated since it must reflect knowledge of what point
in the E-M-C cycle the upgrade has reached.  To make this evident, the
identifier explicitly contains 'expand' or 'contract' as part of its name.

Thus the ``ocata01`` migration (that is, the migration that's currently used in
the fully supported upgrade path) has two identifiers associated with it for
zero-downtime upgrades: ``ocata_expand01`` and ``ocata_contract01``.

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

In order to enable the E-M-C database upgrade cycle, and to enable Glance
rolling upgrades, the ``glance-manage`` tool has been augmented to include the
following operations.

Expanding the Database
----------------------

    glance-manage db expand

This will run the expansion phase of a rolling upgrade process.  Database
expansion should be run as the first step in the rolling upgrade process before
any new services are started.


Migrating the Data
------------------

    glance-manage db migrate

This will run the data migrate phase of a rolling upgrade process.  Database
migration should be run after database expansion but before any new services
are started.


Contracting the Database
------------------------

    glance-manage db contract

This will run the contraction phase of a rolling upgrade process.
Database contraction should be run as the last step of the rolling upgrade
process after all old services are upgraded to new ones.
