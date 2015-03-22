=============
glance-manage
=============

-------------------------
Glance Management Utility
-------------------------

:Author: glance@lists.launchpad.net
:Date:   2014-01-16
:Copyright: OpenStack LLC
:Version: 2014.1
:Manual section: 1
:Manual group: cloud computing

SYNOPSIS
========

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

  **db**
        This is the prefix for the commands below when used with a space
        rather than a _. For example "db version".

  **db_version**
        This will print the current migration level of a glance database.

  **db_upgrade <VERSION>**
        This will take an existing database and upgrade it to the
        specified VERSION.

  **db_downgrade <VERSION>**
        This will take an existing database and downgrade it to the
        specified VERSION.

  **db_version_control**
        Place the database under migration control.

  **db_sync <VERSION> <CURRENT_VERSION>**
        Place a database under migration control and upgrade, creating
        it first if necessary.

  **db_export_metadefs**
        Export the metadata definitions into json format. By default the
        definitions are exported to /etc/glance/metadefs directory.

  **db_load_metadefs**
        Load the metadata definitions into glance database. By default the
        definitions are imported from /etc/glance/metadefs directory.

  **db_unload_metadefs**
        Unload the metadata definitions. Clears the contents of all the glance
        db tables including metadef_namespace_resource_types, metadef_tags,
        metadef_objects, metadef_resource_types, metadef_namespaces and
        metadef_properties.

OPTIONS
=======

  **General Options**

  .. include:: general_options.rst

  **--sql_connection=CONN_STRING**
        A proper SQLAlchemy connection string as described
        `here <http://www.sqlalchemy.org/docs/05/reference/sqlalchemy/connections.html?highlight=engine#sqlalchemy.create_engine>`_

  .. include:: footer.rst

CONFIGURATION
=============

The following paths are searched for a ``glance-manage.conf`` file in the
following order:

* ``~/.glance``
* ``~/``
* ``/etc/glance``
* ``/etc``

All options set in ``glance-manage.conf`` override those set in
``glance-registry.conf`` and ``glance-api.conf``.
