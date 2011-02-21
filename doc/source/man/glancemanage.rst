=============
glance-manage
=============

-------------------------
Glance Management Utility
-------------------------

:Author: glance@lists.launchpad.net
:Date:   2010-11-16
:Copyright: OpenStack LLC
:Version: 0.1.2
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

OPTIONS
=======

  **General options**

  **-v, --verbose**
        Print more verbose output

  **--sql_connection=CONN_STRING**
        A proper SQLAlchemy connection string as described
        `here <http://www.sqlalchemy.org/docs/05/reference/sqlalchemy/connections.html?highlight=engine#sqlalchemy.create_engine>`_

FILES
=====

None

SEE ALSO
========

* `OpenStack Glance <http://glance.openstack.org>`__

BUGS
====

* Glance is sourced in Launchpad so you can view current bugs at `OpenStack Glance <http://glance.openstack.org>`__
