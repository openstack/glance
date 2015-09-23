..
      Copyright 2011 OpenStack Foundation
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

Basic Configuration
===================

Glance has a number of options that you can use to configure the Glance API
server, the Glance Registry server, and the various storage backends that
Glance can use to store images.

Most configuration is done via configuration files, with the Glance API
server and Glance Registry server using separate configuration files.

When starting up a Glance server, you can specify the configuration file to
use (see :doc:`the documentation on controller Glance servers <controllingservers>`).
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

The PasteDeploy configuration (controlling the deployment of the WSGI
application for each component) may be found by default in
<component>-paste.ini alongside the main configuration file, <component>.conf.
For example, ``glance-api-paste.ini`` corresponds to ``glance-api.conf``.
This pathname for the paste config is configurable, as follows::

  [paste_deploy]
  config_file = /path/to/paste/config


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

Optional. Default: See below for default search order.

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

* ``--config-dir=DIR``

Optional. Default: ``None``

Specified on the command line only.

Takes a path to a configuration directory from which all \*.conf fragments
are loaded. This provides an alternative to multiple --config-file options
when it is inconvenient to explicitly enumerate all the config files, for
example when an unknown number of config fragments are being generated
by a deployment framework.

If --config-dir is set, then --config-file is ignored.

An example usage would be:

  $ glance-api --config-dir=/etc/glance/glance-api.d

  $ ls /etc/glance/glance-api.d
   00-core.conf
   01-s3.conf
   02-swift.conf
   03-ssl.conf
   ... etc.

The numeric prefixes in the example above are only necessary if a specific
parse ordering is required (i.e. if an individual config option set in an
earlier fragment is overridden in a later fragment).

Note that ``glance-manage`` currently loads configuration from three files:

* ``glance-registry.conf``
* ``glance-api.conf``
* and the newly created ``glance-manage.conf``

By default ``glance-manage.conf`` only specifies a custom logging file but
other configuration options for ``glance-manage`` should be migrated in there.
**Warning**: Options set in ``glance-manage.conf`` will override options of
the same section and name set in the other two. Similarly, options in
``glance-api.conf`` will override options set in ``glance-registry.conf``.
This tool is planning to stop loading ``glance-registry.conf`` and
``glance-api.conf`` in a future cycle.

Configuring Server Startup Options
----------------------------------

You can put the following options in the ``glance-api.conf`` and
``glance-registry.conf`` files, under the ``[DEFAULT]`` section. They enable
startup and binding behaviour for the API and registry servers, respectively.

* ``bind_host=ADDRESS``

The address of the host to bind to.

Optional. Default: ``0.0.0.0``

* ``bind_port=PORT``

The port the server should bind to.

Optional. Default: ``9191`` for the registry server, ``9292`` for the API server

* ``backlog=REQUESTS``

Number of backlog requests to configure the socket with.

Optional. Default: ``4096``

* ``tcp_keepidle=SECONDS``

Sets the value of TCP_KEEPIDLE in seconds for each server socket.
Not supported on OS X.

Optional. Default: ``600``

* ``client_socket_timeout=SECONDS``

Timeout for client connections' socket operations.  If an incoming
connection is idle for this period it will be closed.  A value of `0`
means wait forever.

Optional. Default: ``900``


* ``workers=PROCESSES``

Number of Glance API or Registry worker processes to start. Each worker
process will listen on the same port. Increasing this value may increase
performance (especially if using SSL with compression enabled). Typically
it is recommended to have one worker process per CPU. The value `0`
will prevent any new processes from being created.

Optional. Default: The number of CPUs available will be used by default.

* ``max_request_id_length=LENGTH``

Limits the maximum size of the x-openstack-request-id header which is
logged. Affects only if context middleware is configured in pipeline.

Optional. Default: ``64`` (Limited by max_header_line default: 16384)

Configuring SSL Support
~~~~~~~~~~~~~~~~~~~~~~~~~

* ``cert_file=PATH``

Path to the certificate file the server should use when binding to an
SSL-wrapped socket.

Optional. Default: not enabled.

* ``key_file=PATH``

Path to the private key file the server should use when binding to an
SSL-wrapped socket.

Optional. Default: not enabled.

* ``ca_file=PATH``

Path to the CA certificate file the server should use to validate client
certificates provided during an SSL handshake. This is ignored if
``cert_file`` and ''key_file`` are not set.

Optional. Default: not enabled.

Configuring Registry Access
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

There are a number of configuration options in Glance that control how
the API server accesses the registry server.

* ``registry_client_protocol=PROTOCOL``

If you run a secure Registry server, you need to set this value to ``https``
and also set ``registry_client_key_file`` and optionally
``registry_client_cert_file``.

