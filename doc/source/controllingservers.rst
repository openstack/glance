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

Controlling Glance Servers
==========================

This section describes the ways to start, stop, and reload Glance's server
programs.

Starting a server
-----------------

There are two ways to start a Glance server (either the API server or the
reference implementation registry server that ships with Glance):

* Manually calling the server program

* Using the ``glance-control`` server daemon wrapper program

Manually starting the server
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The first is by directly calling the server program, passing in command-line
options and a single argument for the ``paste.deploy`` configuration file to
use when configuring the server application.

.. note::

  Glance ships with an ``etc/`` directory that contains sample ``paste.deploy``
  configuration files that you can copy to a standard configuation directory and
  adapt for your own uses.

Here is an example showing how you can manually start the ``glance-api`` server
in a shell.::

  $> sudo glance-api etc/glance.cnf.sample --debug
  2011-02-04 17:12:28    DEBUG [root] ********************************************************************************
  2011-02-04 17:12:28    DEBUG [root] Options:
  2011-02-04 17:12:28    DEBUG [root] ========
  2011-02-04 17:12:28    DEBUG [root] debug                          True
  2011-02-04 17:12:28    DEBUG [root] default_store                  file
  2011-02-04 17:12:28    DEBUG [root] filesystem_store_datadir       /var/lib/glance/images/
  2011-02-04 17:12:28    DEBUG [root] host                           0.0.0.0
  2011-02-04 17:12:28    DEBUG [root] log_config                     None
  2011-02-04 17:12:28    DEBUG [root] log_date_format                %Y-%m-%d %H:%M:%S
  2011-02-04 17:12:28    DEBUG [root] log_dir                        None
  2011-02-04 17:12:28    DEBUG [root] log_file                       glance-api.log
  2011-02-04 17:12:28    DEBUG [root] log_handler                    stream
  2011-02-04 17:12:28    DEBUG [root] port                           9292
  2011-02-04 17:12:28    DEBUG [root] registry_host                  0.0.0.0
  2011-02-04 17:12:28    DEBUG [root] registry_port                  9191
  2011-02-04 17:12:28    DEBUG [root] verbose                        False
  2011-02-04 17:12:28    DEBUG [root] ********************************************************************************
  2011-02-04 17:12:28    DEBUG [routes.middleware] Initialized with method overriding = True, and path info altering = True
  (16940) wsgi starting up on http://0.0.0.0:9292/

Simply supply the configuration file as the first argument
(``etc/glance.cnf.sample`` in the above example) and then any options you
want to use (``--debug`` was used above to show some of the debugging
output that the server shows when starting up. Call the server program
with ``--help`` to see all available options you can specify on the
command line.

For more information on configuring the server via the ``paste.deploy``
configuration files, see the section entitled
:doc:`Configuring Glance servers <configuring>`

Note that the server does not `daemonize` itself when run manually
from the terminal. You can force the server to daemonize using the standard
shell backgrounding indicator, ``&``. However, for most use cases, we recommend
using the ``glance-control`` server daemon wrapper for daemonizing. See below
for more details on daemonization with ``glance-control``.

Using the ``glance-control`` program to start the server
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The second way to start up a Glance server is to use the ``glance-control``
program. ``glance-control`` is a wrapper script that allows the user to
start, stop, restart, and reload the other Glance server programs in
a fashion that is more conducive to automation and scripting.

Servers started via the ``glance-control`` program are always `daemonized`,
meaning that the server program process runs in the background.

To start a Glance server with ``glance-control``, simply call
``glance-control`` with a server and the word "start", followed by
any command-line options you wish to provide. Start the server with ``glance-control``
in the following way::

  $> sudo glance-control <SERVER> start [CONFPATH]

.. note::

  You must use the ``sudo`` program to run ``glance-control`` currently, as the
  pid files for the server programs are written to /var/run/glance/

Here is an example that shows how to start the ``glance-registry`` server
with the ``glance-control`` wrapper script. ::

  $> sudo glance-control registry start etc/glance.cnf.sample
  Starting glance-registry with /home/jpipes/repos/glance/trunk/etc/glance.cnf.sample
 
The same ``paste.deploy`` configuration files are used by ``glance-control``
to start the Glance server programs, and you can specify (as the example above
shows) a configuration file when starting the server.

.. note::

  To start all the Glance servers (currently the glance-api and glance-registry
  programs) at once, you can specify "all" for the <SERVER>

Stopping a server
-----------------

If you started a Glance server manually and did not use the ``&`` backgrounding
function, simply send a terminate signal to the server process by typing
``Ctrl-C``

If you started the Glance server using the ``glance-control`` program, you can
use the ``glance-control`` program to stop it. Simply do the following::

  $> sudo glance-control <SERVER> stop

as this example shows::

  jpipes@serialcoder:~$ sudo glance-control registry stop
  Stopping glance-registry  pid: 17602  signal: 15

Restarting a server
-------------------

You can restart a server with the ``glance-control`` program, as demonstrated
here::

  $> sudo ./bin/glance-control registry restart etc/glance.cnf.sample
  Stopping glance-registry  pid: 17611  signal: 15
  Starting glance-registry with /home/jpipes/repos/glance/use-paste-deploy/etc/glance.cnf.sample
