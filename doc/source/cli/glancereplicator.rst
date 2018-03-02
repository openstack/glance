=================
glance-replicator
=================

---------------------------------------------
Replicate images across multiple data centers
---------------------------------------------

.. include:: header.txt

SYNOPSIS
========

::

  glance-replicator <command> [options] [args]

DESCRIPTION
===========

glance-replicator is a utility can be used to populate a new glance
server using the images stored in an existing glance server. The images
in the replicated glance server preserve the uuids, metadata, and image
data from the original.

COMMANDS
========

``help <command>``
      Output help for one of the commands below

``compare``
      What is missing from the slave glance?

``dump``
      Dump the contents of a glance instance to local disk.

``livecopy``
      Load the contents of one glance instance into another.

``load``
      Load the contents of a local directory into glance.

``size``
      Determine the size of a glance instance if dumped to disk.

OPTIONS
=======

``-h, --help``
      Show this help message and exit

``-c CHUNKSIZE, --chunksize=CHUNKSIZE``
      Amount of data to transfer per HTTP write

``-d, --debug``
      Print debugging information

``-D DONTREPLICATE, --dontreplicate=DONTREPLICATE``
      List of fields to not replicate

``-m, --metaonly``
      Only replicate metadata, not images

``-l LOGFILE, --logfile=LOGFILE``
      Path of file to log to

``-s, --syslog``
      Log to syslog instead of a file

``-t TOKEN, --token=TOKEN``
      Pass in your authentication token if you have one. If
      you use this option the same token is used for both
      the master and the slave.

``-M MASTERTOKEN, --mastertoken=MASTERTOKEN``
      Pass in your authentication token if you have one.
      This is the token used for the master.

``-S SLAVETOKEN, --slavetoken=SLAVETOKEN``
      Pass in your authentication token if you have one.
      This is the token used for the slave.

``-v, --verbose``
      Print more verbose output

.. include:: footer.txt
