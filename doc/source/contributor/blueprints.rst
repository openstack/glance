Blueprints and Specs
====================

The Glance team uses the `glance-specs
<https://opendev.org/openstack/glance-specs>`_ repository for its
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
<https://opendev.org/openstack/glance-specs/src/branch/master/specs/template.rst>`_
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

In addition to the heavy-duty design documents described above, we've made a
provision for lightweight design documents for developers who have an idea for
a small, uncontroversial change.  In such a case, you can propose a *spec
lite*, which is a quick description of what you want to do.

You propose a spec-lite in the same way you propose a full spec: copy
the `spec-lite template
<https://opendev.org/openstack/glance-specs/src/branch/master/specs/spec-lite-template.rst>`_
in the **approved** directory for the release cycle in which you're proposing
the change, fill out the appropriate sections, and put up a patch in gerrit.


Lite spec Submission Guidelines
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Before we dive into the guidelines for writing a good lite spec, it is
worth mentioning that depending on your level of engagement with the
Glance project and your role (user, developer, deployer, operator,
etc.), you are more than welcome to have a preliminary discussion of a
potential lite spec by reaching out to other people involved in the
project. This usually happens by posting mails on the relevant mailing
lists (e.g. `openstack-discuss <http://lists.openstack.org>`_ - include
[glance] in the subject) or on #openstack-glance IRC channel on
OFTC. If current ongoing code reviews are related to your feature,
posting comments/questions on gerrit may also be a way to engage. Some
amount of interaction with Glance developers will give you an idea of
the plausibility and form of your lite spec before you submit it. That
said, this is not mandatory.
