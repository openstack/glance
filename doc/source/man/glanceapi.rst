==========
glance-api
==========

---------------------------------------
Server for the Glance Image Service API
---------------------------------------

:Author: glance@lists.launchpad.net
:Date:   2014-01-02
:Copyright: OpenStack LLC
:Version: 2014.1
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

  **-h, --help**
        Show the help message and exit

  **--version**
        Print the version number and exit

  **-v, --verbose**
        Print more verbose output

  **--noverbose**
        Disable verbose output

  **-d, --debug**
        Print debugging output (set logging level to DEBUG instead of
        default WARNING level)

  **--nodebug**
        Disable debugging output

  **--use-syslog**
        Use syslog for logging

  **--nouse-syslog**
        Disable the use of syslog for logging

  **--syslog-log-facility SYSLOG_LOG_FACILITY**
        syslog facility to receive log lines

  **--config-dir DIR**
        Path to a config directory to pull \*.conf files from. This
        file set is sorted, so as to provide a predictable parse order
        if individual options are over-ridden. The set is parsed after
        the file(s) specified via previous --config-file, arguments hence
        over-ridden options in the directory take precedence. This means
        that configuration from files in a specified config-dir will
        always take precedence over configuration from files specified
        by --config-file, regardless to argument order.

  **--config-file PATH**
        Path to a config file to use. Multiple config files can be
        specified by using this flag multiple times, for example,
        --config-file <file1> --config-file <file2>. Values in latter
        files take precedence. If not specified, the default file
        used is: /etc/glance/glance-api.conf

  **--log-config PATH**
        If this option is specified, the logging configuration file
        specified is used and overrides any other logging options
        specified. Please see the Python logging module documentation
        for details on logging configuration files.

  **--log-format FORMAT**
        A logging.Formatter log message format string which may use any
        of the available logging.LogRecord attributes. Default: None

  **--log-date-format DATE_FORMAT**
        Format string for %(asctime)s in log records. Default: None

  **--log-file PATH, --logfile PATH**
        (Optional) Name of log file to output to. If not set, logging
        will go to stdout.

  **--log-dir LOG_DIR, --logdir LOG_DIR**
        (Optional) The directory to keep log files in (will be prepended
        to --log-file)

FILES
=====

  **/etc/glance/glance-api.conf**
        Default configuration file for Glance API

SEE ALSO
========

* `OpenStack Glance <http://glance.openstack.org>`__

BUGS
====

* Glance is sourced in Launchpad so you can view current bugs at `OpenStack Glance <http://glance.openstack.org>`__
