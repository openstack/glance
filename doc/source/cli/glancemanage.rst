=============
glance-manage
=============

-------------------------
Glance Management Utility
-------------------------

.. include:: header.txt

SYNOPSIS
========

::

  glance-manage [options]

DESCRIPTION
===========

glance-manage is a utility for managing and configuring a Glance installation.
One important use of glance-manage is to setup the database. To do this run::

    glance-manage db_sync

Note: glance-manage commands can be run either like this::

    glance-manage db sync

or with the db commands concatenated, like this::

    glance-manage db_sync



COMMANDS
========

``db``
      This is the prefix for the commands below when used with a space
      rather than a _. For example "db version".

``db_version``
      This will print the current migration level of a glance database.

``db_upgrade [VERSION]``
      This will take an existing database and upgrade it to the
      specified VERSION.

``db_version_control``
      Place the database under migration control.

``db_sync [VERSION]``
      Place an existing database under migration control and upgrade it to
      the specified VERSION.

``db_expand``
      Run this command to expand the database as the first step of a rolling
      upgrade process.

``db_migrate``
      Run this command to migrate the database as the second step of a
      rolling upgrade process.

``db_contract``
      Run this command to contract the database as the last step of a rolling
      upgrade process.

``db_export_metadefs [PATH | PREFIX]``
      Export the metadata definitions into json format. By default the
      definitions are exported to /etc/glance/metadefs directory.
      ``Note: this command will overwrite existing files in the supplied or
      default path.``

``db_load_metadefs [PATH]``
      Load the metadata definitions into glance database. By default the
      definitions are imported from /etc/glance/metadefs directory.

``db_unload_metadefs``
      Unload the metadata definitions. Clears the contents of all the glance
      db tables including metadef_namespace_resource_types, metadef_tags,
      metadef_objects, metadef_resource_types, metadef_namespaces and
      metadef_properties.

``db_purge``
      Purge deleted rows older than a given age from glance db tables.

      This command interprets the following options when it is invoked:

      --max_rows      Purge deleted rows older than age in days (default
                      value if not specified: 100)
      --age_in_days   Limit number of records to delete (default value if
                      not specified: 30 days)

      WARNING: This function is useful primarily in test systems. We do not
      recommend its use in production systems unless you have reviewed
      OpenStack Security Note `OSSN-0075`_ and understand the risk involved.

      .. _`OSSN-0075`: https://wiki.openstack.org/wiki/OSSN/OSSN-0075

``db_purge_images_table``
      Purge deleted rows older than a given age from images db tables.

      This command interprets the following options when it is invoked:

      --max_rows      Purge deleted rows older than age in days (default
                      value if not specified: 100)
      --age_in_days   Limit number of records to delete (default value if
                      not specified: 30 days)

      WARNING: This function is useful primarily in test systems. We do not
      recommend its use in production systems unless you have reviewed
      OpenStack Security Note `OSSN-0075`_ and understand the risk involved.

      .. _`OSSN-0075`: https://wiki.openstack.org/wiki/OSSN/OSSN-0075

OPTIONS
=======

**General Options**

.. include:: general_options.txt

.. include:: footer.txt

CONFIGURATION
=============

The following paths are searched for a ``glance-manage.conf`` file in the
following order:

* ``~/.glance``
* ``~/``
* ``/etc/glance``
* ``/etc``

All options set in ``glance-manage.conf`` override those set in
``glance-api.conf``.