Optional. Default: http

* ``registry_client_key_file=PATH``

The path to the key file to use in SSL connections to the
registry server, if any. Alternately, you may set the
``GLANCE_CLIENT_KEY_FILE`` environ variable to a filepath of the key file

Optional. Default: Not set.

* ``registry_client_cert_file=PATH``

Optional. Default: Not set.

The path to the cert file to use in SSL connections to the
registry server, if any. Alternately, you may set the
``GLANCE_CLIENT_CERT_FILE`` environ variable to a filepath of the cert file

* ``registry_client_ca_file=PATH``

Optional. Default: Not set.

The path to a Certifying Authority's cert file to use in SSL connections to the
registry server, if any. Alternately, you may set the
``GLANCE_CLIENT_CA_FILE`` environ variable to a filepath of the CA cert file

* ``registry_client_insecure=False``

Optional. Default: False.

When using SSL in connections to the registry server, do not require
validation via a certifying authority. This is the registry's equivalent of
specifying --insecure on the command line using glanceclient for the API

* ``registry_client_timeout=SECONDS``

Optional. Default: ``600``.

The period of time, in seconds, that the API server will wait for a registry
request to complete. A value of '0' implies no timeout.

* ``use_user_token=True``

Optional. Default: True

Pass the user token through for API requests to the registry.

If 'use_user_token' is not in effect then admin credentials can be
specified (see below). If admin credentials are specified then they are
used to generate a token; this token rather than the original user's
token is used for requests to the registry.

To prevent failures with token expiration during big files upload,
it is recommended to set this parameter to False.

* ``admin_user=USER``
If 'use_user_token' is not in effect then admin credentials can be
specified. Use this parameter to specify the username.

Optional. Default: None

* ``admin_password=PASSWORD``
If 'use_user_token' is not in effect then admin credentials can be
specified. Use this parameter to specify the password.

Optional. Default: None

* ``admin_tenant_name=TENANTNAME``
If 'use_user_token' is not in effect then admin credentials can be
specified. Use this parameter to specify the tenant name.

Optional. Default: None

* ``auth_url=URL``
If 'use_user_token' is not in effect then admin credentials can be
specified. Use this parameter to specify the Keystone endpoint.

Optional. Default: None

* ``auth_strategy=STRATEGY``
If 'use_user_token' is not in effect then admin credentials can be
specified. Use this parameter to specify the auth strategy.

Optional. Default: keystone

* ``auth_region=REGION``
If 'use_user_token' is not in effect then admin credentials can be
specified. Use this parameter to specify the region.

Optional. Default: None


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

* ``log_use_syslog``

Use syslog logging functionality.

Defaults to False.

Configuring Glance Storage Backends
-----------------------------------

There are a number of configuration options in Glance that control how Glance
stores disk images. These configuration options are specified in the
``glance-api.conf`` config file in the section ``[glance_store]``.

* ``default_store=STORE``

Optional. Default: ``file``

Can only be specified in configuration files.

Sets the storage backend to use by default when storing images in Glance.
Available options for this option are (``file``, ``swift``, ``s3``, ``rbd``, ``sheepdog``,
``cinder`` or ``vsphere``). In order to select a default store it must also
be listed in the ``stores`` list described below.

* ``stores=STORES``

Optional. Default: ``glance.store.filesystem.Store, glance.store.http.Store``

A comma separated list of enabled glance stores. Options are specified
in the format of glance.store.OPTION.Store.  Some available options for this
option are (``filesystem``, ``http``, ``rbd``, ``s3``, ``swift``, ``sheepdog``,
``cinder``, ``gridfs``, ``vmware_datastore``)

Configuring Glance Image Size Limit
-----------------------------------

The following configuration option is specified in the
``glance-api.conf`` config file in the section ``[DEFAULT]``.

* ``image_size_cap=SIZE``

Optional. Default: ``1099511627776`` (1 TB)

Maximum image size, in bytes, which can be uploaded through the Glance API server.

**IMPORTANT NOTE**: this value should only be increased after careful consideration
and must be set to a value under 8 EB (9223372036854775808).

Configuring Glance User Storage Quota
-------------------------------------

The following configuration option is specified in the
``glance-api.conf`` config file in the section ``[DEFAULT]``.

* ``user_storage_quota``

Optional. Default: 0 (Unlimited).

This value specifies the maximum amount of storage that each user can use
across all storage systems. Optionally unit can be specified for the value.
Values are accepted in B, KB, MB, GB or TB which are for Bytes, KiloBytes,
MegaBytes, GigaBytes and TeraBytes respectively. Default unit is Bytes.

