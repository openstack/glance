============================
So You Want to Contribute...
============================

For general information on contributing to OpenStack, please check out the
`contributor guide <https://docs.openstack.org/contributors/>`_ to get started.
It covers all the basics that are common to all OpenStack projects: the
accounts you need, the basics of interacting with our Gerrit review system, how
we communicate as a community, etc.

Below will cover the more project specific information you need to get started
with the Glance project, which is responsible for the following OpenStack
deliverables:

glance
    | The OpenStack Image service.
    | code: https://opendev.org/openstack/glance
    | docs: https://glance.openstack.org
    | api-ref: https://docs.openstack.org/api-ref/image
    | Launchpad: https://launchpad.net/glance

glance_store
    | Glance's stores library.
    | code: https://opendev.org/openstack/glance_store
    | docs: https://docs.openstack.org/glance_store
    | Launchpad: https://launchpad.net/glance_store

python-glanceclient
    | Python client library for the OpenStack Image API; includes
      a CLI shell.
    | code: https://opendev.org/openstack/python-glanceclient
    | docs: https://docs.openstack.org/python-glanceclient
    | Launchpad: https://launchpad.net/python-glanceclient

See the ``CONTRIBUTING.rst`` file in each code repository for more
information about contributing to that specific deliverable.  Additionally,
you should look over the docs links above; most components have helpful
developer information specific to that deliverable.

Communication
~~~~~~~~~~~~~

IRC
    People working on the Glance project may be found in the
    ``#openstack-glance`` channel on Freenode during working hours
    in their timezone.  The channel is logged, so if you ask a question
    when no one is around, you can check the log to see if it's been
    answered: http://eavesdrop.openstack.org/irclogs/%23openstack-glance/

weekly meeting
    Thursdays at 14:00 UTC in ``#openstack-meeting-4`` on Freenode.
    Meetings are logged: http://eavesdrop.openstack.org/meetings/glance/

    More information (including a link to the Agenda, some pointers on
    meeting etiquette, and an ICS file to put the meeting on your calendar)
    can be found at: http://eavesdrop.openstack.org/#Glance_Team_Meeting

mailing list
    We use the openstack-discuss@lists.openstack.org mailing list for
    asynchronous discussions or to communicate with other OpenStack teams.
    Use the prefix ``[glance]`` in your subject line (it's a high-volume
    list, so most people use email filters).

    More information about the mailing list, including how to subscribe
    and read the archives, can be found at:
    http://lists.openstack.org/cgi-bin/mailman/listinfo/openstack-discuss

physical meet-ups
    The Glance project usually has a presence at the OpenDev/OpenStack
    Project Team Gathering that takes place at the beginning of each
    development cycle.  Planning happens on an etherpad whose URL is
    announced at the weekly meetings and on the mailing list.

Contacting the Core Team
~~~~~~~~~~~~~~~~~~~~~~~~

The glance-core team is an active group of contributors who are responsible
for directing and maintaining the Glance project.  As a new contributor, your
interaction with this group will be mostly through code reviews, because
only members of glance-core can approve a code change to be merged into the
code repository.

.. note::
   Although your contribution will require reviews by members of
   glance-core, these aren't the only people whose reviews matter.
   Anyone with a gerrit account can post reviews, so you can ask
   other developers you know to review your code ... and you can
   review theirs.  (A good way to learn your way around the codebase
   is to review other people's patches.)

   If you're thinking, "I'm new at this, how can I possibly provide
   a helpful review?", take a look at `How to Review Changes the
   OpenStack Way
   <https://docs.openstack.org/project-team-guide/review-the-openstack-way.html>`_.

You can learn more about the role of core reviewers in the OpenStack
governance documentation:
https://docs.openstack.org/contributors/common/governance.html#core-reviewer

The membership list of glance-core is maintained in gerrit:
https://review.opendev.org/#/admin/groups/13,members

You can also find the members of the glance-core team at the Glance weekly
meetings.


New Feature Planning
~~~~~~~~~~~~~~~~~~~~

The Glance project uses both "specs" and "blueprints" to track new features.
Here's a quick rundown of what they are and how the Glance project uses them.

specs
    | Exist in the glance-specs repository.
      Each spec must have a Launchpad blueprint (see below) associated with
      it for tracking purposes.

    | A spec is required for any new Glance core feature, anything that
      changes the Image API, or anything that entails a mass change
      to existing drivers.

    | The specs repository is: https://opendev.org/openstack/glance-specs
    | It contains a ``README.rst`` file explaining how to file a spec.

    | You can read rendered specs docs at:
    | https://specs.openstack.org/openstack/glance-specs/

blueprints
    | Exist in Launchpad, where they can be targeted to release milestones.
    | You file one at https://blueprints.launchpad.net/glance

You can learn more about new feature planning:
https://docs.openstack.org/glance/latest/contributor/blueprints.html


Feel free to ask in ``#openstack-glance`` or at the weekly meeting if you
have an idea you want to develop and you're not sure whether it requires
a blueprint *and* a spec or simply a blueprint.

The Glance project observes the following deadlines.  For the current
development cycle, the dates of each (and a more detailed description)
may be found on the release schedule, which you can find from:
https://releases.openstack.org/

* spec freeze (all specs must be approved by this date)
* new driver merge deadline
* new target driver merge deadline
* new feature status checkpoint
* third-party CI compliance checkpoint

Additionally, the Glance project observes the OpenStack-wide deadlines,
for example, final release of non-client libraries (glance_store), final
release for client libraries (python-glanceclient), feature freeze,
etc.  These are also noted and explained on the release schedule for the
current development cycle.

Task Tracking
~~~~~~~~~~~~~

We track our tasks in Launchpad.  See the top of the page for the URL of each
Glance project deliverable.

If you're looking for some smaller, easier work item to pick up and get started
on, search for the 'low-hanging-fruit' tag in the Bugs section.

When you start working on a bug, make sure you assign it to yourself.
Otherwise someone else may also start working on it, and we don't want to
duplicate efforts.  Also, if you find a bug in the code and want to post a
fix, make sure you file a bug (and assign it to yourself!) just in case someone
else comes across the problem in the meantime.

Reporting a Bug
~~~~~~~~~~~~~~~

You found an issue and want to make sure we are aware of it? You can do so in
the Launchpad space for the affected deliverable:

* glance: https://bugs.launchpad.net/glance
* glance_store: https://bugs.launchpad.net/glance_store
* python-glanceclient: https://bugs.launchpad.net/python-glanceclient

Getting Your Patch Merged
~~~~~~~~~~~~~~~~~~~~~~~~~

The Glance project policy is that a patch must have two +2s before it can
be merged.  (Exceptions are documentation changes, which require only a
single +2, and specs, for which the PTL may require more than two +2s,
depending on the complexity of the proposal.)

Patches lacking unit tests are unlikely to be approved.

In addition, some changes may require a release note.  Any patch that
changes functionality, adds functionality, or addresses a significant
bug should have a release note.  You can find more information about
how to write a release note in the :ref:`release-notes` section of the
Glance Contributors Guide.

Keep in mind that the best way to make sure your patches are reviewed in
a timely manner is to review other people's patches.  We're engaged in a
cooperative enterprise here.

You can see who's been doing what with Glance recently in Stackalytics:
https://www.stackalytics.com/report/activity?module=glance-group

Project Team Lead Duties
~~~~~~~~~~~~~~~~~~~~~~~~

All common PTL duties are enumerated in the `PTL guide
<https://docs.openstack.org/project-team-guide/ptl.html>`_.

Additional responsibilities for the Glance PTL can be found by reading through
the :ref:`managing-development` section of the Glance documentation.
