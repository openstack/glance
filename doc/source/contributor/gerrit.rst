.. _reviewing-glance:

Code Reviews
============

Glance follows the same `Review guidelines`_ outlined by the OpenStack
community. This page provides additional information that is helpful for
reviewers of patches to Glance.

Gerrit
------

Glance uses the `Gerrit`_ tool to review proposed code changes. The review
site is https://review.opendev.org

Gerrit is a complete replacement for Github pull requests. `All Github pull
requests to the Cinder repository will be ignored`.

See `Quick Reference`_ for information on quick reference for developers.
See `Getting Started`_ for information on how to get started using Gerrit.
See `Development Workflow`_ for more detailed information on how to work with
Gerrit.

The Great Change
----------------

With the demise of Python 2.7 in January 2020, beginning with the Ussuri
development cycle, Glance only needs to support Python 3 runtimes (in
particular, 3.6 and 3.7).  Thus we can begin to incorporate Python 3
language features and remove Python 2 compatibility code.  At the same
time, however, we are still supporting stable branches that must support
Python 2.  Our biggest interaction with the stable branches is backporting
bugfixes, where in the ideal case, we're just doing a simple cherry-pick of
a commit from master to the stable branches.  You can see that there's some
tension here.

With that in mind, here are some guidelines for reviewers and developers
that the Glance community has agreed on during this phase where we want to
write pure Python 3 but still must support Python 2 code.

.. _transition-guidelines:

Python 2 to Python 3 transition guidelines
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* We need to be checking the code coverage of test cases very carefully so
  that new code has excellent coverage.  The idea is that we want these
  tests to fail when a backport is proposed to a stable branch and the
  tests are run under Python 2 (if the code is using any Python-3-only
  language features).
* New features can use Python-3-only language constructs, but bugfixes
  likely to be backported should be more conservative and write for
  Python 2 compatibility.
* The code for drivers may continue to use the six compatibility library at
  their discretion.
* We will not remove six from mainline Cinder code that impacts the drivers
  (for example, classes they inherit from).
* We can remove six from code that doesn't impact drivers, keeping in mind
  that backports may be more problematic, and hence making sure that we have
  really good test coverage.

Unit Tests
----------

Glance requires unit tests with all patches that introduce a new
branch or function in the code.  Changes that do not come with a
unit test change should be considered closely and usually returned
to the submitter with a request for the addition of unit test.

.. _Review guidelines: https://docs.openstack.org/doc-contrib-guide/docs-review-guidelines.html
.. _Gerrit: https://review.opendev.org/#/q/project:openstack/glance+status:open
.. _Quick Reference: https://docs.openstack.org/infra/manual/developers.html#quick-reference
.. _Getting Started: https://docs.openstack.org/infra/manual/developers.html#getting-started
.. _Development Workflow: https://docs.openstack.org/infra/manual/developers.html#development-workflow
