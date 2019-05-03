==================
Glance Release CPL
==================

So you've volunteered to be the Glance Release Cross-Project Liaison (CPL) and
now you're worried about what you've gotten yourself into. Well, here are some
tips for you from former release CPLs.

You will be doing vital and important work both for Glance and OpenStack.
Releases have to be available at the scheduled milestones and RC dates because
end users, other OpenStack projects, and packagers rely on releases being
available so they can begin their work. Missing a date can have a cascading
effect on all the people who are depending on the release being available at
its scheduled time. Sounds scary, I know, but you'll also get a lot of
satisfaction out of having a key role in keeping OpenStack running smoothly.


Who You Have to Be
==================

You do **not** have to be:

- The PTL

- A core reviewer

- A stable-branch core reviewer/maintainer

You **do** have to be:

- A member of the Glance community

- A person who has signed the OpenStack CLA (or whatever is in use at the time
  you are reading this)

- Someone familiar with or willing to learn git, gerrit, etc.

- Someone who will be comfortable saying "No" when colleagues want to sneak
  just one more thing in before a deadline.

- Someone willing to work with the release team on a regular basis and attend
  their `weekly meeting`_.

  Just as the stable maintenance team is responsible for the stability and
  quality of the stable branches, the release CPL must take on responsibility
  for the stability and quality of every release artifact of Glance. If you
  are too lenient with your colleagues, you might be responsible for
  introducing a catastrophic or destabilizing release. Suppose someone,
  possibly even the PTL, shows up right before RC1 with a large but probably
  innocuous change. Even if this passes the gate, you should err on the side
  of caution and ask to not allow it to merge.
  (This has happened `before <https://review.opendev.org/#/c/427535/>`_ )

A Release CPL has authority within the Glance project. They have authority
through two measures:

- Being the person who volunteered to do this hard work

- Maintaining a healthy relationship with the PTL and their Glance colleagues.

Use this authority to ensure that each Glance release is the best possible.
The PTL's job is to lead technical direction, your job is to shepherd cats and
help them focus on the priorities for each release.


What This Does Not Grant You
============================

Volunteering to be Release CPL does not give you the right to be a Glance Core
Reviewer. That is a separate role that is determined based on the quality of
your reviews. You should be primarily motivated by wanting to help the team
ship an excellent release.


Get To Know The Release Team
============================

