===============
glance-registry
===============

--------------------------------------
Server for the Glance Registry Service
--------------------------------------

:Author: glance@lists.launchpad.net
:Date:   2010-11-16
:Copyright: OpenStack LLC
:Version: 0.1.2
:Manual section: 1
:Manual group: cloud computing

SYNOPSIS
========

  glance-registry [options]

DESCRIPTION
===========

glance-registry is a server daemon that serves image metadata through a
REST-like API.

OPTIONS
=======

  **General options**

  **-v, --verbose**
        Print more verbose output

  **--registry_host=HOST**
        Address of host running ``glance-registry``. Defaults to `0.0.0.0`.

  **--registry_port=PORT**
        Port that ``glance-registry`` listens on. Defaults to `9191`.

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
