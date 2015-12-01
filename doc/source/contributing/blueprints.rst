Blueprints and Specs
====================

The Glance team uses the `glance-specs
<http://git.openstack.org/cgit/openstack/glance-specs>`_ repository for its
specification reviews. Detailed information can be found `here
<https://wiki.openstack.org/wiki/Blueprints#Glance>`_. Please also find
additional information in the reviews.rst file.

The Glance team enforces a deadline for specs proposals. It's a soft
freeze that happens after the first milestone is cut and before the
second milestone is out. There's a freeze exception week that follows
the freeze week. A new proposal can still be submitted during this
period, but be aware that it will most likely be postponed unless a
particularly good argument is made in favor of having an exception for
it.

Please note that we use a `template
<http://git.openstack.org/cgit/openstack/glance-specs/tree/specs/template.rst>`_
for spec submissions. It is not required to fill out all sections in the
template. Review of the spec may require filling in information left out by
the submitter.

Spec Notes
----------

There are occasions when a spec will be approved and the code will not land in
the cycle it was targeted at. For these cases, the work flow to get the spec
into the next release is as follows:

* Anyone can propose a patch to glance-specs which moves a spec from the
  previous release into the new release directory.

.. NOTE: mention the `approved`, `implemented` dirs

The specs which are moved in this way can be fast-tracked into the
next release. Please note that it is required to re-propose the spec
for the new release however and that it'll be evaluated based on the
resources available and cycle priorities.

Glance Spec Lite
----------------

In Mitaka the team introduced the concept of lite specs. Lite specs
are small features tracked as Launchpad bugs, with status `wishlist`
and tagged with the new 'spec-lite' tag, and allow for the submission
and review of these feature requests before code is submitted.

This allows for small features that don't warrant a detailed spec to
be proposed, evaluated, and worked on. The team evaluates these
requests as it evaluates specs. Once a bug has been approved as a
Request for Enhancement (RFE), it'll be targeted for a release.

The workflow for the life of a spec-lite in Launchpad is as follows:

* File a bug with a small summary of what the request change is
  following the format below:
.. NOTE: add format
* The bug is triaged and tagged with the `spec-lite` tag.
* The bug is evaluated and marked as `Triaged` to announce approval or
  to `Won't fix` to announce rejection or `Invalid` to request a full
  spec.
* The bug is moved to `In Progress` once the code is up and ready to
  review.
* The bug is moved to `Fix Committed` once the patch lands.

In summary:

+--------------+-----------------------------------------------------------------------------+
|State         | Meaning                                                                     |
+==============+=============================================================================+
|New           | This is where spec-lite starts, as filed by the community.                  |
+--------------+-----------------------------------------------------------------------------+
|Triaged       | Drivers - Move to this state to mean, "you can start working on it"         |
+--------------+-----------------------------------------------------------------------------+
|Won't Fix     | Drivers - Move to this state to reject a lite-spec.                         |
+--------------+-----------------------------------------------------------------------------+
|Invalid       | Drivers - Move to this state to request a full spec for this request        |
+--------------+-----------------------------------------------------------------------------+

The drivers team will be discussing the following bug reports during their IRC meeting:

* `New RFE's <https://bugs.launchpad.net/glance/+bugs?field.status%3Alist=NEW&field.tag=spec-lite&field.importance%3Alist=WISHLIST>`_
* `New RFE's <https://bugs.launchpad.net/glance-store/+bugs?field.status%3Alist=NEW&field.tag=spec-lite&field.importance%3Alist=WISHLIST>`_
* `New RFE's <https://bugs.launchpad.net/python-glanceclient/+bugs?field.status%3Alist=NEW&field.tag=spec-lite&field.importance%3Alist=WISHLIST>`_


Lite spec Submission Guidelines
-------------------------------

Before we dive into the guidelines for writing a good lite spec, it is
worth mentioning that depending on your level of engagement with the
Glance project and your role (user, developer, deployer, operator,
etc.), you are more than welcome to have a preliminary discussion of a
potential lite spec by reaching out to other people involved in the
project. This usually happens by posting mails on the relevant mailing
lists (e.g. `openstack-dev <http://lists.openstack.org>`_ - include
[glance] in the subject) or on #openstack-glance IRC channel on
Freenode. If current ongoing code reviews are related to your feature,
posting comments/questions on gerrit may also be a way to engage. Some
amount of interaction with Glance developers will give you an idea of
the plausibility and form of your lite spec before you submit it. That
said, this is not mandatory.

When you submit a bug report on
https://bugs.launchpad.net/glance/+filebug, there are two fields that
must be filled: 'summary' and 'further information'.  The 'summary'
must be brief enough to fit in one line: if you can't describe it in a
few words it may mean that you are either trying to capture more than
one lite spec at once, or that you are having a hard time defining
what you are trying to solve at all.

The 'further information' section must be a description of what you
would like to see implemented in Glance. The description should
provide enough details for a knowledgeable developer to understand
what is the existing problem and what's the proposed solution.

Once you are happy with what you wrote, set the importance to
`Wishlist`, and submit. Do not worry, we are here to help you get it
right! Happy hacking.

Lite spec from existing bugs
----------------------------

If there's an already existing bug that describes a small feature
suitable for a spec-lite, all you need to do is change the importance
field to `Wishlist`. Please don't create a new bug! The comments and
history of the existing bug are important for the spec-lite review.
