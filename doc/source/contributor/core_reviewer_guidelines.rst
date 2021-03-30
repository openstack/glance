===================
Glance Code Reviews
===================

Code reviews are a critical component of all OpenStack projects. Glance
accepts patches from many diverse people with diverse backgrounds,
employers, and experience levels. Code reviews provide a way to enforce a
level of consistency across the project, and also allow for the careful
on-boarding of contributions from new contributors.

Glance Spec Review Practices
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In addition to code reviews, Glance also maintains a BP specification git
repository. Detailed instructions for the use of this repository are provided
`here <https://opendev.org/openstack/glance-specs/src/branch/master/README.rst>`_.
It is expected that Glance core team members are actively reviewing
specifications which are pushed out for review to the specification repository.
Glance specs are approved/merged by the PTL only. The PTL can approve a spec
if it has a +2 from any two core reviewers.

Some guidelines around this process are provided below:

* Before approving a spec, the PTL or other core reviewers should confirm that
  all the comments about the specification have been addressed.
* The PTL reserves the right to decide which specifications are important and
  need to be approved for given cycle.
* All specifications should be approved within 1 week after milestone-1
  release. Specifications which are not approved by then can be discussed in
  the following weekly meeting and a decision will be made whether to grant an
  FFE or move them to next cycle.
* The role of a core spec reviewer is to determine design fitness of the
  proposed change, as well as suitability for inclusion in the project. In
  order to do this, sufficient detail must be provided in the proposal, and
  core reviewers should iterate with the author until a suitable amount of
  information is included.

Guidelines for core reviewers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Glance follows the code review guidelines as set forth for all OpenStack
projects. It is expected that all reviewers are following the guidelines set
forth on that `page <https://docs.openstack.org/project-team-guide/review-the-openstack-way.html>`_.
In addition to that, the following rules are to be followed:

* Use of +W

  * For a documentation change any core can ninja approve the patch if
    everything is correct
  * For a patch which fixes a bug, the approver should ensure that:

    * Unit or Functional tests have been added/updated
    * A release note has been added if the bug is not trivial
    * The commit message is tagged with Closes-Bug: #bugid

  * For a patch which adds/implements a new feature, the approver should
    ensure that:

    * Documentation is updated to explain how the new feature will work
    * If an API call is added/modified, the API reference doc should be
      updated accordingly
    * Tempest/CI coverage is proposed/available for the new feature
    * Client side changes are addressed if required

* Use of -2

  * A -2 should be used to indicate that a patch or change cannot be allowed
    to merge because of a fundamental conflict with the scope or goals of the
    project. It should not be used in cases where the patch could be altered
    to address feedback, or where further discussion is likely to lead to an
    alternative implementation that would be suitable.
  * A -2 review should always be accompanied by a comment explaining the reason
    that the change does not fit with the project goals, so that the submitter
    can understand the reasons and refocus their future contributions more
    productively.
  * The core team should come to an agreement if there is a difference of
    opinion about the suitability of the patch.
  * If a majority of the team is in favor of moving forward with the patch then
    the person who added these -2(s) will change it to -1 if they still don't
    agree with the implementation. As an open source team, we operate on
    consensus of multiple people and do not support individual members acting
    against the will of the others.
  * The PTL reserves the right to ask a core reviewer to change their -2 vote
    to a -1.

* Procedural use of -2

  * In some situations, a core reviewer will put a -2 vote on a patch to "hold"
    it temporarily from merging due to some procedural criteria. This may be
    used on feature changes after Feature Freeze and before branching for the
    next release, to ensure that no features are unintentionally merged during
    the freeze.
  * It may also be used to avoid merging something that depends on a
    corresponding patch in another tree, or some job configuration change that
    would otherwise result in a breakage if merged too soon. The person who
    added these -2s will then remove them again once the blocking issue has
    cleared.
  * When placing the -2, they should leave a comment explaining exactly what is
    happening, that the -2 is "procedural" and provide a timeline or criteria
    after which the vote will be dropped. Submitters can continue to revise the
    change during the freeze.

* Use of -W

  * A Workflow -1 vote indicates that the change is not currently ready for a
    comprehensive review and is intended for the original submitter to indicate
    to reviewers that they do not expect the patch to be mergeable. Only core
    reviewers and the original change owner can vote Workflow -1 on a given
    patch. Any workflow votes are cleared when a new patch set is submitted
    for the change. This is a better way to get feedback on ongoing work than
    the legacy method of a Draft change (which is hidden from reviewers not
    specifically added to it).
  * Core reviewers may also use the Workflow -1 vote to prevent a change from
    being merged during some temporary condition, without interrupting the
    code-review process.
