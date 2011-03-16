..
      Copyright 2011 OpenStack, LLC
      All Rights Reserved.

      Licensed under the Apache License, Version 2.0 (the "License"); you may
      not use this file except in compliance with the License. You may obtain
      a copy of the License at

          http://www.apache.org/licenses/LICENSE-2.0

      Unless required by applicable law or agreed to in writing, software
      distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
      WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
      License for the specific language governing permissions and limitations
      under the License.

Configuring Glance
==================

.. todo:: Complete details of configuration with paste.deploy config files

Configuring Logging in Glance
-----------------------------

There are a number of configuration options in Glance that control how Glance
servers log messages. The configuration options are specified in the
``glance.conf`` config file.

* ``--log-config=PATH``

Optional. Default: ``None``

Specified on the command line only.

Takes a path to a configuration file to use for configuring logging.

* ``--log-format``

*Because of a bug in the PasteDeploy package, this option is only available
on the command line.*

Optional. Default: ``%(asctime)s %(levelname)8s [%(name)s] %(message)s``

The format of the log records. See the
`logging module <http://docs.python.org/library/logging.html>`_ documentation for
more information on setting this format string.

* ``log_file`` (``--log-file`` when specified on the command line)

The filepath of the file to use for logging messages from Glance's servers. If
missing, the default is to output messages to ``stdout``, so if you are running
Glance servers in a daemon mode (using ``glance-control``) you should make
sure that the ``log_file`` option is set appropriately.

* ``log_dir`` (``--log-dir`` when specified on the command line)

The filepath of the directory to use for log files. If not specified (the default)
the ``log_file`` is used as an absolute filepath.

* ``log_date_format`` (``--log-date-format`` when specified from the command line)

The format string for timestamps in the log output.

Defaults to ``%Y-%m-%d %H:%M:%S``. See the
`logging module <http://docs.python.org/library/logging.html>`_ documentation for
more information on setting this format string.
