===================
glance-cache-pruner
===================

-------------------
Glance cache pruner
-------------------

:Author: glance@lists.launchpad.net
:Date:   2014-01-16
:Copyright: OpenStack LLC
:Version: 2014.1
:Manual section: 1
:Manual group: cloud computing

SYNOPSIS
========

  glance-cache-pruner [options]

DESCRIPTION
===========

Prunes images from the Glance cache when the space exceeds the value
set in the image_cache_max_size configuration option. This is meant
to be run as a periodic task, perhaps every half-hour.

OPTIONS
========

  **General options**

  .. include:: general_options.rst

FILES
=====

  **/etc/glance/glance-cache.conf**
        Default configuration file for the Glance Cache

  .. include:: footer.rst
