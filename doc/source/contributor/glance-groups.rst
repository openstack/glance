
.. _glance-groups:

=====================================
Glance Groups in Gerrit and Launchpad
=====================================

Glance-related groups in Launchpad
==================================

.. list-table::
   :header-rows: 1

   * - group
     - what
     - who
     - where
   * - "Glance" team
     - not sure, exactly
     - an "open" team, anyone with a Launchpad account can join
     - `Glance Launchpad <https://launchpad.net/~glance>`_
   * - "Glance Bug Team" team
     - can triage (change status fields) on bugs
     - an "open" team, people self-nominate
     - `Glance Bug Team <https://launchpad.net/~glance-bugs>`_
   * - "Glance Drivers" team
     - not sure, exactly
     - Anyone who is interested in doing some work, has a Launchpad
       account, and is approved by the current members
     - `Glance Drivers Team <https://launchpad.net/~glance-drivers>`_
   * - "Glance Release" team
     - Maintains the Launchpad space for Glance, glance_store,
       python-glanceclient, and glance-tempest-plugin
     - Anyone who is interested in doing some work, has a Launchpad
       account, and is approved by the current members
     - `Glance Release Team <https://launchpad.net/~glance-release>`_
   * - "Glance Core security contacts" team
     - can see and work on private security bugs while they are under embargo
     - subset of glance-core (the OpenStack Vulnerablity Management Team
       likes to keep this team small), so even though the PTL can add people,
       you should propose them on the mailing list first.
     - `Glance Security Team <https://launchpad.net/~glance-coresec>`_

Glance-related groups in Gerrit
===============================

The Glance project has total control over the membership of these groups.

.. list-table::
   :header-rows: 1

   * - group
     - what
     - who
     - where
   * - glance-ptl
     - Current Glance PTL
     - glance ptl
     - `Glance PTL <https://review.opendev.org/admin/groups/3a2d24a98c24482a0371a4762ba0c1b3ade078b8,members>`_
   * - glance-core
     - +2 powers in Glance project code repositories
     - glance core reviewers
     - `Glance Core Team <https://review.opendev.org/admin/groups/1d14a0536e224488ae2c442c499ad16dddcdf8b8,members>`_
   * - glance-specs-core
     - +2 powers in glance-specs repository
     - glance-core (plus others if appropriate; currently only glance-core)
     - `Glance Specs Core Team <https://review.opendev.org/admin/groups/b922792a1e96d66b0fc3b2cdbb6aaad7ae9eeefe,members>`_
   * - glance-tempest-plugin-core
     - +2 powers on the glance-tempest-plugin repository
     - glance-core plus other appropriate people
     - `Glance Tempest Plugin Core Team <https://review.opendev.org/admin/groups/0231143f107f488b7525707b3547b7eac26471ec,members>`_

The Glance project shares control over the membership of these groups.  If you
want to add someone to one of these groups who doesn't already have membership
by being in an included group, be sure to include the other groups or
individual members in your proposal email.

.. list-table::
   :header-rows: 1

   * - group
     - what
     - who
     - where
   * - glance-stable-maint
     - +2 powers on backports to stable branches
     - subset of glance-core (subject to approval by stable-maint-core) plus
       the stable-maint-core team
     - `Glance Stable Core Team <https://review.opendev.org/admin/groups/6a290a73668d7cdefb7bdfdc5a85f9adb61bbaa5,members>`_

NOTE: The following groups exist, but I don't think they are used for anything
anymore.

.. list-table::
   :header-rows: 1

   * - group
     - where
   * - glance-release
     - `Glance Release <https://review.opendev.org/admin/groups/a405991a32b8d5cbc975db4c956cb11d04805192,members>`_
   * - glance-release-branch
     - `Glance Stable Release Team <https://review.opendev.org/admin/groups/fe8ee0c76e7a0bf4b33afbb81741ec4daca50ed4,members>`_

How Gerrit groups are connected to project repositories
-------------------------------------------------------

The connection between the groups defined in gerrit and what they
can do is defined in the project-config repository:
https://opendev.org/openstack/project-config

* ``gerrit/projects.yaml`` sets the config file for a project
* ``gerrit/acls`` contains the config files
