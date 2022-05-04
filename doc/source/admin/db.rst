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

Updating and Migrating the Database
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The default metadata driver for Glance uses `SQLAlchemy`_, which implies there
exists a backend database which must be managed. The ``glance-manage`` binary
provides a set of commands for making this easier.

The commands should be executed as a subcommand of 'db'::

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

.. _`current directory`: https://opendev.org/openstack/glance/src/branch/stable/ocata/glance/db/sqlalchemy/migrate_repo/versions
.. _`045_add_visibility.py`: https://opendev.org/openstack/glance/src/branch/stable/ocata/glance/db/sqlalchemy/migrate_repo/versions/045_add_visibility.py
.. _`ocata01_add_visibility_remove_is_public.py`: https://opendev.org/openstack/glance/src/branch/stable/ocata/glance/db/sqlalchemy/alembic_migrations/versions/ocata01_add_visibility_remove_is_public.py

Sync the Database
-----------------
::

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
   :ref:`zero-downtime` for more information.


Determining the Database Version
--------------------------------
::

    glance-manage db version

This will print the current migration level of a Glance database.


Upgrading an Existing Database
------------------------------
::

    glance-manage db upgrade [VERSION]

This will take an existing database and upgrade it to the specified VERSION.

.. _downgrades:

Downgrading an Existing Database
--------------------------------

Downgrading an existing database is **NOT SUPPORTED**.

Upgrades involve complex operations and can fail. Before attempting any
upgrade, you should make a full database backup of your production data. As of
the OpenStack Kilo release (April 2013), database downgrades are not supported,
and the only method available to get back to a prior database version is to
restore from backup.

Database Maintenance
~~~~~~~~~~~~~~~~~~~~

Like most OpenStack systems, Glance performs *soft* deletions when it deletes
records from its database.  Depending on usage patterns in your cloud, you may
occasionally want to actually remove such soft deleted table rows.  This
operation is called *purging* the database, and you can use the
``glance-manage`` tool to do this.

High-Level Database Architecture
--------------------------------

Roughly, what we've got in the glance database is an **images** table that
stores the image **id** and some other core image properties.  All the other
information about the image (for example: where the image data is stored in
the backend, what projects an image has been shared with, image tags, custom
image properties) is stored in other tables in which the **image id** is
a foreign key.

Because the **images** table keeps track of what image identifiers have been
issued, it must be treated differently from the other tables with respect to
purging the database.

.. note::
   Before the Rocky release (17.0.0), the **images** table was *not* treated
   differently, which made Glance vulnerable to `OSSN-0075
   <https://wiki.openstack.org/wiki/OSSN/OSSN-0075>`_, "Deleted Glance image
   IDs may be reassigned".  Please read through that OpenStack Security
   Note to understand the nature of the problem.

   Additionally, the Glance spec `Mitigate OSSN-0075
   <https://specs.openstack.org/openstack/glance-specs/specs/rocky/approved/glance/mitigate-ossn-0075.html>`_
   contains a discussion of the issue and explains the changes made to the
   ``glance-manage`` tool for the Rocky release.  The `Gerrit review of the
   spec <https://review.opendev.org/#/c/468179/>`_ contains an extensive
   discussion of several alternative approaches and will give you an idea of
   why the Glance team provided a "mitigation" instead of a fix.

Purging the Database
--------------------

You can use the ``glance-manage`` tool to purge the soft-deleted rows from
all tables *except* the images table::

   glance-manage db purge

This command takes two optional parameters:

--age_in_days NUM    Only purge rows that have been deleted for longer
                     than *NUM* days.  The default is 30 days.

--max_rows NUM       Purge a maximum of *NUM* rows from each table.
                     The default is 100. All deleted rows are purged if equals
                     -1


Purging the Images Table
------------------------

Remember that image identifiers are used by other OpenStack services that
require access to images.  These services expect that when an image is
requested by ID, they will receive the same data every time.  When the
**images** table is purged of its soft-deleted rows, Glance loses its
memory that those image IDs were ever mapped to some particular payload.
Thus, care must be taken in purging the **images** table.  We recommend
that it be done much less frequently than the "regular" purge operation.

Use the following command to purge the images table::

    glance-manage db purge_images_table

Be sure you have read and understood the implications of `OSSN-0075
<https://wiki.openstack.org/wiki/OSSN/OSSN-0075>`_ before you use this
command, which purges the soft-deleted rows from the images table.

It takes two optional parameters:

--age_in_days NUM    Only purge rows that have been deleted for longer
                     than *NUM* days.  The default is 180 days.

--max_rows NUM       Purge a maximum of *NUM* rows from the **images** table.
                     The default is 100. All deleted rows are purged if equals
                     -1

It is possible for this command to fail with an IntegrityError saying
something like "Cannot delete or update a parent row: a foreign key
constraint fails".  This can happen when you try to purge records from
the **images** table when related records have not yet been purged from
other tables.  The ``purge_images_table`` command should only be issued
after all related information has been purged using the "regular" ``purge``
command.
