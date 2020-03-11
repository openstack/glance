.. _release-notes:

Release Notes
=============

Release notes are notes available for operators to get an idea what each
project has included and changed during a cycle. They may also include
various warnings and notices.

Generating release notes is done with Reno.  You can submit a release note as a
yaml file with your patch, and Reno will gather and organize all the individual
notes into releases by looking at the commit hash associated with the yaml file
to see where it falls relative to branches/tags, and generate a single page of
notes for each release.

OpenStack has adopted Reno because it allows release notes to be written at the
time the code is committed.  At that time, the impact of the change is still
clear in everyone's mind, and it avoids the situation where the PTL is
scrambling to write a detailed set of notes at the last minute.

You can read through the past `Glance Release Notes
<https://docs.openstack.org/releasenotes/glance/index.html>`_
to get a sense of what changes require a release note.  If you're not sure,
ask in IRC or at the weekly Glance meeting.  Sometimes a reviewer will force
the issue by adding "needs a release note" as a comment on your gerrit review.

A lot of people who write high-quality code are not comfortable writing release
notes.  If you are such a person, and you're working on a patch that requires
a release note, you can ask in IRC or at the weekly Glance meeting for a
volunteer to take care of the release note for you.

You use Reno to generate a release note as follows:

.. code-block:: bash

    $ tox -e venv -- reno new <bug-,bp-,whatever>

This will generate a yaml file in ``releasenotes/notes`` that will contain
instructions about how to fill in (or remove) the various sections of
the document. Modify the yaml file as appropriate and include it as
part of your commit.

.. note::
   The Glance team has adopted the convention that the PTL writes the
   ``prelude`` section for a cycle's release notes at release time, when
   it's clear what's been accomplished during the cycle and what should be
   highlighted.  So don't include a ``prelude`` section in your release
   note.

Commit your note to git (required for reno to pick it up):

.. code-block:: bash

    $ git add releasenotes/notes/<note>; git commit

Once the release notes have been committed you can build them by using:

.. code-block:: bash

   $ tox -e releasenotes

This will create the HTML files under ``releasenotes/build/html/``.
