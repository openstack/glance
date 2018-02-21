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

.. _rolling-upgrades:

Rolling Upgrades
================

.. note:: The Rolling Upgrades feature is EXPERIMENTAL and its use in
          production systems is currently **not supported**.

          This statement remains true for the Queens release of Glance.  What
          is the holdup, you ask?  Before asserting that the feature is fully
          supported, the Glance team needs to have automated tests that perform
          rolling upgrades in the OpenStack Continuous Integration gates.  The
          Glance project team has not had sufficient testing and development
          resources in recent cycles to prioritize this work.

          The Glance project team is committed to the stability of Glance.  As
          part of OpenStack, we are committed to `The Four Opens`_.  If the
          ability to perform rolling upgrades in production systems is
          important to you, feel free to participate in the Glance community to
          help coordinate and drive such an effort.  (We gently remind you that
          "participation" includes providing testing and development
          resources.)

          .. _`The Four Opens`: https://governance.openstack.org/tc/reference/opens.html

Scope of this document
----------------------

This page describes one way to perform a rolling upgrade from Newton to Ocata
for a particular configuration of Glance services.  There may be other ways to
perform a rolling upgrade from Newton to Ocata for other configurations of
Glance services, but those are beyond the scope of this document.  For the
experimental rollout of rolling upgrades, we describe only the following
simple case.

Prerequisites
-------------

* MySQL/MariaDB 5.5 or later

* Glance running Images API v2 only

* Glance not using the Glance Registry

* Multiple Glance nodes

* A load balancer or some other type of redirection device is being used
  in front of the Glance nodes in such a way that a node can be dropped
  out of rotation, that is, that Glance node continues running the Glance
  service but is no longer having requests routed to it

Procedure
---------

Following is the process to upgrade Glance with zero downtime:

1. Backup the Glance database.

2. Choose an arbitrary Glance node or provision a new node to install the new
   release. If an existing Glance node is chosen, gracefully stop the Glance
   services.  In what follows, this node will be referred to as the NEW NODE.

.. _Stop the Glance processes gracefully:

.. note::
   **Gracefully stopping services**

   Before stopping the Glance processes on a node, one may choose to wait until
   all the existing connections drain out. This could be achieved by taking the
   node out of rotation, that is, by ensuring that requests are no longer
   routed to that node. This way all the requests that are currently being
   processed will get a chance to finish processing.  However, some Glance
   requests like uploading and downloading images may last a long time. This
   increases the wait time to drain out all connections and consequently the
   time to upgrade Glance completely.  On the other hand, stopping the Glance
   services before the connections drain out will present the user with errors.
   While arguably this is not downtime given that Images API requests are
   continually being serviced by other nodes, this is nonetheless an unpleasant
   user experience for the user whose in-flight request has terminated in an
   error.  Hence, an operator must be judicious when stopping the services.

3. Upgrade the NEW NODE with new release and update the configuration
   accordingly.  **DO NOT** start the Glance services on the NEW NODE at
   this time.

4. Using the NEW NODE, expand the database using the command::

    glance-manage db expand

    .. warning::

     For MySQL, using the ``glance-manage db_expand`` command requires that
     you either grant your glance user ``SUPER`` privileges, or run
     ``set global log_bin_trust_function_creators=1;`` in mysql beforehand.

5. Then, also on the NEW NODE, perform the data migrations using the command::

    glance-manage db migrate

   *The data migrations must be completed before you proceed to the next step.*

6. Start the Glance processes on the NEW NODE.  It is now ready to receive
   traffic from the load balancer.

7. Taking one node at a time from the remaining nodes, for each node:

   a. `Stop the Glance processes gracefully`_ as described in Step 2, above.
      *Do not proceed until the "old" Glance services on the node have been
      completely shut down.*

   b. Upgrade the node to the new release (and corresponding configuration).

   c. Start the updated Glance processes on the upgraded node.

8. After **ALL** of the nodes have been upgraded to run the new Glance
   services, and there are **NO** nodes running any old Glance services,
   contract the database by running the command from any one of the upgraded
   nodes::

    glance-manage db contract