Example values would be,
    user_storage_quota=20GB

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

* ``filesystem_store_file_perm=PERM_MODE``

Optional. Default: ``0``

Can only be specified in configuration files.

`This option is specific to the filesystem storage backend.`

The required permission value, in octal representation, for the created image file.
You can use this value to specify the user of the consuming service (such as Nova) as
the only member of the group that owns the created files. To keep the default value,
assign a permission value that is less than or equal to 0.  Note that the file owner
must maintain read permission; if this value removes that permission an error message
will be logged and the BadStoreConfiguration exception will be raised.  If the Glance
service has insufficient privileges to change file access permissions, a file will still
be saved, but a warning message will appear in the Glance log.

Configuring the Filesystem Storage Backend with multiple stores
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``filesystem_store_datadirs=PATH:PRIORITY``

Optional. Default: ``/var/lib/glance/images/:1``

Example::

  filesystem_store_datadirs = /var/glance/store
  filesystem_store_datadirs = /var/glance/store1:100
  filesystem_store_datadirs = /var/glance/store2:200

This option can only be specified in configuration file and is specific
to the filesystem storage backend only.

filesystem_store_datadirs option allows administrators to configure
multiple store directories to save glance image in filesystem storage backend.
Each directory can be coupled with its priority.

**NOTE**:

* This option can be specified multiple times to specify multiple stores.
* Either filesystem_store_datadir or filesystem_store_datadirs option must be
  specified in glance-api.conf
* Store with priority 200 has precedence over store with priority 100.
* If no priority is specified, default priority '0' is associated with it.
* If two filesystem stores have same priority store with maximum free space
  will be chosen to store the image.
* If same store is specified multiple times then BadStoreConfiguration
  exception will be raised.

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

**IMPORTANT NOTE**: Swift authentication addresses use HTTPS by default. This
means that if you are running Swift with authentication over HTTP, you need
to set your ``swift_store_auth_address`` to the full URL, including the ``http://``.

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
Glance write chunks to Swift?  The default is 200MB.

* ``swift_store_multi_tenant=False``

Optional. Default: ``False``

Can only be specified in configuration files.

`This option is specific to the Swift storage backend.`

If set to True enables multi-tenant storage mode which causes Glance images
to be stored in tenant specific Swift accounts. When set to False Glance
stores all images in a single Swift account.

* ``swift_store_multiple_containers_seed``

Optional. Default: ``0``

Can only be specified in configuration files.

`This option is specific to the Swift storage backend.`

When set to 0, a single-tenant store will only use one container to store all
images. When set to an integer value between 1 and 32, a single-tenant store
will use multiple containers to store images, and this value will determine
how many characters from an image UUID are checked when determining what
container to place the image in. The maximum number of containers that will be
created is approximately equal to 16^N. This setting is used only when
swift_store_multi_tentant is disabled.

Example: if this config option is set to 3 and
swift_store_container = 'glance', then an image with UUID
'fdae39a1-bac5-4238-aba4-69bcc726e848' would be placed in the container
'glance_fda'. All dashes in the UUID are included when creating the container
name but do not count toward the character limit, so in this example with N=10
the container name would be 'glance_fdae39a1-ba'.

When choosing the value for swift_store_multiple_containers_seed, deployers
should discuss a suitable value with their swift operations team. The authors
of this option recommend that large scale deployments use a value of '2',
which will create a maximum of ~256 containers. Choosing a higher number than
this, even in extremely large scale deployments, may not have any positive
impact on performance and could lead to a large number of empty, unused
containers. The largest of deployments could notice an increase in performance
if swift rate limits are throttling on single container. Note: If dynamic
container creation is turned off, any value for this configuration option
higher than '1' may be unreasonable as the deployer would have to manually
create each container.

* ``swift_store_admin_tenants``

Can only be specified in configuration files.

`This option is specific to the Swift storage backend.`

Optional. Default: Not set.

A list of swift ACL strings that will be applied as both read and
write ACLs to the containers created by Glance in multi-tenant
mode. This grants the specified tenants/users read and write access
to all newly created image objects. The standard swift ACL string
formats are allowed, including:

<tenant_id>:<username>
<tenant_name>:<username>
\*:<username>

Multiple ACLs can be combined using a comma separated list, for
example: swift_store_admin_tenants = service:glance,*:admin

* ``swift_store_auth_version``

Can only be specified in configuration files.

`This option is specific to the Swift storage backend.`

Optional. Default: ``2``

A string indicating which version of Swift OpenStack authentication
to use. See the project
`python-swiftclient <http://docs.openstack.org/developer/python-swiftclient/>`_
for more details.

* ``swift_store_service_type``

Can only be specified in configuration files.

