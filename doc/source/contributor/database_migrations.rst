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

======================================================
Writing Database Migrations for Zero-Downtime Upgrades
======================================================

Beginning in Ocata, OpenStack Glance uses Alembic, which replaced SQLAlchemy
Migrate as the database migration engine. Moving to Alembic is particularly
motivated by the zero-downtime upgrade work. Refer to [GSPEC1]_ and [GSPEC2]_
for more information on zero-downtime upgrades in Glance and why a move to
Alembic was deemed necessary.

Stop right now and go read [GSPEC1]_ and [GSPEC2]_ if you haven't done so
already. Those documents explain the strategy Glance has approved for database
migrations, and we expect you to be familiar with them in what follows.  This
document focuses on the "how", but unless you understand the "what" and "why",
you'll be wasting your time reading this document.

Prior to Ocata, database migrations were conceived as monoliths.  Thus, they
did not need to carefully distinguish and manage database schema expansions,
data migrations, or database schema contractions. The modern database
migrations are more sensitive to the characteristics of changes being
attempted and thus we clearly identify three phases of a database migration:
(1) expand, (2) migrate, and (3) contract.  A developer modifying the Glance
database must supply a script for each of these phases.

Here's a quick reminder of what each phase entails.
For more information, see [GSPEC1]_.

Expand
  Expand migrations MUST be additive in nature. Expand migrations
  should be seen as the minimal set of schema changes required by the new
  services that can be applied while the old services are still running.
  Expand migrations should optionally include temporary database triggers that
  keep the old and new columns in sync. If a database change needs data to be
  migrated between columns, then temporary database triggers are required to
  keep the columns in sync while the data migrations are in-flight.

  .. note::
      Sometimes there could be an exception to the additive-only change
      strategy for expand phase. It is described more elaborately in [GSPEC1]_.
      Again, consider this as a last reminder to read [GSPEC1]_, if you haven't
      already done so.

Migrate
  Data migrations MUST NOT attempt any schema changes and only move existing
  data between old and new columns such that new services can start consuming
  the new tables and/or columns introduced by the expand migrations.

Contract
  Contract migrations usually include the remaining schema changes required by
  the new services that couldn't be applied during expand phase due to their
  incompatible nature with the old services. Any temporary database triggers
  added during the expand migrations MUST be dropped with contract migrations.


Alembic Migrations
==================
As mentioned earlier, starting in Ocata Glance database migrations must be
written for Alembic. All existing Glance migrations have been ported to
Alembic. They can be found here [GMIGS1]_.


Schema Migrations (Expand/Contract)
-----------------------------------

* All Glance schema migrations must reside in
  ``glance.db.sqlalchemy.alembic_migrations.versions`` package

* Every Glance schema migration must be a python module with the following
  structure

  .. code::

    """<docstring describing the migration>

    Revision ID: <unique revision id>
    Revises: <parent revision id>
    """

    <your imports here>

    revision = <unique revision id>
    down_revision = <parent revision id>
    depends_on = <id of dependent revision or None>

    def upgrade():
        <your schema changes here>


  Identifiers ``revision``, ``down_revision`` and ``depends_on`` are
  elaborated below.

* The ``revision`` identifier is a unique revision id for every migration.
  It must conform to one of the following naming schemes.

  All monolith migrations must conform to:

  .. code::

    <release name><two-digit sequence number per release>


  And, all expand/contract migrations must conform to:

  .. code::

    <release name>_[expand|contract]<two-digit sequence number per release>


  Example:

  .. code::

    Monolith migration: ocata01
    Expand migration: ocata_expand01
    Contract migration: ocata_contract01

  This name convention is devised with an intention to easily understand the
  migration sequence. While the ``<release name>`` mentions the release a
  migration belongs to, the ``<two-digit sequence number per release>`` helps
  identify the order of migrations within each release. For modern migrations,
  the ``[expand|contract]`` part of the revision id helps identify the
  revision branch a migration belongs to.

* The ``down_revision`` identifier MUST be specified for all Alembic migration
  scripts. It points to the previous migration (or ``revision`` in Alembic
  lingo) on which the current migration is based. This essentially
  establishes a migration sequence very much a like a singly linked list would
  (except that we use a ``previous`` link here instead of the more traditional
  ``next`` link.)

  The very first migration, ``liberty`` in our case, would have
  ``down_revision`` set to ``None``. All other migrations must point to the
  last migration in the sequence at the time of writing the migration.

  For example, Glance has two migrations in Mitaka, namely, ``mitaka01``
  and ``mitaka02``. The migration sequence for Mitaka should look like:

  .. code::

                 liberty
                    ^
                    |
                    |
                 mitaka01
                    ^
                    |
                    |
                 mitaka02

* The ``depends_on`` identifier helps establish dependencies between two
  migrations. If a migration ``X`` depends on running  migration ``Y`` first,
  then ``X`` is said to depend on ``Y``. This could be specified in the
  migration as shown below:

  .. code::

    revision = 'X'
    down_revision = 'W'
    depends_on = 'Y'

  Naturally, every migration depends on the migrations preceding it in the
  migration sequence. Hence, in a typical branch-less migration sequence,
  ``depends_on`` is of limited use. However, this could be useful for
  migration sequences with branches. We'll see more about this in the next
  section.

