===================
glance-cache-manage
===================

------------------------
Cache management utility
------------------------

.. include:: header.txt

SYNOPSIS
========

::

  glance-cache-manage <command> [options] [args]

COMMANDS
========

``help <command>``
      Output help for one of the commands below

``list-cached``
      List all images currently cached

``list-queued``
      List all images currently queued for caching

``queue-image``
      Queue an image for caching

``delete-cached-image``
      Purges an image from the cache

``delete-all-cached-images``
      Removes all images from the cache

``delete-queued-image``
      Deletes an image from the cache queue

``delete-all-queued-images``
      Deletes all images from the cache queue

OPTIONS
=======

``--version``
      show program's version number and exit

``-h, --help``
      show this help message and exit

``-v, --verbose``
      Print more verbose output

``-d, --debug``
      Print more verbose output

``-H ADDRESS, --host=ADDRESS``
      Address of Glance API host.
      Default: 0.0.0.0

``-p PORT, --port=PORT``
      Port the Glance API host listens on.
      Default: 9292

``-k, --insecure``
      Explicitly allow glance to perform "insecure" SSL
      (https) requests. The server's certificate will not be
      verified against any certificate authorities. This
      option should be used with caution.

``-A TOKEN, --auth_token=TOKEN``
      Authentication token to use to identify the client to the glance server

``-f, --force``
      Prevent select actions from requesting user confirmation

``-S STRATEGY, --os-auth-strategy=STRATEGY``
      Authentication strategy (keystone or noauth)

.. include:: openstack_options.txt

.. include:: footer.txt
