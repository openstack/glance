===================
glance-cache-manage
===================

------------------------
Cache management utility
------------------------

:Author: glance@lists.launchpad.net
:Date:   2012-01-03
:Copyright: OpenStack LLC
:Version: 2012.1-dev
:Manual section: 1
:Manual group: cloud computing

SYNOPSIS
========

  glance-cache-manage <command> [options] [args]

COMMANDS
========

  **help <command>**
        Output help for one of the commands below

  **list-cached**
        List all images currently cached

  **list-queued**
        List all images currently queued for caching

  **queue-image**
        Queue an image for caching

  **delete-cached-image**
        Purges an image from the cache

  **delete-all-cached-images**
        Removes all images from the cache

  **delete-queued-image**
        Deletes an image from the cache queue

  **delete-all-queued-images**
        Deletes all images from the cache queue

  **clean**
        Removes any stale or invalid image files from the cache

OPTIONS
=======

  **--version**
        show program's version number and exit

  **-h, --help**
        show this help message and exit
        
  **-v, --verbose**
        Print more verbose output

  **-d, --debug**
        Print more verbose output

  **-H ADDRESS, --host=ADDRESS**
        Address of Glance API host.
        Default: 0.0.0.0

  **-p PORT, --port=PORT**
        Port the Glance API host listens on.
        Default: 9292

  **-A TOKEN, --auth_token=TOKEN**
        Authentication token to use to identify the client to the glance server

  **-f, --force**
        Prevent select actions from requesting user confirmation

SEE ALSO
========

* `OpenStack Glance <http://glance.openstack.org>`__

BUGS
====

* Glance is sourced in Launchpad so you can view current bugs at `OpenStack Glance <http://glance.openstack.org>`__
