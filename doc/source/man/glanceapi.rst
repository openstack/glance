==========
glance-api
==========

---------------------------------------
Server for the Glance Image Service API
---------------------------------------

:Author: glance@lists.launchpad.net
:Date:   2010-11-16
:Copyright: OpenStack LLC
:Version: 0.1.2
:Manual section: 1
:Manual group: cloud computing

SYNOPSIS
========

  glance-api [options]

DESCRIPTION
===========

glance-api is a server daemon that serves the Glance API

OPTIONS
=======

  **General options**

  **-v, --verbose**
        Print more verbose output

  **--api_host=HOST**
        Address of host running ``glance-api``. Defaults to `0.0.0.0`.

  **--api_port=PORT**
        Port that ``glance-api`` listens on. Defaults to `9292`.

  **--default_store=STORE**
        The default backend store that Glance should use when storing virtual
        machine images. The default value is `filesystem`. Choices are any of
        `filesystem`, `swift`, or `s3`

  **--filesystem_store_datadir=DIR**
        The directory that the `filesystem` backend store should use to write
        virtual machine images. This directory should be writeable by the user
        running ``glance-api``

FILES
=====

None

SEE ALSO
========

* `OpenStack Glance <http://glance.openstack.org>`__

BUGS
====

* Glance is sourced in Launchpad so you can view current bugs at `OpenStack Glance <http://glance.openstack.org>`__