* All schema migration scripts must adhere to the naming convention
  mentioned below:

  .. code::

    <unique revision id>_<very brief description>.py

  Example:

  .. code::

    Monolith migration: ocata01_add_visibility_remove_is_public.py
    Expand migration: ocata_expand01_add_visibility.py
    Contract migration: ocata_contract01_remove_is_public.py


Dependency Between Contract and Expand Migrations
-------------------------------------------------

* To achieve zero-downtime upgrades, the Glance migration sequence has been
  branched into ``expand`` and ``contract`` branches. As the name suggests,
  the ``expand`` branch contains only the expand migrations and the
  ``contract`` branch contains only the contract migrations. As per the
  zero-downtime migration strategy, the expand migrations are run first
  followed by contract migrations. To establish this dependency, we make the
  contract migrations explicitly depend on their corresponding expand
  migrations. Thus, running contract migrations without running expansions is
  not possible.

  For example, the Community Images migration in Ocata includes the
  experimental E-M-C migrations. The expand migration is ``ocata_expand01``
  and the contract migration is ``ocata_contract01``. The dependency is
  established as below.

  .. code::

    revision = 'ocata_contract01'
    down_revision = 'mitaka02'
    depends_on = 'ocata_expand01'


  Every contract migration in Glance MUST depend on its corresponding expand
  migration. Thus, the current Glance migration sequence looks as shown below:

  .. code::

                              liberty
                                 ^
                                 |
                                 |
                             mitaka01
                                 ^
                                 |
                                 |
                             mitaka02
                                 ^
                                 |
                    +------------+------------+
                    |                         |
                    |                         |
             ocata_expand01 <------  ocata_contract01
                    ^                         ^
                    |                         |
                    |                         |
              pike_expand01 <------   pike_contract01


Data Migrations
---------------

* All Glance data migrations must reside in
  ``glance.db.sqlalchemy.alembic_migrations.data_migrations`` package.

* The data migrations themselves are not Alembic migration scripts. And, hence
  they don't require a unique revision id. However, they must adhere to a
  similar naming convention discussed above. That is:

  .. code::

    <release name>_migrate<two-digit sequence number per release>_<very brief description>.py

  Example:

  .. code::

    Data Migration: ocata_migrate01_community_images.py

* All data migrations modules must adhere to the following structure:

  .. code::

    def has_migrations(engine):
        <your code to determine whether or not there are any pending rows to be
        migrated>
        return <boolean>


    def migrate(engine):
        <your code to migrate rows in the database.>
        return <number of rows migrated>


NOTES
-----

* In Ocata and Pike, Glance required every database migration to include
  both monolithic and Expand-Migrate-Contract (E-M-C) style migrations.  In
  Queens, E-M-C migrations became the default and a monolithic migration
  script is no longer required.

  In Queens, the glance-manage tool was refactored so that the ``glance-manage
  db sync`` command runs the expand, migrate, and contract scripts "under
  the hood".  From the viewpoint of the operator, there is no difference
  between having a single monolithic script and having three scripts.

  Since we are using the same scripts for offline and online (zero-downtime)
  database upgrades, as a developer you have to pay attention in your scripts
  to determine whether you need to add/remove triggers in the expand/contract
  scripts.  See the changes to the ocata scripts in
  https://review.opendev.org/#/c/544792/ for an example of how to do this.

* Alembic is a database migration engine written for SQLAlchemy. So, any
  migration script written for SQLAlchemy Migrate should work with Alembic as
  well provided the structural differences above (primarily adding
  ``revision``, ``down_revision`` and ``depends_on``) are taken care of.
  Moreover, it maybe easier to do certain operations with Alembic.
  Refer to [ALMBC]_ for information on Alembic operations.

* A given database change may not require actions in each of the expand,
  migrate, contract phases, but nonetheless, we require a script for *each*
  phase for *every* change.  In the case where an action is not required, a
  ``no-op`` script, described below, MUST be used.

  For instance, if a database migration is completely contractive in nature,
  say removing a column, there won't be a need for expand and migrate
  operations. But, including a ``no-op`` expand and migrate scripts will make
  it explicit and also preserve the one-to-one correspondence between expand,
  migrate and contract scripts.

  A no-op expand/contract Alembic migration:

  .. code::


    """An example empty Alembic migration script

    Revision ID: foo02
    Revises: foo01
    """

    revision = foo02
    down_revision = foo01

    def upgrade():
        pass


  A no-op migrate script:

  .. code::

    """An example empty data migration script"""

    def has_migrations(engine):
        return False


    def migrate(engine):
        return 0

References
==========
.. [GSPEC1] `Database Strategy for Rolling Upgrades
            <https://specs.openstack.org/openstack/glance-specs/specs/ocata/implemented/glance/database-strategy-for-rolling-upgrades.html>`_
.. [GSPEC2] `Glance Alembic Migrations Spec
            <https://specs.openstack.org/openstack/glance-specs/specs/ocata/implemented/glance/alembic-migrations.html>`_
.. [GMIGS1] `Glance Alembic Migrations Implementation
            <https://opendev.org/openstack/glance/src/branch/master/glance/db/sqlalchemy/alembic_migrations/versions>`_
.. [ALMBC] `Alembic Operations <http://alembic.zzzcomputing.com/en/latest/ops.html>`_