OpenStack has teams for most projects and efforts. In that vein, the release
team works on tooling to make releasing projects easier as well as verifying
releases. As CPL it is your job to work with this team. At the time of this
writing, the team organizes in ``#openstack-release`` and has a `weekly
meeting`_. Idling in their team channel and attending the meeting are two very
strongly suggested (if not required) actions for the CPL. You should introduce
yourself well in advance of the release deadlines. You should also take the
time to research what actions you may need to take in advance of those
deadlines as the release team becomes very busy around those deadlines.


Familiarize Yourself with Community Goals
=========================================

Community Goals **are** Glance Goals. They are documented and tracked in the
`openstack/governance`_ repository. In Ocata, for example, the CPL assumed the
responsibility of monitoring those goals and reporting back to the TC when
we completed them.

In my opinion, it makes sense for the Release CPL to perform this task because
they are the ones who are keenly aware of the deadlines in the release
schedule and can remind the assigned developers of those deadlines.

It also is important for the Release CPL to coordinate with the PTL to ensure
that there are project-specific deadlines for the goals. This will ensure the
work is completed and reviewed in a timely fashion and hopefully early enough
to catch any bugs that shake out of the work.


Familiarize Yourself with the Release Tooling
=============================================

The Release Team has worked to automate much of the release process over the
last several development cycles. Much of the tooling is controlled by updating
certain YAML files in the `openstack/releases`_ repository.

To release a Glance project, look in the ``deliverables`` directory for the
cycle's codename, e.g., ``pike``, and then look for the project inside of
that. Update that using the appropriate syntax and after the release team has
reviewed your request and approved it, the rest will be automated for you.

For more information on release management process and tooling, refer to
`release management process guide`_ and `release management tooling guide`_.


Familiarize Yourself with the Bug Tracker
=========================================

The `bug tracker`_ is the best way to determine what items are slated to get
in for each particular milestone or cycle release. Use it to the best of its
capabilities.

Release Stability and the Gate
==============================

As you may know at this point, OpenStack's Integrated Gate will begin to
experience longer queue times and more frequent unrelated failures around
milestones and release deadlines (as other projects attempt to sneak things
in at the last minute).

You may help your colleagues (and yourself) if you advocate for deadlines on
features, etc., at least a week in advance of the actual release deadline.
This can apply to all release deadlines (milestone, release candidate, final).
If you can stabilize your project prior to the flurry of activity, you will
ship a better product. You can also then focus on bug fixing reviews in the
interim between your project priorities deadline and the actual release
deadline.

There are periodic "tips" test jobs set up for each of glance, glance_store,
and python-glanceclient.  These jobs test our current masters (which use
the released versions of dependencies) against the master branches of our
dependencies.  This way we can get a heads-up if a dependency merges a change
that will break us.  In order for this to work, someone has to keep an eye
on these jobs ... and that person is you.  Part of your job is to report on
the status of the periodic jobs at the weekly glance meeting.

You can see the output of these jobs by going to the Zuul Builds Page,
``http://zuul.openstack.org/builds.html``.  (Note: it takes a minute or so
for the page to populate.)  You can filter the results by Pipeline (you
want ``periodic``) and Project (use ``openstack/glance``,
``openstack/glance_store``, or ``openstack/python-glanceclient``).  You
can find a link to the logs of each job from that page.  (Note: your
responsibility as Release CPL is limited to monitoring and notifying the
team about the status of the jobs.  But feel free to fix them if you want
to!)


Checklist
=========

The release team will set dates for all the milestones for each release. The
release schedule can be found from this page:
https://releases.openstack.org/index.html
There are checklists to follow for various important release aspects:


Glance Specific Goals
---------------------

While the release team sets dates for community-wide releases, you should work
with the PTL to set Glance specific deadlines/events such spec proposal freeze,
spec freeze, mid-cycle, bug squash and review squash etc. Also, you can set
additional deadlines for Glance priorities to ensure work is on-track for a
timely release.

You are also responsible for ensuring PTL and other concerned individuals are
aware and reminded of the events/deadlines to ensure timely release.


Milestone Release
-----------------

The release schedule for the current cycle will give you a range of dates for
each milestone release. It is your job to propose the release for Glance
sometime during that range and ensure the release is created. This means the
following:

- Showing up at meetings to announce the planned date weeks in advance.

  Your colleagues on the Glance team will need at least 4 weeks notice so they
  can plan and prioritize what work should be included in the milestone.

- Reminding your colleagues what the stated priorities for that milestone
  were, their progress, etc.

- Being inflexible in the release date. As soon as you pick your date, stick
  to it. If a feature slips a milestone to the next, it is not the end of the
  world. It is not ideal, but Glance *needs* to release its milestone as soon
  as possible.

- Proposing the release in a timely and correct fashion on the day you stated.
  You may have colleagues try to argue their case to the release team. This is
  when your collaboration with the PTL will be necessary. The PTL needs to
  help affirm your decision to release the version of the project you can on
  the day you decide it.

- Release ``glance_store`` and ``python-glanceclient`` at least once per
  milestone.

- Write `release notes`_

Release Candidate Releases
--------------------------

The release candidate release period is similarly scoped to a few days. It is
even more important that Glance release during that period. To help your
colleagues, try to schedule this release as close to the end of that range as
possible. Once RC1 is released, only bugs introduced since the last milestone
that are going to compromise the integrity of the release should be merged.
Again, your duties include all of the Milestone Release duties plus the
following:

- When proposing the release, you need to appropriately configure the release
  tooling to create a stable branch. If you do not, then you have not
  appropriately created the release candidate.

- Keeping a *very* watchful eye on what is proposed to and approved for master
  as well as your new stable branch. Again, automated updates from release
  tooling and *release critical* bugs are the only things that should be
  merged to either.

- If release critical bugs are found and fixed, proposing a new release
  candidate from the SHA on the stable branch.

- Write `release notes`_

- Announce that any non-release-critical changes won't be accepted from this
  point onwards until the final Glance release is made. Consider adding -2 on
  such reviews  with good description to prevent further updates.
  This also helps in keeping the gate relatively free to process
  the release-critical changes.


Final Releases
--------------

The release team usually proposes all of the projects' final releases in one
patch based off the final release candidate. After those are created, some
things in Glance need to be updated immediately.

- The migration tooling that Glance uses relies on some constants defined in
  `glance/db/migration.py`_. Post final release, those need *immediate*
  updating.


Acknowledgements
----------------
This document was originally written by Ian Cordasco.  It's maintained and
revised by the Glance Release CPLs:

- Ian Cordasco, Release CPL for Ocata
- Hemanth Makkapati, Release CPL for Pike
- Erno Kuvaja, Release CPL for Queens
- Brian Rosmaita, Release CPL for Rocky

.. links
.. _weekly meeting:
    http://eavesdrop.openstack.org/#Release_Team_Meeting
.. _openstack/governance:
    https://opendev.org/openstack/governance
.. _openstack/releases:
    https://opendev.org/openstack/releases
.. _StoryBoard:
    https://storyboard.openstack.org/
.. _glance/db/migration.py:
    https://github.com/openstack/glance/blob/master/glance/db/migration.py
.. _release management process guide:
    https://docs.openstack.org/project-team-guide/release-management.html
.. _release management tooling guide:
    https://opendev.org/openstack/releases/src/branch/master/README.rst
.. _bug tracker:
    https://bugs.launchpad.net/glance
.. _release notes:
    https://docs.openstack.org/project-team-guide/release-management.html#managing-release-notes