`This option is specific to the Swift storage backend.`

Optional. Default: ``object-store``

A string giving the service type of the swift service to use. This
setting is only used if swift_store_auth_version is ``2``.

* ``swift_store_region``

Can only be specified in configuration files.

`This option is specific to the Swift storage backend.`

Optional. Default: Not set.

A string giving the region of the swift service endpoint to use. This
setting is only used if swift_store_auth_version is ``2``. This
setting is especially useful for disambiguation if multiple swift
services might appear in a service catalog during authentication.

* ``swift_store_endpoint_type``

Can only be specified in configuration files.

`This option is specific to the Swift storage backend.`

Optional. Default: ``publicURL``

A string giving the endpoint type of the swift service endpoint to
use. This setting is only used if swift_store_auth_version is ``2``.

* ``swift_store_ssl_compression``

Can only be specified in configuration files.

`This option is specific to the Swift storage backend.`

Optional. Default: True.

If set to False, disables SSL layer compression of https swift
requests. Setting to 'False' may improve performance for images which
are already in a compressed format, e.g. qcow2. If set to True then
compression will be enabled (provided it is supported by the swift
proxy).

* ``swift_store_cacert``

Can only be specified in configuration files.

Optional. Default: ``None``

A string giving the path to a CA certificate bundle that will allow Glance's
services to perform SSL verification when communicating with Swift.

* ``swift_store_retry_get_count``

The number of times a Swift download will be retried before the request
fails.
Optional. Default: ``0``

Configuring Multiple Swift Accounts/Stores
------------------------------------------

In order to not store Swift account credentials in the database, and to
have support for multiple accounts (or multiple Swift backing stores), a
reference is stored in the database and the corresponding configuration
(credentials/ parameters) details are stored in the configuration file.
Optional.  Default: not enabled.

The location for this file is specified using the ``swift_store_config_file`` config file
in the section ``[DEFAULT]``. **If an incorrect value is specified, Glance API Swift store
service will not be configured.**
* ``swift_store_config_file=PATH``

`This option is specific to the Swift storage backend.`

* ``default_swift_reference=DEFAULT_REFERENCE``

Required when multiple Swift accounts/backing stores are configured.

Can only be specified in configuration files.

`This option is specific to the Swift storage backend.`

It is the default swift reference that is used to add any new images.
* ``swift_store_auth_insecure``

If True, bypass SSL certificate verification for Swift.

Can only be specified in configuration files.

`This option is specific to the Swift storage backend.`

Optional. Default: ``False``

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

Note that the namespace for S3 buckets is **global**,
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

* ``s3_store_object_buffer_dir=PATH``

Optional. Default: ``the platform's default temporary directory``

Can only be specified in configuration files.

`This option is specific to the S3 storage backend.`

When sending images to S3, what directory should be
used to buffer the chunks? By default the platform's
temporary directory will be used.

* ``s3_store_large_object_size=SIZE_IN_MB``

Optional. Default: ``100``

Can only be specified in configuration files.

`This option is specific to the S3 storage backend.`

Size, in ``MB``, should S3 start chunking image files
and do a multipart upload in S3.

* ``s3_store_large_object_chunk_size=SIZE_IN_MB``

Optional. Default: ``10``

Can only be specified in configuration files.

`This option is specific to the S3 storage backend.`

Multipart upload part size, in ``MB``, should S3 use
when uploading parts. The size must be greater than or
equal to 5MB. The default is 10MB.

* ``s3_store_thread_pools=NUM``

Optional. Default: ``10``

Can only be specified in configuration files.

`This option is specific to the S3 storage backend.`

The number of thread pools to perform a multipart upload
in S3. The default is 10.

Configuring the RBD Storage Backend
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Note**: the RBD storage backend requires the python bindings for
librados and librbd. These are in the python-ceph package on
Debian-based distributions.

* ``rbd_store_pool=POOL``

Optional. Default: ``rbd``

Can only be specified in configuration files.

`This option is specific to the RBD storage backend.`

Sets the RADOS pool in which images are stored.

* ``rbd_store_chunk_size=CHUNK_SIZE_MB``

Optional. Default: ``4``

Can only be specified in configuration files.

`This option is specific to the RBD storage backend.`

Images will be chunked into objects of this size (in megabytes).
For best performance, this should be a power of two.

* ``rados_connect_timeout``

Optional. Default: ``0``

Can only be specified in configuration files.

`This option is specific to the RBD storage backend.`

Prevents glance-api hangups during the connection to RBD. Sets the time
to wait (in seconds) for glance-api before closing the connection.
Setting ``rados_connect_timeout<=0`` means no timeout.

