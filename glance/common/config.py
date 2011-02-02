#!/usr/bin/env python
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
Routines for configuring Glance
"""

import logging
import logging.config
import logging.handlers
import optparse
import os
import sys

import glance.common.exception as exception

DEFAULT_LOG_FORMAT = "%(asctime)s %(levelname)8s [%(name)s] %(message)s"
DEFAULT_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_LOG_HANDLER = 'stream'
LOGGING_HANDLER_CHOICES = ['syslog', 'file', 'stream']


def parse_options(parser, cli_args=None):
    """
    Returns the parsed CLI options, command to run and its arguments, merged
    with any same-named options found in a configuration file.

    The function returns a tuple of (options, args), where options is a
    mapping of option key/str(value) pairs, and args is the set of arguments
    (not options) supplied on the command-line.

    The reason that the option values are returned as strings only is that
    ConfigParser and paste.deploy only accept string values...

    :param parser: The option parser
    :param cli_args: (Optional) Set of arguments to process. If not present,
                     sys.argv[1:] is used.
    :retval tuple of (options, args)
    """

    (options, args) = parser.parse_args(cli_args)

    return (vars(options), args)


def options_to_conf(options):
    """
    Converts a mapping of options having typed values into
    a mapping of configuration options having only stringified values.

    This method is used to convert the return of parse_options()[0]
    into the configuration mapping that is expected by ConfigParser
    and paste.deploy.

    :params options: Mapping of typed option key/values
    """
    return dict([(k, str(v)) for k, v in options.items()])


def add_common_options(parser):
    """
    Given a supplied optparse.OptionParser, adds an OptionGroup that
    represents all common configuration options.

    :param parser: optparse.OptionParser
    """
    help_text = "The following configuration options are common to "\
                "all glance programs."

    group = optparse.OptionGroup(parser, "Common Options", help_text)
    group.add_option('-v', '--verbose', default=False, dest="verbose",
                     action="store_true",
                     help="Print more verbose output")
    group.add_option('-d', '--debug', default=False, dest="debug",
                     action="store_true",
                     help="Print debugging output")
    parser.add_option_group(group)


def add_daemon_options(parser):
    """
    Given a supplied optparse.OptionParser, adds an OptionGroup that
    represents all the configuration options around daemonization.

    :param parser: optparse.OptionParser
    """
    help_text = "The following configuration options are specific to "\
                "the daemonizing of this program."

    group = optparse.OptionGroup(parser, "Daemon Options", help_text)
    group.add_option('--daemonize', default=False, action="store_true",
                     help="Daemonize this process")
    group.add_option("--pidfile", default=None,
                     help="(Optional) Name of pid file for the server")
    group.add_option("--uid", type=int, default=os.getuid(),
                     help="uid under which to run. Default: %default")
    group.add_option("--gid", type=int, default=os.getgid(),
                     help="gid under which to run. Default: %default")
    group.add_option('--working-directory', '--working-dir',
                     default=os.path.abspath(os.getcwd()),
                     help="The working directory. Default: %default")
    parser.add_option_group(group)


def add_log_options(prog_name, parser):
    """
    Given a supplied optparse.OptionParser, adds an OptionGroup that
    represents all the configuration options around logging.

    :param parser: optparse.OptionParser
    """
    help_text = "The following configuration options are specific to logging "\
                "functionality for this program."

    group = optparse.OptionGroup(parser, "Logging Options", help_text)
    group.add_option('--log-config', default=None, metavar="PATH",
                     help="If this option is specified, the logging "
                          "configuration file specified is used and overrides "
                          "any other logging options specified. Please see "
                          "the Python logging module documentation for "
                          "details on logging configuration files.")
    group.add_option('--log-handler', default=DEFAULT_LOG_HANDLER,
                     metavar="HANDLER",
                     choices=LOGGING_HANDLER_CHOICES,
                     help="What logging handler to use? "
                           "Default: %default")
    group.add_option('--log-format', metavar="FORMAT",
                      default=DEFAULT_LOG_FORMAT,
                      help="Format string for log records. Default: %default")
    group.add_option('--log-date-format', metavar="FORMAT",
                      default=DEFAULT_LOG_DATE_FORMAT,
                      help="Format string for %(asctime)s in log records. "
                           "Default: %default")
    group.add_option('--log-file', default="%s.log" % prog_name,
                      metavar="PATH",
                      help="(Optional) Name of log file to output to.")
    group.add_option("--log-dir", default=None,
                      help="(Optional) The directory to keep log files in "
                           "(will be prepended to --logfile)")
    parser.add_option_group(group)


def setup_logging(options):
    """
    Sets up the logging options for a log with supplied name

    :param options: Mapping of typed option key/values
    """

    if options.get('log_config', None):
        # Use a logging configuration file for all settings...
        if os.path.exists(options['log_config']):
            logging.config.fileConfig(options['log_config'])
            return
        else:
            raise RuntimeError("Unable to locate specified logging "
                               "config file: %s" % options['log_config'])

    debug = options.get('debug', False)
    verbose = options.get('verbose', False)
    root_logger = logging.root
    if debug:
        root_logger.setLevel(logging.DEBUG)
    elif verbose:
        root_logger.setLevel(logging.INFO)
    else:
        root_logger.setLevel(logging.WARNING)

    # Set log configuration from options...
    log_format = options.get('log_format', DEFAULT_LOG_FORMAT)
    log_date_format = options.get('log_date_format', DEFAULT_LOG_DATE_FORMAT)
    formatter = logging.Formatter(log_format, log_date_format)

    log_handler = options.get('log_handler', DEFAULT_LOG_HANDLER)
    if log_handler == 'syslog':
        syslog = logging.handlers.SysLogHandler(address='/dev/log')
        syslog.setFormatter(formatter)
        root_logger.addHandler(syslog)
    elif log_handler == 'file':
        logfile = options['log_file']
        logdir = options['log_dir']
        if logdir:
            logfile = os.path.join(logdir, logfile)
        logfile = logging.FileHandler(logfile)
        logfile.setFormatter(formatter)
        logfile.setFormatter(formatter)
        root_logger.addHandler(logfile)
    elif log_handler == 'stream':
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
    else:
        raise exception.BadInputError(
            "unrecognized log handler '%(log_handler)s'" % locals())

    # Log the options used when starting if we're in debug mode...
    if debug:
        root_logger.debug("*" * 80)
        root_logger.debug("Options:")
        root_logger.debug("========")
        for key, value in sorted(options.items()):
            root_logger.debug("%(key)-30s %(value)s" % locals())
        root_logger.debug("*" * 80)
