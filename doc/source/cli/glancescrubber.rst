===============
glance-scrubber
===============

--------------------
Glance scrub service
--------------------

.. include:: header.txt

SYNOPSIS
========

::

  glance-scrubber [options]

DESCRIPTION
===========

glance-scrubber is a utility that allows an operator to configure Glance for
the asynchronous deletion of images or to revert the image's status from
`pending_delete` to `active`.  Whether this makes sense for your deployment
depends upon the storage backend you are using and the size of typical images
handled by your Glance installation.

An image in glance is really a combination of an image record (stored in the
database) and a file of image data (stored in a storage backend).  Under normal
operation, the image-delete call is synchronous, that is, Glance receives the
DELETE request, deletes the image data from the storage backend, then deletes
the image record from the database, and finally returns a 204 as the result of
the call.  If the backend is fast and deletion time is not a function of data
size, these operations occur very quickly.  For backends where deletion time is
a function of data size, however, the image-delete operation can take a
significant amount of time to complete, to the point where a client may timeout
waiting for the response.  This in turn leads to user dissatisfaction.

To avoid this problem, Glance has a ``delayed_delete`` configuration option
(False by default) that may be set in the **glance-api.conf** file.  With this
option enabled, when Glance receives a DELETE request, it does *only* the
database part of the request, marking the image's status as ``pending_delete``,
and returns immediately.  (The ``pending_delete`` status is not visible to
users; an image-show request for such an image will return 404.)  However, it
is important to note that when ``delayed_delete`` is enabled, *Glance does not
delete image data from the storage backend*.  That's where the glance-scrubber
comes in.

The glance-scrubber cleans up images that have been deleted.  If you run Glance
with ``delayed_delete`` enabled, you *must* run the glance-scrubber
occasionally or your storage backend will eventually fill up with "deleted"
image data.

The glance-scrubber can also revert a image to `active` if operators delete
the image by mistake and the pending-delete is enabled in Glance. Please make
sure the ``glance-scrubber`` is not running before restoring the image to avoid
image data inconsistency.

Configuration of glance-scrubber is done in the **glance-scrubber.conf** file.
Options are explained in detail in comments in the sample configuration file,
so we only point out a few of them here.

``scrub_time``
    minimum time in seconds that an image will stay in ``pending_delete``
    status (default is 0)

``scrub_pool_size``
    configures a thread pool so that scrubbing can be performed in parallel
    (default is 1, that is, serial scrubbing)

``daemon``
    a boolean indicating whether the scrubber should run as a daemon
    (default is False)

``wakeup_time``
    time in seconds between runs when the scrubber is run in daemon mode
    (ignored if the scrubber is not being run in daemon mode)

``metadata_encryption_key``
    If your **glance-api.conf** sets a value for this option (the default is to
    leave it unset), you must include the same setting in your
    **glance-scrubber.conf** or the scrubber won't be able to determine the
    locations of your image data.

``restore``
    reset the specified image's status from'pending_delete' to 'active' when
    the image is deleted by mistake.

``[database]``
    As of the Queens release of Glance (16.0.0), the glance-scrubber does not
    use the deprecated Glance registry, but instead contacts the Glance
    database directly.  Thus your **glance-scrubber.conf** file must contain a
    [database] section specifying the relevant information.

``[glance_store]``
   This section of the file contains the configuration information for the
   storage backends used by your Glance installation.

The usual situation is that whatever your **glance-api.conf** has for the
``[database]`` and ``[glance_store]`` configuration groups should go into your
**glance-scrubber.conf**, too.  Of course, if you have heavily customized your
setup, you know better than we do what you are doing.  The key thing is that
the scrubber needs to be able to access the Glance database to determine what
images need to be scrubbed (and to mark them as deleted once their associated
data has been removed from the storage backend), and it needs the glance_store
information so it can delete the image data.

OPTIONS
=======

**General options**

.. include:: general_options.txt

**-D, --daemon**
      Run as a long-running process. When not specified (the
      default) run the scrub operation once and then exits.
      When specified do not exit and run scrub on
      wakeup_time interval as specified in the config.

**--nodaemon**
      The inverse of --daemon. Runs the scrub operation once and
      then exits. This is the default.

**--restore <IMAGE_ID>**
      Restore the specified image status from 'pending_delete' to 'active'.

FILES
=====

**/etc/glance/glance-scrubber.conf**
    Default configuration file for the Glance Scrubber

.. include:: footer.txt