* ``rbd_store_ceph_conf=PATH``

Optional. Default: ``/etc/ceph/ceph.conf``, ``~/.ceph/config``, and ``./ceph.conf``

Can only be specified in configuration files.

`This option is specific to the RBD storage backend.`

Sets the Ceph configuration file to use.

* ``rbd_store_user=NAME``

Optional. Default: ``admin``

Can only be specified in configuration files.

`This option is specific to the RBD storage backend.`

Sets the RADOS user to authenticate as. This is only needed
when `RADOS authentication <http://ceph.newdream.net/wiki/Cephx>`_
is `enabled. <http://ceph.newdream.net/wiki/Cluster_configuration#Cephx_auth>`_

A keyring must be set for this user in the Ceph
configuration file, e.g. with a user ``glance``::

  [client.glance]
  keyring=/etc/glance/rbd.keyring

To set up a user named ``glance`` with minimal permissions, using a pool called
``images``, run::

  rados mkpool images
  ceph-authtool --create-keyring /etc/glance/rbd.keyring
  ceph-authtool --gen-key --name client.glance --cap mon 'allow r' --cap osd 'allow rwx pool=images' /etc/glance/rbd.keyring
  ceph auth add client.glance -i /etc/glance/rbd.keyring

Configuring the Sheepdog Storage Backend
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``sheepdog_store_address=ADDR``

Optional. Default: ``localhost``

Can only be specified in configuration files.

`This option is specific to the Sheepdog storage backend.`

Sets the IP address of the sheep daemon

* ``sheepdog_store_port=PORT``

Optional. Default: ``7000``

Can only be specified in configuration files.

`This option is specific to the Sheepdog storage backend.`

Sets the IP port of the sheep daemon

* ``sheepdog_store_chunk_size=SIZE_IN_MB``

Optional. Default: ``64``

Can only be specified in configuration files.

`This option is specific to the Sheepdog storage backend.`

Images will be chunked into objects of this size (in megabytes).
For best performance, this should be a power of two.

Configuring the Cinder Storage Backend
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Note**: Currently Cinder store is a partial implementation.
After Cinder expose 'brick' library, and 'Readonly-volume-attaching',
'volume-multiple-attaching' enhancement ready, the store will support
'Upload' and 'Download' interface finally.

* ``cinder_catalog_info=<service_type>:<service_name>:<endpoint_type>``

Optional. Default: ``volume:cinder:publicURL``

Can only be specified in configuration files.

`This option is specific to the Cinder storage backend.`

Sets the info to match when looking for cinder in the service catalog.
Format is : separated values of the form: <service_type>:<service_name>:<endpoint_type>

* ``cinder_endpoint_template=http://ADDR:PORT/VERSION/%(project_id)s``

Optional. Default: ``None``

Can only be specified in configuration files.

Override service catalog lookup with template for cinder endpoint.
e.g. http://localhost:8776/v1/%(project_id)s

* ``os_region_name=REGION_NAME``

Optional. Default: ``None``

Can only be specified in configuration files.

Region name of this node.

* ``cinder_ca_certificates_file=CA_FILE_PATH``

Optional. Default: ``None``

Can only be specified in configuration files.

Location of ca certicates file to use for cinder client requests.

* ``cinder_http_retries=TIMES``

Optional. Default: ``3``

Can only be specified in configuration files.

Number of cinderclient retries on failed http calls.

* ``cinder_api_insecure=ON_OFF``

Optional. Default: ``False``

Can only be specified in configuration files.

Allow to perform insecure SSL requests to cinder.

Configuring the VMware Storage Backend
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``vmware_server_host=ADDRESS``

Required when using the VMware storage backend.

Can only be specified in configuration files.

Sets the address of the ESX/ESXi or vCenter Server target system.
The address can contain an IP (``127.0.0.1``), an IP and port
(``127.0.0.1:443``), a DNS name (``www.my-domain.com``) or DNS and port.

`This option is specific to the VMware storage backend.`

* ``vmware_server_username=USERNAME``

Required when using the VMware storage backend.

Can only be specified in configuration files.

Username for authenticating with VMware ESX/ESXi or vCenter Server.

* ``vmware_server_password=PASSWORD``

Required when using the VMware storage backend.

Can only be specified in configuration files.

Password for authenticating with VMware ESX/ESXi or vCenter Server.

* ``vmware_datacenter_path=DC_PATH``

Optional. Default: ``ha-datacenter``

Can only be specified in configuration files.

Inventory path to a datacenter. If the ``vmware_server_host`` specified
is an ESX/ESXi, the ``vmware_datacenter_path`` is optional. If specified,
it should be ``ha-datacenter``.

* ``vmware_datastore_name=DS_NAME``

