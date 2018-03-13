====================
glance-cache-cleaner
====================

----------------------------------------------------------------
Glance Image Cache Invalid Cache Entry and Stalled Image cleaner
----------------------------------------------------------------

.. include:: header.txt

SYNOPSIS
========

::

  glance-cache-cleaner [options]

DESCRIPTION
===========

This is meant to be run as a periodic task from cron.

If something goes wrong while we're caching an image (for example the fetch
times out, or an exception is raised), we create an 'invalid' entry. These
entries are left around for debugging purposes. However, after some period of
time, we want to clean these up.

Also, if an incomplete image hangs around past the image_cache_stall_time
period, we automatically sweep it up.

OPTIONS
=======

**General options**

.. include:: general_options.txt

FILES
=====

**/etc/glance/glance-cache.conf**
  Default configuration file for the Glance Cache

.. include:: footer.txt
