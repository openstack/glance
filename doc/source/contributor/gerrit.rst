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
particular, 3.6 and 3.7).  There was a four cycle transition period, but
starting in the Yoga development cycle, all Python 2 compatibility code
has been removed and only Python 3 is supposed.

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