Required when using the VMware storage backend.

Can only be specified in configuration files.

Datastore name associated with the ``vmware_datacenter_path``

* ``vmware_datastores``

Optional. Default: Not set.

This option can only be specified in configuration file and is specific
to the VMware storage backend.

vmware_datastores allows administrators to configure multiple datastores to
save glance image in the VMware store backend. The required format for the
option is: <datacenter_path>:<datastore_name>:<optional_weight>.

where datacenter_path is the inventory path to the datacenter where the
datastore is located. An optional weight can be given to specify the priority.

Example::

  vmware_datastores = datacenter1:datastore1
  vmware_datastores = dc_folder/datacenter2:datastore2:100
  vmware_datastores = datacenter1:datastore3:200

**NOTE**:

  - This option can be specified multiple times to specify multiple datastores.
  - Either vmware_datastore_name or vmware_datastores option must be specified
    in glance-api.conf
  - Datastore with weight 200 has precedence over datastore with weight 100.
  - If no weight is specified, default weight '0' is associated with it.
  - If two datastores have same weight, the datastore with maximum free space
    will be chosen to store the image.
  - If the datacenter path or datastore name contains a colon (:) symbol, it
    must be escaped with a backslash.

* ``vmware_api_retry_count=TIMES``

Optional. Default: ``10``

Can only be specified in configuration files.

The number of times VMware ESX/VC server API must be
retried upon connection related issues.

* ``vmware_task_poll_interval=SECONDS``

Optional. Default: ``5``

Can only be specified in configuration files.

The interval used for polling remote tasks invoked on VMware ESX/VC server.

* ``vmware_store_image_dir``

Optional. Default: ``/openstack_glance``

Can only be specified in configuration files.

The path to access the folder where the images will be stored in the datastore.

* ``vmware_api_insecure=ON_OFF``

Optional. Default: ``False``

Can only be specified in configuration files.

Allow to perform insecure SSL requests to ESX/VC server.

Configuring the Storage Endpoint
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``swift_store_endpoint=URL``

Optional. Default: ``None``

Can only be specified in configuration files.

Overrides the storage URL returned by auth. The URL should include the
path up to and excluding the container. The location of an object is
obtained by appending the container and object to the configured URL.
e.g. ``https://www.my-domain.com/v1/path_up_to_container``

Configuring the Image Cache
---------------------------

Glance API servers can be configured to have a local image cache. Caching of
image files is transparent and happens using a piece of middleware that can
optionally be placed in the server application pipeline.

This pipeline is configured in the PasteDeploy configuration file,
<component>-paste.ini. You should not generally have to edit this file
directly, as it ships with ready-made pipelines for all common deployment
flavors.

Enabling the Image Cache Middleware
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To enable the image cache middleware, the cache middleware must occur in
the application pipeline **after** the appropriate context middleware.

The cache middleware should be in your ``glance-api-paste.ini`` in a section
titled ``[filter:cache]``. It should look like this::

  [filter:cache]
  paste.filter_factory = glance.api.middleware.cache:CacheFilter.factory

A ready-made application pipeline including this filter is defined in
the ``glance-api-paste.ini`` file, looking like so::

  [pipeline:glance-api-caching]
  pipeline = versionnegotiation context cache apiv1app

To enable the above application pipeline, in your main ``glance-api.conf``
configuration file, select the appropriate deployment flavor like so::

  [paste_deploy]
  flavor = caching

Enabling the Image Cache Management Middleware
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

There is an optional ``cachemanage`` middleware that allows you to
directly interact with cache images. Use this flavor in place of the
``cache`` flavor in your api config file.

  [paste_deploy]
  flavor = cachemanage

Configuration Options Affecting the Image Cache
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. note::

  These configuration options must be set in both the glance-cache
  and glance-api configuration files.


One main configuration file option affects the image cache.

 * ``image_cache_dir=PATH``

Required when image cache middleware is enabled.

Default: ``/var/lib/glance/image-cache``

This is the base directory the image cache can write files to.
Make sure the directory is writeable by the user running the
``glance-api`` server

 * ``image_cache_driver=DRIVER``

Optional. Choice of ``sqlite`` or ``xattr``

Default: ``sqlite``

The default ``sqlite`` cache driver has no special dependencies, other
than the ``python-sqlite3`` library, which is installed on virtually
all operating systems with modern versions of Python. It stores
information about the cached files in a SQLite database.

The ``xattr`` cache driver required the ``python-xattr>=0.6.0`` library
and requires that the filesystem containing ``image_cache_dir`` have
access times tracked for all files (in other words, the noatime option
CANNOT be set for that filesystem). In addition, ``user_xattr`` must be
set on the filesystem's description line in fstab. Because of these
requirements, the ``xattr`` cache driver is not available on Windows.

 * ``image_cache_sqlite_db=DB_FILE``

