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

Glance has a number of options that you can use to configure the Glance API
server, the Glance Registry server, and the various storage backends that
Glance can use to store images.

Most configuration is done via configuration files, with the Glance API
server and Glance Registry server using separate configuration files.

When starting up a Glance server, you can specify the configuration file to
use (see `the documentation on controller Glance servers <controllingservers>`_).
If you do **not** specify a configuration file, Glance will look in the following
directories for a configuration file, in order:

* ``~/.glance``
* ``~/``
* ``/etc/glance``
* ``/etc``

The Glance API server configuration file should be named ``glance-api.conf``.
Similarly, the Glance Registry server configuration file should be named
``glance-registry.conf``. If you installed Glance via your operating system's
package management system, it is likely that you will have sample
configuration files installed in ``/etc/glance``.

In addition to this documentation page, you can check the
``etc/glance-api.conf`` and ``etc/glance-registry.conf`` sample configuration
files distributed with Glance for example configuration files for each server
application with detailed comments on what each options does.

Common Configuration Options in Glance
--------------------------------------

Glance has a few command-line options that are common to all Glance programs:

* ``--verbose``

Optional. Default: ``False``

Can be specified on the command line and in configuration files.

Turns on the INFO level in logging and prints more verbose command-line
interface printouts.

* ``--debug``

Optional. Default: ``False``

Can be specified on the command line and in configuration files.

Turns on the DEBUG level in logging.

* ``--config-file=PATH``

Optional. Default: ``None``

Specified on the command line only.

Takes a path to a configuration file to use when running the program. If this
CLI option is not specified, then we check to see if the first argument is a
file. If it is, then we try to use that as the configuration file. If there is
no file or there were no arguments, we search for a configuration file in the
following order:

* ``~/.glance``
* ``~/``
* ``/etc/glance``
* ``/etc``

The filename that is searched for depends on the server application name. So,
if you are starting up the API server, ``glance-api.conf`` is searched for,
otherwise ``glance-registry.conf``.

Configuring Logging in Glance
-----------------------------

There are a number of configuration options in Glance that control how Glance
servers log messages.

* ``--log-config=PATH``

Optional. Default: ``None``

Specified on the command line only.

Takes a path to a configuration file to use for configuring logging.

Logging Options Available Only in Configuration Files
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You will want to place the different logging options in the **[DEFAULT]** section
in your application configuration file. As an example, you might do the following
for the API server, in a configuration file called ``etc/glance-api.conf``::

  [DEFAULT]
  log_file = /var/log/glance/api.log

* ``log_file``

The filepath of the file to use for logging messages from Glance's servers. If
missing, the default is to output messages to ``stdout``, so if you are running
Glance servers in a daemon mode (using ``glance-control``) you should make
sure that the ``log_file`` option is set appropriately.

* ``log_dir``

The filepath of the directory to use for log files. If not specified (the default)
the ``log_file`` is used as an absolute filepath.

* ``log_date_format``

The format string for timestamps in the log output.

Defaults to ``%Y-%m-%d %H:%M:%S``. See the
`logging module <http://docs.python.org/library/logging.html>`_ documentation for
more information on setting this format string.

Configuring Glance Storage Backends
-----------------------------------

There are a number of configuration options in Glance that control how Glance
stores disk images. These configuration options are specified in the
``glance-api.conf`` config file in the section ``[DEFAULT]``.

* ``default_store=STORE``

Optional. Default: ``file``

Can only be specified in configuration files.

Sets the storage backend to use by default when storing images in Glance.
Available options for this option are (``file``, ``swift``, or ``s3``).

Configuring the Filesystem Storage Backend
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``filesystem_store_datadir=PATH``

Optional. Default: ``/var/lib/glance/images/``

Can only be specified in configuration files.

`This option is specific to the filesystem storage backend.`

Sets the path where the filesystem storage backend write disk images. Note that
the filesystem storage backend will attempt to create this directory if it does
not exist. Ensure that the user that ``glance-api`` runs under has write
permissions to this directory.

Configuring the Swift Storage Backend
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``swift_store_auth_address=URL``

Required when using the Swift storage backend.

Can only be specified in configuration files.

`This option is specific to the Swift storage backend.`

Sets the authentication URL supplied to Swift when making calls to its storage
system. For more information about the Swift authentication system, please
see the `Swift auth <http://swift.openstack.org/overview_auth.html>`_ 
documentation and the
`overview of Swift authentication <http://docs.openstack.org/openstack-object-storage/admin/content/ch02s02.html>`_.

* ``swift_store_user=USER``

Required when using the Swift storage backend.

Can only be specified in configuration files.

`This option is specific to the Swift storage backend.`

Sets the user to authenticate against the ``swift_store_auth_address`` with.

* ``swift_store_key=KEY``

Required when using the Swift storage backend.

Can only be specified in configuration files.

`This option is specific to the Swift storage backend.`

Sets the authentication key to authenticate against the
``swift_store_auth_address`` with for the user ``swift_store_user``.

* ``swift_store_container=CONTAINER``

Optional. Default: ``glance``

Can only be specified in configuration files.

