Documentation
=============

Tips for Doc Writers (and Developers, too!)
-------------------------------------------

Here are some useful tips about questions that come up a lot but aren't always
easy to find answers to.

* Make example URLs consistent

  For consistency, example URLs for openstack components are in the form:

  .. code::

    project.openstack.example.org

  So, for example, an example image-list call to Glance would use a URL
  written like this:

  .. code::

    http://glance.openstack.example.org/v2/images

* URLs for OpenStack project documentation

  Each project's documentation is published to the following URLs:

  - ``https://docs.openstack.org/$project-name/latest`` - built from master
  - ``https://docs.openstack.org/$project-name/$series`` - built from stable

  For example, the Glance documentation is published to:

  - ``https://docs.openstack.org/glance/latest`` - built from master
  - ``https://docs.openstack.org/glance/ocata`` - built from stable/ocata

* URLs for OpenStack API Reference Guides

  Each project's API Reference Guide is published to:

  - ``https://docs.openstack.org/api-ref/$service-type``

  For example, the Glance Image Service API Reference guide is
  published to:

  - ``https://docs.openstack.org/api-ref/image``

Where to Contribute
-------------------

There are a few different kinds of documentation associated with Glance to
which you may want to contribute:

* Configuration

  As you read through the sample configuration files in the ``etc`` directory
  in the source tree, you may find typographical errors, or grammatical
  problems, or text that could use clarification.  The Glance team welcomes
  your contributions, but please note that the sample configuration files are
  generated, not static text.  Thus you must modify the source code where the
  particular option you're correcting is defined and then re-generate the conf
  file using ``tox -e genconfig``.

* Glance's Documentation

  The Glance Documentation (what you're reading right now) lives in the source
  code tree under ``doc/source``.  It consists of information for developers
  working on Glance, information for consumers of the OpenStack Images APIs
  implemented by Glance, and information for operators deploying Glance.  Thus
  there's a wide range of documents to which you could contribute.

  Small improvements can simply be addressed by a patch, but it's probably a
  good idea to first file a bug for larger changes so they can be tracked more
  easily (especially if you plan to submit several different patches to address
  the shortcoming).

* User Guides

  There are several user guides published by the OpenStack Documentation Team.
  Please see the README in their code repository for more information:
  https://github.com/openstack/openstack-manuals

* OpenStack API Reference

  There's a "quick reference" guide to the APIs implemented by Glance:
  https://docs.openstack.org/api-ref/image/

  The guide is generated from source files in the source code tree under
  ``api-ref/source``.  Corrections in spelling or typographical errors may be
  addressed directly by a patch.  If you note a divergence between the API
  reference and the actual behavior of Glance, please file a bug before
  submitting a patch.

  Additionally, now that the quick reference guides are being maintained by
  each project (rather than a central team), you may note divergences in format
  between the Glance guides and those of other teams.  For example, some
  projects may have adopted an informative new way to display error codes.  If
  you notice structural improvements that our API reference is missing, please
  file a bug.  And, of course, we would also welcome your patch implementing
  the improvement!