Optional.

Default: ``cache.db``

When using the ``sqlite`` cache driver, you can set the name of the database
that will be used to store the cached images information. The database
is always contained in the ``image_cache_dir``.

 * ``image_cache_max_size=SIZE``

Optional.

Default: ``10737418240`` (10 GB)

Size, in bytes, that the image cache should be constrained to. Images files
are cached automatically in the local image cache, even if the writing of that
image file would put the total cache size over this size. The
``glance-cache-pruner`` executable is what prunes the image cache to be equal
to or less than this value. The ``glance-cache-pruner`` executable is designed
to be run via cron on a regular basis. See more about this executable in
:doc:`Controlling the Growth of the Image Cache <cache>`


Configuring the Glance Registry
-------------------------------

There are a number of configuration options in Glance that control how
this registry server operates. These configuration options are specified in the
``glance-registry.conf`` config file in the section ``[DEFAULT]``.

**IMPORTANT NOTE**: The glance-registry service is only used in conjunction
with the glance-api service when clients are using the v1 REST API. See
`Configuring Glance APIs`_ for more info.

* ``sql_connection=CONNECTION_STRING`` (``--sql-connection`` when specified
  on command line)

Optional. Default: ``None``

Can be specified in configuration files. Can also be specified on the
command-line for the ``glance-manage`` program.

Sets the SQLAlchemy connection string to use when connecting to the registry
database. Please see the documentation for
`SQLAlchemy connection strings <http://www.sqlalchemy.org/docs/05/reference/sqlalchemy/connections.html>`_
online. You must urlencode any special characters in CONNECTION_STRING.

* ``sql_timeout=SECONDS``
  on command line)

Optional. Default: ``3600``

Can only be specified in configuration files.

Sets the number of seconds after which SQLAlchemy should reconnect to the
datastore if no activity has been made on the connection.

* ``enable_v1_registry=<True|False>``

Optional. Default: ``True``

* ``enable_v2_registry=<True|False>``

Optional. Default: ``True``

Defines which version(s) of the Registry API will be enabled.
If the Glance API server parameter ``enable_v1_api`` has been set to ``True`` the
``enable_v1_registry`` has to be ``True`` as well.
If the Glance API server parameter ``enable_v2_api`` or ``enable_v3_api`` has been
set to ``True`` and the parameter ``data_api`` has been set to
``glance.db.registry.api`` the ``enable_v2_registry`` has to be set to ``True``


Configuring Notifications
-------------------------

Glance can optionally generate notifications to be logged or sent to
a message queue. The configuration options are specified in the
``glance-api.conf`` config file in the section ``[DEFAULT]``.

* ``notification_driver``

Optional. Default: ``noop``

Sets the notification driver used by oslo.messaging. Options include
``messaging``, ``messagingv2``, ``log`` and ``routing``.

For more information see :doc:`Glance notifications <notifications>` and
`oslo.messaging <http://docs.openstack.org/developer/oslo.messaging/>`_.

* ``disabled_notifications``

Optional. Default: ``[]``

List of disabled notifications. A notification can be given either as a
notification type to disable a single event, or as a notification group prefix
to disable all events within a group.

Example: if this config option is set to ["image.create", "metadef_namespace"],
then "image.create" notification will not be sent after image is created and
none of the notifications for metadefinition namespaces will be sent.

Configuring Glance Property Protections
---------------------------------------

Access to image meta properties may be configured using a
:doc:`Property Protections Configuration file <property-protections>`.  The
location for this file can be specified in the ``glance-api.conf`` config file
in the section ``[DEFAULT]``. **If an incorrect value is specified, glance api
service will not start.**

* ``property_protection_file=PATH``

Optional. Default: not enabled.

If property_protection_file is set, the file may use either roles or policies
to specify property protections.

* ``property_protection_rule_format=<roles|policies>``

Optional. Default: ``roles``.

Configuring Glance APIs
-----------------------

The glance-api service implements versions 1, 2 and 3 of
the OpenStack Images API. Disable any version of
the Images API using the following options:

* ``enable_v1_api=<True|False>``

Optional. Default: ``True``

* ``enable_v2_api=<True|False>``

Optional. Default: ``True``

* ``enable_v3_api=<True|False>``

Optional. Default: ``False``

**IMPORTANT NOTE**: To use v2 registry in v2 or v3 API, you must set
``data_api`` to glance.db.registry.api in glance-api.conf.

Configuring Glance Tasks
------------------------

