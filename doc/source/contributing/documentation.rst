Documentation
=============

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

  There are some Glance-related API quick-reference guides published by the
  OpenStack Documentation Team. Please see the README in their code repository
  for more information: https://github.com/openstack/api-site

Release Notes
-------------

Release notes are notes available for operators to get an idea what each
project has included and changed during a cycle. They may also include
various warnings and notices.

Generating release notes is done with Reno.

.. code-block:: bash

    $ tox -e venv -- reno new <bug-,bp-,whatever>

This will generate a yaml file in ``releasenotes/notes`` that will contain
instructions about how to fill in (or remove) the various sections of
the document. Modify the yaml file as appropriate and include it as
part of your commit.

Once the release notes have been committed you can build them by using:

.. code-block:: bash

   $ tox -e releasenotes

This will create the HTML files under ``releasenotes/build/html/``.
