=============
glance-status
=============

---------------------
Glance Status Utility
---------------------

.. include:: header.txt

SYNOPSIS
========

::

  glance-status [options]

DESCRIPTION
===========

``glance-status`` is a command line utility to aid operators in upgrading
glance by running programmable checks for things that might prevent upgrades.

COMMANDS
========

``upgrade``
      This is the prefix for checking the glance deployment for any upgrade
      issues that might prevent glance from upgrading.

You can also run with a category argument such as ``upgrade`` to see a list of
all commands in that category::

    glance-status upgrade

These sections describe the available categories and arguments for
:command:`glance-status`.

Categories and commands
-----------------------

``glance-status upgrade check``
  Performs a release-specific readiness check before restarting services with
  new code, or upgrading. This command expects to have complete configuration
  and access to the database.

  **Return Codes**

  .. list-table::
     :widths: 20 80
     :header-rows: 1

     * - Return code
       - Description
     * - 0
       - All upgrade readiness checks passed successfully and there is nothing
         to do.
     * - 1
       - At least one check encountered an issue and requires further
         investigation. This is considered a warning but the upgrade may be OK.
     * - 2
       - There was an upgrade status check failure that needs to be
         investigated. This should be considered something that stops an
         upgrade.
     * - 255
       - An unexpected error occurred.

  **History of Checks**

  **18.0.0 (Stein)**

  * Placeholder to be filled in with checks as they are added in Stein.

OPTIONS
=======

**General Options**

``-h, --help``
      show this help message and exit

``--config-dir DIR``
      Path to a config directory to pull `*.conf` files from.
      This file set is sorted, so as to provide a predictable
      parse order if individual options are over-ridden. The
      set is parsed after the file(s) specified via previous
      --config-file, arguments hence over-ridden options in
      the directory take precedence.

``--config-file PATH``
      Path to a config file to use. Multiple config files can
      be specified, with values in later files taking
      precedence. Defaults to None.

.. include:: footer.txt