`This option is specific to the Swift storage backend.`

Sets the name of the container to use for Glance images in Swift.

* ``swift_store_create_container_on_put``

Optional. Default: ``False``

Can only be specified in configuration files.

`This option is specific to the Swift storage backend.`

If true, Glance will attempt to create the container ``swift_store_container``
if it does not exist.

* ``swift_store_large_object_size=SIZE_IN_MB``

Optional. Default: ``5120``

Can only be specified in configuration files.

`This option is specific to the Swift storage backend.`

What size, in MB, should Glance start chunking image files
and do a large object manifest in Swift? By default, this is
the maximum object size in Swift, which is 5GB

* ``swift_store_large_object_chunk_size=SIZE_IN_MB``

Optional. Default: ``200``

Can only be specified in configuration files.

`This option is specific to the Swift storage backend.`

When doing a large object manifest, what size, in MB, should
Glance write chunks to Swift? This amount of data is written
to a temporary disk buffer during the process of chunking
the image file, and the default is 200MB

Configuring the S3 Storage Backend
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``s3_store_host=URL``

Required when using the S3 storage backend.

Can only be specified in configuration files.

`This option is specific to the S3 storage backend.`

Default: s3.amazonaws.com

Sets the main service URL supplied to S3 when making calls to its storage
system. For more information about the S3 authentication system, please
see the `S3 documentation <http://aws.amazon.com/documentation/s3/>`_ 

* ``s3_store_access_key=ACCESS_KEY``

Required when using the S3 storage backend.

Can only be specified in configuration files.

`This option is specific to the S3 storage backend.`

Sets the access key to authenticate against the ``s3_store_host`` with.

You should set this to your 20-character Amazon AWS access key.

* ``s3_store_secret_key=SECRET_KEY``

Required when using the S3 storage backend.

Can only be specified in configuration files.

`This option is specific to the S3 storage backend.`

Sets the secret key to authenticate against the
``s3_store_host`` with for the access key ``s3_store_access_key``.

You should set this to your 40-character Amazon AWS secret key.

* ``s3_store_bucket=BUCKET``

Required when using the S3 storage backend.

Can only be specified in configuration files.

`This option is specific to the S3 storage backend.`

Sets the name of the bucket to use for Glance images in S3.

Note that the namespace for S3 buckets is **global**, and
therefore you must use a name for the bucket that is unique. It
is recommended that you use a combination of your AWS access key,
**lowercased** with "glance".

For instance if your Amazon AWS access key is:

``ABCDEFGHIJKLMNOPQRST``

then make your bucket value be:

``abcdefghijklmnopqrstglance``

* ``s3_store_create_bucket_on_put``

Optional. Default: ``False``

Can only be specified in configuration files.

`This option is specific to the S3 storage backend.`

If true, Glance will attempt to create the bucket ``s3_store_bucket``
if it does not exist.

Configuring the Glance Registry
-------------------------------

Glance ships with a default, reference implementation registry server. There
are a number of configuration options in Glance that control how this registry
server operates. These configuration options are specified in the
``glance-registry.conf`` config file in the section ``[DEFAULT]``.

* ``sql_connection=CONNECTION_STRING`` (``--sql-connection`` when specified
  on command line)

Optional. Default: ``None``

Can be specified in configuration files. Can also be specified on the
command-line for the ``glance-manage`` program.

Sets the SQLAlchemy connection string to use when connecting to the registry
database. Please see the documentation for
`SQLAlchemy connection strings <http://www.sqlalchemy.org/docs/05/reference/sqlalchemy/connections.html>`_
online.

* ``sql_timeout=SECONDS``
  on command line)

Optional. Default: ``3600``

Can only be specified in configuration files.

Sets the number of seconds after which SQLAlchemy should reconnect to the
datastore if no activity has been made on the connection.

Configuring Notifications
-------------------------

Glance can optionally generate notifications to be logged or sent to
a RabbitMQ queue. The configuration options are specified in the
``glance-api.conf`` config file in the section ``[DEFAULT]``.

* ``notifier_strategy``

Optional. Default: ``noop``

Sets the strategy used for notifications. Options are ``logging``,
``rabbit`` and ``noop``.
For more information :doc:`Glance notifications <notifications>`

* ``rabbit_host``

Optional. Default: ``localhost``

Host to connect to when using ``rabbit`` strategy.

* ``rabbit_port``

Optional. Default: ``5672``

Port to connect to when using ``rabbit`` strategy.

* ``rabbit_use_ssl``

Optional. Default: ``false``

Boolean to use SSL for connecting when using ``rabbit`` strategy.

* ``rabbit_userid``

Optional. Default: ``guest``

Userid to use for connection when using ``rabbit`` strategy.

* ``rabbit_password``

Optional. Default: ``guest``

Password to use for connection when using ``rabbit`` strategy.

* ``rabbit_virtual_host``

Optional. Default: ``/``

Virtual host to use for connection when using ``rabbit`` strategy.

* ``rabbit_notification_topic``

Optional. Default: ``glance_notifications``

Topic to use for connection when using ``rabbit`` strategy.
