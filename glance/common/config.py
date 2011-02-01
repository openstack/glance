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


DEFAULT_LOG_FORMAT = "%(asctime)s (%(name)s): %(levelname)s %(message)s"
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


def add_log_options(parser):
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
    group.add_option('--log-handler', default='stream', metavar="HANDLER",
                     choices=LOGGING_HANDLER_CHOICES,
                     help="What logging handler to use? "
                           "Default: %default")
    group.add_option('--log-format', metavar="FORMAT",
                      default=DEFAULT_LOG_FORMAT,
                      help="Format string for log records. Default: %default")
    group.add_option('--log-file', default=None,
                      metavar="PATH",
                      help="(Optional) Name of log file to output to.")
    group.add_option("--log-dir", default=None,
                      help="(Optional) The directory to keep log files in "
                           "(will be prepended to --logfile)")
    parser.add_option_group(group)


def setup_logging(prog_name, options):
    """
    Sets up the logging options for a log with supplied name

    :param prog_name: Name of the log/program
    :param options: Mapping of typed option key/values
    """

    if options['log_config']:
        # Use a logging configuration file for all settings...
        if os.path.exists(options['log_config']):
            logging.config.fileConfig(options['log_config'])
        else:
            raise RuntimeError("Unable to locate specified logging "
                               "config file: %s" % options['log_config'])
    else:
        # Set log configuration from options...
        logger = logging.getLogger(prog_name)
        formatter = logging.Formatter(options['log_format'])

        if options['log_handler'] == 'syslog':
            syslog = logging.handlers.SysLogHandler(address='/dev/log')
            syslog.setFormatter(formatter)
            logger.addHandler(syslog)
        else:
            logfile = options['log_file']
            logdir = options['log_dir']
            if not logfile:
                logfile = '%s.log' % prog_name
            if logdir:
                logfile = os.path.join(logdir, logfile)
            logfile = logging.FileHandler(logfile)
            logfile.setFormatter(formatter)
            logger.addHandler(logfile)

    if options['verbose']:
        logging.getLogger(prog_name).setLevel(logging.DEBUG)
    else:
        logging.getLogger(prog_name).setLevel(logging.WARNING)
