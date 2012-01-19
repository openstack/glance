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
import os
import sys

from glance import version
from glance.common import cfg
from glance.common import wsgi


paste_deploy_group = cfg.OptGroup('paste_deploy')
paste_deploy_opts = [
    cfg.StrOpt('flavor'),
    cfg.StrOpt('config_file'),
    ]


class GlanceConfigOpts(cfg.CommonConfigOpts):

    def __init__(self, default_config_files=None, **kwargs):
        super(GlanceConfigOpts, self).__init__(
            project='glance',
            version='%%prog %s' % version.version_string(),
            default_config_files=default_config_files,
            **kwargs)


class GlanceCacheConfigOpts(GlanceConfigOpts):

    def __init__(self, **kwargs):
        config_files = cfg.find_config_files(project='glance',
                                             prog='glance-cache')
        super(GlanceCacheConfigOpts, self).__init__(config_files, **kwargs)


def setup_logging(conf):
    """
    Sets up the logging options for a log with supplied name

    :param conf: a cfg.ConfOpts object
    """

    if conf.log_config:
        # Use a logging configuration file for all settings...
        if os.path.exists(conf.log_config):
            logging.config.fileConfig(conf.log_config)
            return
        else:
            raise RuntimeError("Unable to locate specified logging "
                               "config file: %s" % conf.log_config)

    root_logger = logging.root
    if conf.debug:
        root_logger.setLevel(logging.DEBUG)
    elif conf.verbose:
        root_logger.setLevel(logging.INFO)
    else:
        root_logger.setLevel(logging.WARNING)

    formatter = logging.Formatter(conf.log_format, conf.log_date_format)

    if conf.use_syslog:
        try:
            facility = getattr(logging.handlers.SysLogHandler,
                               conf.syslog_log_facility)
        except AttributeError:
            raise ValueError(_("Invalid syslog facility"))

        handler = logging.handlers.SysLogHandler(address='/dev/log',
                                                 facility=facility)
    elif conf.log_file:
        logfile = conf.log_file
        if conf.log_dir:
            logfile = os.path.join(conf.log_dir, logfile)
        handler = logging.handlers.WatchedFileHandler(logfile)
    else:
        handler = logging.StreamHandler(sys.stdout)

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)


def _register_paste_deploy_opts(conf):
    """
    Idempotent registration of paste_deploy option group

    :param conf: a cfg.ConfigOpts object
    """
    conf.register_group(paste_deploy_group)
    conf.register_opts(paste_deploy_opts, group=paste_deploy_group)


def _get_deployment_flavor(conf):
    """
    Retrieve the paste_deploy.flavor config item, formatted appropriately
    for appending to the application name.

    :param conf: a cfg.ConfigOpts object
    """
    _register_paste_deploy_opts(conf)
    flavor = conf.paste_deploy.flavor
    return '' if not flavor else ('-' + flavor)


def _get_deployment_config_file(conf):
    """
    Retrieve the deployment_config_file config item, formatted as an
    absolute pathname.

   :param conf: a cfg.ConfigOpts object
    """
    _register_paste_deploy_opts(conf)
    config_file = conf.paste_deploy.config_file
    if not config_file:
        # Assume paste config is in a paste.ini file corresponding
        # to the last config file
        path = conf.config_file[-1].replace(".conf", "-paste.ini")
    else:
        path = config_file
    return os.path.abspath(path)


def load_paste_app(conf, app_name=None):
    """
    Builds and returns a WSGI app from a paste config file.

    We assume the last config file specified in the supplied ConfigOpts
    object is the paste config file.

    :param conf: a cfg.ConfigOpts object
    :param app_name: name of the application to load

    :raises RuntimeError when config file cannot be located or application
            cannot be loaded from config file
    """
    if app_name is None:
        app_name = conf.prog

    # append the deployment flavor to the application name,
    # in order to identify the appropriate paste pipeline
    app_name += _get_deployment_flavor(conf)

    conf_file = _get_deployment_config_file(conf)

    try:
        # Setup logging early
        setup_logging(conf)

        logger = logging.getLogger(app_name)

        app = wsgi.paste_deploy_app(conf_file, app_name, conf)

        # Log the options used when starting if we're in debug mode...
        if conf.debug:
            conf.log_opt_values(logging.getLogger(app_name), logging.DEBUG)

        return app
    except (LookupError, ImportError), e:
        raise RuntimeError("Unable to load %(app_name)s from "
                           "configuration file %(conf_file)s."
                           "\nGot: %(e)r" % locals())
