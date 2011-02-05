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

import ConfigParser
import logging
import logging.config
import logging.handlers
import optparse
import os
import re
import sys

from paste import deploy

import glance.common.exception as exception

DEFAULT_LOG_FORMAT = "%(asctime)s %(levelname)8s [%(name)s] %(message)s"
DEFAULT_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_LOG_HANDLER = 'stream'
LOGGING_HANDLER_CHOICES = ['syslog', 'file', 'stream']


def parse_options(parser, cli_args=None, defaults=None):
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
    :param defaults: (optional) mapping of default values for options
    :retval tuple of (options, args)
    """

    if defaults:
        int_re = re.compile(r'^\d+$')
        float_re = re.compile(r'^([+-]?(((\d+(\.)?)|(\d*\.\d+))'
                              '([eE][+-]?\d+)?))$')
        for key, value in defaults.items():
            # Do our best to figure out what the actual option
            # type is underneath...
            if value.lower() in ('true', 'on'):
                value = True
            elif value.lower() in ('false', 'off'):
                value = False
            elif int_re.match(value):
                value = int(value)
            elif float_re.match(value):
                value = float(value)
            defaults[key] = value

        parser.set_defaults(**defaults)
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
    group.add_option('--config', default=None,
                     help="Configuration file to read when loading "
                          "application. If missing, the first argument is "
                          "used. If no arguments are found, then a set of "
                          "standard directories are searched for a config "
                          "file.")
    group.add_option("--pid-file", default=None, metavar="PATH",
                     help="(Optional) Name of pid file for the server. "
                          "If not specified, the pid file will be named "
                          "/var/run/glance/<SERVER>.pid.")
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
    # Note that we use a hard-coded log format in the options
    # because of Paste.Deploy bug #379
    # http://trac.pythonpaste.org/pythonpaste/ticket/379
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


def get_config_file_options(conf_file=None, conf_dirs=None, app_name=None):
    """
    Look for configuration files in a number of standard directories and
    return a mapping of options found in the files.

    The files that are searched for are in the following order, with
    options found in later files overriding options found in earlier
    files::

        /etc/glance.cnf
        /etc/glance/glance.cnf
        ~/glance.cnf
        ~/.glance/glance.cnf
        ./glance.cnf
        supplied conf_file param, if any.

    :param conf_file: (optional) config file to read options from. Options
                      from this config file override all others
    :param conf_dirs: (optional) sequence of directory paths to search for
                      config files. Generally just used in testing
    :param app_name: (optional) name of application we're interested in.
                     Supplying this will ensure that only the [DEFAULT]
                     section and the [app_name] sections of the config
                     files will be read. If not supplied (the default), all
                     sections are read for configuration options.

    :retval Mapping of configuration options read from config files
    """

    # Note that we do this in reverse priority order because
    # later configs overwrite the values of previously-read
    # configuration options

    fixup_path = lambda p: os.path.abspath(os.path.expanduser(p))
    config_file_dirs = conf_dirs or \
                           ['/etc',
                            '/etc/glance/',
                            fixup_path('~'),
                            fixup_path(os.path.join('~', '.glance')),
                            fixup_path(os.getcwd())]

    config_files = []
    results = {}
    for cfg_dir in config_file_dirs:
        cfg_file = os.path.join(cfg_dir, 'glance.cnf')
        if os.path.exists(cfg_file):
            config_files.append(cfg_file)

    if conf_file:
        config_files.append(fixup_path(conf_file))

    cp = ConfigParser.ConfigParser()
    for config_file in config_files:
        if not cp.read(config_file):
            msg = 'Unable to read config file: %s' % config_file
            raise RuntimeError(msg)

        results.update(cp.defaults())
        # Add any sections we have in the configuration file, too...
        for section in cp.sections():
            section_option_keys = cp.options(section)
            if not app_name or (app_name == section):
                for k in section_option_keys:
                    results[k] = cp.get(section, k)

    return results


def find_config_file(options, args):
    """
    Return the first config file found.

    We search for the paste config file in the following order:
    * If --config-file option is used, use that
    * If args[0] is a file, use that
    * Search for glance.cnf in standard directories:
        * .
        * ~.glance/
        * ~
        * /etc/glance
        * /etc

    :retval Full path to config file, or None if no config file found
    """

    if getattr(options, 'config', None):
        if os.path.exists(options.config_file):
            return os.path.abspath(getattr(options, 'config'))
    elif args:
        if os.path.exists(args[0]):
            return os.path.abspath(args[0])
    config_file_dirs = [os.path.abspath(os.getcwd()),
                        os.path.expanduser(os.path.join('~', '.glance')),
                        os.path.expanduser('~'),
                        '/etc/glance/',
                        '/etc']

    for d in config_file_dirs:
        if not os.path.isdir(d):
            continue
        files = os.listdir(d)
        for f in files:
            if os.path.basename(f) == 'glance.cnf':
                return f


def load_paste_app(app_name, options, args):
    """
    Builds and returns a WSGI app from a paste config file.

    We search for the paste config file in the following order:
    * If --config-file option is used, use that
    * If args[0] is a file, use that
    * Search for glance.cnf in standard directories:
        * .
        * ~.glance/
        * ~
        * /etc/glance
        * /etc

    :param app_name: Name of the application to load
    :param options: Set of typed options returned from parse_options()
    :param args: Command line arguments from argv[1:]

    :raises RuntimeError when config file cannot be located or application
            cannot be loaded from config file
    """
    conf_file = find_config_file(options, args)
    if not conf_file:
        raise RuntimeError("Unable to locate any configuration file. "
                            "Cannot load application %s" % app_name)
    try:
        app = deploy.loadapp("config:%s" % conf_file, name=app_name,
                             global_conf=options_to_conf(options))
    except (LookupError, ImportError), e:
        raise RuntimeError("Unable to load %(app_name)s from "
                           "configuration file %(conf_file)s."
                           "\nGot: %(e)r" % locals())
    return app