Glance Tasks are implemented only for version 2 of the OpenStack Images API.

The config value ``task_time_to_live`` is used to determine how long a task
would be visible to the user after transitioning to either the ``success`` or
the ``failure`` state.

* ``task_time_to_live=<Time_in_hours>``

Optional. Default: ``48``

The config value ``task_executor`` is used to determine which executor
should be used by the Glance service to process the task. The currently
available implementation is: ``taskflow``.

* ``task_executor=<executor_type>``

Optional. Default: ``taskflow``

The ``taskflow`` engine has its own set of configuration options,
under the ``taskflow_executor`` section, that can be tuned to improve
the task execution process. Among the available options, you may find
``engine_mode`` and ``max_workers``. The former allows for selecting
an execution model and the available options are ``serial``,
``parallel`` and ``worker-based``. The ``max_workers`` option,
instead, allows for controlling the number of workers that will be
instantiated per executor instance.

The default value for the ``engine_mode`` is ``parallel``, whereas
the default number of ``max_workers`` is ``10``.

Configuring Glance performance profiling
----------------------------------------

Glance supports using osprofiler to trace the performance of each key internal
handling, including RESTful API calling, DB operation and etc.

``Please be aware that Glance performance profiling is currently a work in
progress feature.`` Although, some trace points is available, e.g. API
execution profiling at wsgi main entry and SQL execution profiling at DB
module, the more fine-grained trace point is being worked on.

The config value ``enabled`` is used to determine whether fully enable
profiling feature for glance-api and glance-registry service.

* ``enabled=<True|False>``

Optional. Default: ``True``

The config value ``trace_sqlalchemy`` is used to determine whether fully enable
sqlalchemy engine based SQL execution profiling feature for glance-api and
glance-registry services.

* ``trace_sqlalchemy=<True|False>``

Optional. Default: ``True``

**IMPORTANT NOTE**: The HMAC key which is used for encrypting context data for
performance profiling is configured in paste config file of glance-api and
glance-registry service separately, by default they place at
/etc/glance/api-paste.ini and /etc/glance/registry-paste.ini files, in order
to make profiling work as designed operator needs to make those values of HMAC
key be consistent for all services in your deployment. Without HMAC key the
profiling will not be triggered even profiling feature is enabled.

Configuring Glance public endpoint
----------------------------------

This setting allows an operator to configure the endpoint URL that will
appear in the Glance "versions" response (that is, the response to
``GET /``\  ).  This can be necessary when the Glance API service is run
behind a proxy because the default endpoint displayed in the versions
response is that of the host actually running the API service.  If
Glance is being run behind a load balancer, for example, direct access
to individual hosts running the Glance API may not be allowed, hence the
load balancer URL would be used for this value.

* ``public_endpoint=<None|URL>``

Optional. Default: ``None``

Configuring Glance digest algorithm
-----------------------------------

Digest algorithm that will be used for digital signature. The default
is sha256. Use the command::

  openssl list-message-digest-algorithms

to get the available algorithms supported by the version of OpenSSL on the
platform. Examples are "sha1", "sha256", "sha512", etc. If an invalid
digest algorithm is configured, all digital signature operations will fail and
return a ValueError exception with "No such digest method" error.

* ``digest_algorithm=<algorithm>``

Optional. Default: ``sha256``

Configuring http_keepalive option
---------------------------------

* ``http_keepalive=<True|False>``

If False, server will return the header "Connection: close", If True, server
will return "Connection: Keep-Alive" in its responses. In order to close the
client socket connection explicitly after the response is sent and read
successfully by the client, you simply have to set this option to False when
you create a wsgi server.

Configuring the Health Check
----------------------------

This setting allows an operator to configure the endpoint URL that will
provide information to load balancer if given API endpoint at the node should
be available or not. Both Glance API and Glance Registry servers can be
configured to expose a health check URL.

To enable the health check middleware, it must occur in the beginning of the
application pipeline.

The health check middleware should be placed in your
``glance-api-paste.ini`` / ``glance-registry-paste.ini`` in a section
titled ``[filter:healthcheck]``. It should look like this::

  [filter:healthcheck]
  paste.filter_factory = oslo_middleware:Healthcheck.factory
  backends = disable_by_file
  disable_by_file_path = /etc/glance/healthcheck_disable

A ready-made application pipeline including this filter is defined e.g. in
the ``glance-api-paste.ini`` file, looking like so::

  [pipeline:glance-api]
  pipeline = healthcheck versionnegotiation osprofiler unauthenticated-context rootapp

For more information see
`oslo.middleware <http://docs.openstack.org/developer/oslo.middleware/api.html#oslo_middleware.Healthcheck>`_.
