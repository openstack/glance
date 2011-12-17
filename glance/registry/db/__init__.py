# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2010-2011 OpenStack LLC.
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

from glance.common import cfg


def add_options(conf):
    """
    Adds any configuration options that the db layer might have.

    :param conf: A ConfigOpts object
    :retval None
    """
    conf.register_group(cfg.OptGroup('registrydb',
                                title='Registry Database Options',
                                help='The following configuration options '
                                     'are specific to the Glance image '
                                     'registry database.'))
    conf.register_cli_opt(cfg.StrOpt('sql_connection',
                                     metavar='CONNECTION',
                                     help='A valid SQLAlchemy connection '
                                          'string for the registry database. '
                                          'Default: %default'))
