# Copyright 2011 OpenStack Foundation
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
import os

from oslo_config import cfg
from oslo_middleware import cors
from oslo_policy import opts
from oslo_policy import policy
from paste import deploy

from glance.i18n import _
from glance.version import version_info as version

paste_deploy_opts = [
    cfg.StrOpt('flavor',
               sample_default='keystone',
               help=_("""
Deployment flavor to use in the server application pipeline.

Provide a string value representing the appropriate deployment
flavor used in the server application pipeline. This is typically
the partial name of a pipeline in the paste configuration file with
the service name removed.

For example, if your paste section name in the paste configuration
file is [pipeline:glance-api-keystone], set ``flavor`` to
``keystone``.

Possible values:
    * String value representing a partial pipeline name.

Related Options:
    * config_file

""")),
    cfg.StrOpt('config_file',
               sample_default='glance-api-paste.ini',
               help=_("""
Name of the paste configuration file.

Provide a string value representing the name of the paste
configuration file to use for configuring pipelines for
server application deployments.

NOTES:
    * Provide the name or the path relative to the glance directory
      for the paste configuration file and not the absolute path.
    * The sample paste configuration file shipped with Glance need
      not be edited in most cases as it comes with ready-made
      pipelines for all common deployment flavors.

If no value is specified for this option, the ``paste.ini`` file
with the prefix of the corresponding Glance service's configuration
file name will be searched for in the known configuration
directories. (For example, if this option is missing from or has no
value set in ``glance-api.conf``, the service will look for a file
named ``glance-api-paste.ini``.) If the paste configuration file is
not found, the service will not start.

Possible values:
    * A string value representing the name of the paste configuration
      file.

Related Options:
    * flavor

""")),
]
image_format_opts = [
    cfg.ListOpt('container_formats',
                default=['ami', 'ari', 'aki', 'bare', 'ovf', 'ova', 'docker',
                         'compressed'],
                help=_("Supported values for the 'container_format' "
                       "image attribute"),
                deprecated_opts=[cfg.DeprecatedOpt('container_formats',
                                                   group='DEFAULT')]),
    cfg.ListOpt('disk_formats',
                default=['ami', 'ari', 'aki', 'vhd', 'vhdx', 'vmdk', 'raw',
                         'qcow2', 'vdi', 'iso', 'ploop'],
                help=_("Supported values for the 'disk_format' "
                       "image attribute"),
                deprecated_opts=[cfg.DeprecatedOpt('disk_formats',
                                                   group='DEFAULT')]),
    cfg.ListOpt('vmdk_allowed_types',
                default=['streamOptimized', 'monolithicSparse'],
                help=_("A list of strings describing allowed VMDK "
                       "'create-type' subformats that will be allowed. "
                       "This is recommended to only include "
                       "single-file-with-sparse-header variants to avoid "
                       "potential host file exposure due to processing named "
                       "extents. If this list is empty, then no VDMK image "
                       "types allowed. Note that this is currently only "
                       "checked during image conversion (if enabled), and "
                       "limits the types of VMDK images we will convert "
                       "from.")),
]
task_opts = [
    cfg.IntOpt('task_time_to_live',
               default=48,
               help=_("Time in hours for which a task lives after, either "
                      "succeeding or failing"),
               deprecated_opts=[cfg.DeprecatedOpt('task_time_to_live',
                                                  group='DEFAULT')]),
    cfg.StrOpt('task_executor',
               default='taskflow',
               help=_("""
Task executor to be used to run task scripts.

Provide a string value representing the executor to use for task
executions. By default, ``TaskFlow`` executor is used.

``TaskFlow`` helps make task executions easy, consistent, scalable
and reliable. It also enables creation of lightweight task objects
and/or functions that are combined together into flows in a
declarative manner.

Possible values:
    * taskflow

Related Options:
    * None

""")),
    cfg.StrOpt('work_dir',
               sample_default='/work_dir',
               help=_("""
Absolute path to the work directory to use for asynchronous
task operations.

The directory set here will be used to operate over images -
normally before they are imported in the destination store.

NOTE: When providing a value for ``work_dir``, please make sure
that enough space is provided for concurrent tasks to run
efficiently without running out of space.

A rough estimation can be done by multiplying the number of
``max_workers`` with an average image size (e.g 500MB). The image
size estimation should be done based on the average size in your
deployment. Note that depending on the tasks running you may need
to multiply this number by some factor depending on what the task
does. For example, you may want to double the available size if
image conversion is enabled. All this being said, remember these
are just estimations and you should do them based on the worst
case scenario and be prepared to act in case they were wrong.

Possible values:
    * String value representing the absolute path to the working
      directory

Related Options:
    * None

""")),
]

common_opts = [
    cfg.StrOpt('hashing_algorithm',
               default='sha512',
               help=_("""
Secure hashing algorithm used for computing the 'os_hash_value' property.

This option configures the Glance "multihash", which consists of two
image properties: the 'os_hash_algo' and the 'os_hash_value'.  The
'os_hash_algo' will be populated by the value of this configuration
option, and the 'os_hash_value' will be populated by the hexdigest computed
when the algorithm is applied to the uploaded or imported image data.

The value must be a valid secure hash algorithm name recognized by the
python 'hashlib' library.  You can determine what these are by examining
the 'hashlib.algorithms_available' data member of the version of the
library being used in your Glance installation.  For interoperability
purposes, however, we recommend that you use the set of secure hash
names supplied by the 'hashlib.algorithms_guaranteed' data member because
those algorithms are guaranteed to be supported by the 'hashlib' library
on all platforms.  Thus, any image consumer using 'hashlib' locally should
be able to verify the 'os_hash_value' of the image.

The default value of 'sha512' is a performant secure hash algorithm.

If this option is misconfigured, any attempts to store image data will fail.
For that reason, we recommend using the default value.

Possible values:
    * Any secure hash algorithm name recognized by the Python 'hashlib'
      library

Related options:
    * None

""")),
    cfg.IntOpt('image_member_quota', default=128,
               help=_("""
Maximum number of image members per image.

This limits the maximum of users an image can be shared with. Any negative
value is interpreted as unlimited.

Related options:
    * None

""")),
    cfg.IntOpt('image_property_quota', default=128,
               help=_("""
Maximum number of properties allowed on an image.

This enforces an upper limit on the number of additional properties an image
can have. Any negative value is interpreted as unlimited.

""")),
    cfg.IntOpt('image_tag_quota', default=128,
               help=_("""
Maximum number of tags allowed on an image.

Any negative value is interpreted as unlimited.

Related options:
    * None

""")),
    cfg.IntOpt('image_location_quota', default=10,
               help=_("""
Maximum number of locations allowed on an image.

Any negative value is interpreted as unlimited.

Related options:
    * None

""")),
    cfg.IntOpt('limit_param_default', default=25, min=1,
               help=_("""
The default number of results to return for a request.

Responses to certain API requests, like list images, may return
multiple items. The number of results returned can be explicitly
controlled by specifying the ``limit`` parameter in the API request.
However, if a ``limit`` parameter is not specified, this
configuration value will be used as the default number of results to
be returned for any API request.

NOTES:
    * The value of this configuration option may not be greater than
      the value specified by ``api_limit_max``.
    * Setting this to a very large value may slow down database
      queries and increase response times. Setting this to a
      very low value may result in poor user experience.

Possible values:
    * Any positive integer

Related options:
    * api_limit_max

""")),
    cfg.IntOpt('api_limit_max', default=1000, min=1,
               help=_("""
Maximum number of results that could be returned by a request.

As described in the help text of ``limit_param_default``, some
requests may return multiple results. The number of results to be
returned are governed either by the ``limit`` parameter in the
request or the ``limit_param_default`` configuration option.
The value in either case, can't be greater than the absolute maximum
defined by this configuration option. Anything greater than this
value is trimmed down to the maximum value defined here.

NOTE: Setting this to a very large value may slow down database
      queries and increase response times. Setting this to a
      very low value may result in poor user experience.

Possible values:
    * Any positive integer

Related options:
    * limit_param_default

""")),
    cfg.BoolOpt('show_image_direct_url', default=False,
                help=_("""
Show direct image location when returning an image.

This configuration option indicates whether to show the direct image
location when returning image details to the user. The direct image
location is where the image data is stored in backend storage. This
image location is shown under the image property ``direct_url``.

When multiple image locations exist for an image, the best location
is displayed based on the location strategy indicated by the
configuration option ``location_strategy``.

NOTES:
    * Revealing image locations can present a GRAVE SECURITY RISK as
      image locations can sometimes include credentials. Hence, this
      is set to ``False`` by default. Set this to ``True`` with
      EXTREME CAUTION and ONLY IF you know what you are doing!
    * If an operator wishes to avoid showing any image location(s)
      to the user, then both this option and
      ``show_multiple_locations`` MUST be set to ``False``.

Possible values:
    * True
    * False

Related options:
    * show_multiple_locations
    * location_strategy

""")),
    # NOTE(flaper87): The policy.yaml file should be updated and the location
    # related rules set to admin only once this option is finally removed.
    # NOTE(rosmaita): Unfortunately, this option is used to gate some code
    # paths; if the location related policies are set admin-only, then no
    # normal users can save or retrieve image data.
    cfg.BoolOpt('show_multiple_locations', default=False,
                deprecated_for_removal=True,
                deprecated_reason=_('Use of this option, deprecated since '
                                    'Newton, is a security risk and will be '
                                    'removed once we figure out a way to '
                                    'satisfy those use cases that currently '
                                    'require it.  An earlier announcement '
                                    'that the same functionality can be '
                                    'achieved with greater granularity by '
                                    'using policies is incorrect.  You cannot '
                                    'work around this option via policy '
                                    'configuration at the present time, '
                                    'though that is the direction we believe '
                                    'the fix will take.  Please keep an eye '
                                    'on the Glance release notes to stay up '
                                    'to date on progress in addressing this '
                                    'issue.'),
                deprecated_since='Newton',
                help=_("""
Show all image locations when returning an image.

This configuration option indicates whether to show all the image
locations when returning image details to the user. When multiple
image locations exist for an image, the locations are ordered based
on the location strategy indicated by the configuration opt
``location_strategy``. The image locations are shown under the
image property ``locations``.

NOTES:
    * Revealing image locations can present a GRAVE SECURITY RISK as
      image locations can sometimes include credentials. Hence, this
      is set to ``False`` by default. Set this to ``True`` with
      EXTREME CAUTION and ONLY IF you know what you are doing!
    * See https://wiki.openstack.org/wiki/OSSN/OSSN-0065 for more
      information.
    * If an operator wishes to avoid showing any image location(s)
      to the user, then both this option and
      ``show_image_direct_url`` MUST be set to ``False``.

Possible values:
    * True
    * False

Related options:
    * show_image_direct_url
    * location_strategy

""")),
    cfg.IntOpt('image_size_cap', default=1099511627776, min=1,
               max=9223372036854775808,
               help=_("""
Maximum size of image a user can upload in bytes.

An image upload greater than the size mentioned here would result
in an image creation failure. This configuration option defaults to
1099511627776 bytes (1 TiB).

NOTES:
    * This value should only be increased after careful
      consideration and must be set less than or equal to
      8 EiB (9223372036854775808).
    * This value must be set with careful consideration of the
      backend storage capacity. Setting this to a very low value
      may result in a large number of image failures. And, setting
      this to a very large value may result in faster consumption
      of storage. Hence, this must be set according to the nature of
      images created and storage capacity available.

Possible values:
    * Any positive number less than or equal to 9223372036854775808

""")),
    cfg.StrOpt('user_storage_quota', default='0',
               help=_("""
Maximum amount of image storage per tenant.

This enforces an upper limit on the cumulative storage consumed by all images
of a tenant across all stores. This is a per-tenant limit.

The default unit for this configuration option is Bytes. However, storage
units can be specified using case-sensitive literals ``B``, ``KB``, ``MB``,
``GB`` and ``TB`` representing Bytes, KiloBytes, MegaBytes, GigaBytes and
TeraBytes respectively. Note that there should not be any space between the
value and unit. Value ``0`` signifies no quota enforcement. Negative values
are invalid and result in errors.

This has no effect if ``use_keystone_limits`` is enabled.

Possible values:
    * A string that is a valid concatenation of a non-negative integer
      representing the storage value and an optional string literal
      representing storage units as mentioned above.

Related options:
    * use_keystone_limits

""")),
    cfg.BoolOpt('use_keystone_limits', default=False,
                help=_("""
Utilize per-tenant resource limits registered in Keystone.

Enabling this feature will cause Glance to retrieve limits set in keystone
for resource consumption and enforce them against API users. Before turning
this on, the limits need to be registered in Keystone or all quotas will be
considered to be zero, and thus reject all new resource requests.

These per-tenant resource limits are independent from the static
global ones configured in this config file. If this is enabled, the
relevant static global limits will be ignored.
""")),
    cfg.HostAddressOpt('pydev_worker_debug_host',
                       sample_default='localhost',
                       help=_("""
Host address of the pydev server.

Provide a string value representing the hostname or IP of the
pydev server to use for debugging. The pydev server listens for
debug connections on this address, facilitating remote debugging
in Glance.

Possible values:
    * Valid hostname
    * Valid IP address

Related options:
    * None

""")),
    cfg.PortOpt('pydev_worker_debug_port',
                default=5678,
                help=_("""
Port number that the pydev server will listen on.

Provide a port number to bind the pydev server to. The pydev
process accepts debug connections on this port and facilitates
remote debugging in Glance.

Possible values:
    * A valid port number

Related options:
    * None

""")),
    cfg.StrOpt('metadata_encryption_key',
               secret=True,
               help=_("""
AES key for encrypting store location metadata.

Provide a string value representing the AES cipher to use for
encrypting Glance store metadata.

NOTE: The AES key to use must be set to a random string of length
16, 24 or 32 bytes.

Possible values:
    * String value representing a valid AES key

Related options:
    * None

""")),
    cfg.StrOpt('digest_algorithm',
               default='sha256',
               deprecated_for_removal=True,
               deprecated_since="Dalmatian",
               deprecated_reason=_("""
This option has had no effect since the removal of native SSL support.
"""),
               help=_("""
Digest algorithm to use for digital signature.

Provide a string value representing the digest algorithm to
use for generating digital signatures. By default, ``sha256``
is used.

To get a list of the available algorithms supported by the version
of OpenSSL on your platform, run the command:
``openssl list-message-digest-algorithms``.
Examples are 'sha1', 'sha256', and 'sha512'.

NOTE: ``digest_algorithm`` is not related to Glance's image signing
and verification. It is only used to sign the universally unique
identifier (UUID) as a part of the certificate file and key file
validation.

Possible values:
    * An OpenSSL message digest algorithm identifier

Relation options:
    * None

""")),
    cfg.StrOpt('node_staging_uri',
               default='file:///tmp/staging/',
               help=_("""
The URL provides location where the temporary data will be stored

This option is for Glance internal use only. Glance will save the
image data uploaded by the user to 'staging' endpoint during the
image import process.

This option does not change the 'staging' API endpoint by any means.

NOTE: It is discouraged to use same path as [task]/work_dir

NOTE: 'file://<absolute-directory-path>' is the only option
api_image_import flow will support for now.

NOTE: The staging path must be on shared filesystem available to all
Glance API nodes.

Possible values:
    * String starting with 'file://' followed by absolute FS path

Related options:
    * [task]/work_dir

""")),
    cfg.ListOpt('enabled_import_methods',
                item_type=cfg.types.String(quotes=True),
                bounds=True,
                default=['glance-direct', 'web-download',
                         'copy-image'],
                help=_("""
    List of enabled Image Import Methods

    'glance-direct', 'copy-image' and 'web-download' are enabled by default.
    'glance-download' is available, but requires federated deployments.

    Related options:
        * [DEFAULT]/node_staging_uri""")),
    cfg.StrOpt('worker_self_reference_url',
               default=None,
               help=_("""
The URL to this worker.

If this is set, other glance workers will know how to contact this one
directly if needed. For image import, a single worker stages the image
and other workers need to be able to proxy the import request to the
right one.

If unset, this will be considered to be `public_endpoint`, which
normally would be set to the same value on all workers, effectively
disabling the proxying behavior.

Possible values:
    * A URL by which this worker is reachable from other workers

Related options:
    * public_endpoint

""")),
]

wsgi_opts = [
    cfg.IntOpt('task_pool_threads',
               default=16,
               min=1,
               help=_("""
The number of threads (per worker process) in the pool for processing
asynchronous tasks. This controls how many asynchronous tasks (i.e. for
image interoperable import) each worker can run at a time. If this is
too large, you *may* have increased memory footprint per worker and/or you
may overwhelm other system resources such as disk or outbound network
bandwidth. If this is too small, image import requests will have to wait
until a thread becomes available to begin processing.""")),
    cfg.StrOpt('python_interpreter',
               default=None,
               help=_("""
Path to the python interpreter to use when spawning external
processes. If left unspecified, this will be sys.executable, which should
be the same interpreter running Glance itself. However, in some situations
(for example, uwsgi) sys.executable may not actually point to a python
interpreter and an alternative value must be set.""")),
]


CONF = cfg.CONF
CONF.register_opts(paste_deploy_opts, group='paste_deploy')
CONF.register_opts(image_format_opts, group='image_format')
CONF.register_opts(task_opts, group='task')
CONF.register_opts(common_opts)
CONF.register_opts(wsgi_opts, group='wsgi')
policy.Enforcer(CONF)


def parse_args(args=None, usage=None, default_config_files=None):
    CONF(args=args,
         project='glance',
         version=version.cached_version_string(),
         usage=usage,
         default_config_files=default_config_files)


def parse_cache_args(args=None):
    config_files = cfg.find_config_files(project='glance', prog='glance-api')
    # NOTE(abhishekk): Reading glance-api file first and glance-cache file
    # later so that if glance-cache file has different values set for some
    # cache related options then they should take precedence.
    config_files.extend(cfg.find_config_files(project='glance',
                                              prog='glance-cache'))
    parse_args(args=args, default_config_files=config_files)


def _get_deployment_flavor(flavor=None):
    """
    Retrieve the paste_deploy.flavor config item, formatted appropriately
    for appending to the application name.

    :param flavor: if specified, use this setting rather than the
                   paste_deploy.flavor configuration setting
    """
    if not flavor:
        flavor = CONF.paste_deploy.flavor
    return '' if not flavor else ('-' + flavor)


def _get_paste_config_path():
    paste_suffix = '-paste.ini'
    conf_suffix = '.conf'
    if CONF.config_file:
        # Assume paste config is in a paste.ini file corresponding
        # to the last config file
        path = CONF.config_file[-1].replace(conf_suffix, paste_suffix)
    else:
        path = CONF.prog + paste_suffix
    return CONF.find_file(os.path.basename(path))


def _get_deployment_config_file():
    """
    Retrieve the deployment_config_file config item, formatted as an
    absolute pathname.
    """
    path = CONF.paste_deploy.config_file
    if not path:
        path = _get_paste_config_path()
    if not path or not (os.path.isfile(os.path.abspath(path))):
        msg = _("Unable to locate paste config file for %s.") % CONF.prog
        raise RuntimeError(msg)
    return os.path.abspath(path)


def load_paste_app(app_name, flavor=None, conf_file=None):
    """
    Builds and returns a WSGI app from a paste config file.

    We assume the last config file specified in the supplied ConfigOpts
    object is the paste config file, if conf_file is None.

    :param app_name: name of the application to load
    :param flavor: name of the variant of the application to load
    :param conf_file: path to the paste config file

    :raises RuntimeError: when config file cannot be located or application
            cannot be loaded from config file
    """
    # append the deployment flavor to the application name,
    # in order to identify the appropriate paste pipeline
    app_name += _get_deployment_flavor(flavor)

    if not conf_file:
        conf_file = _get_deployment_config_file()

    try:
        logger = logging.getLogger(__name__)
        logger.debug("Loading %(app_name)s from %(conf_file)s",
                     {'conf_file': conf_file, 'app_name': app_name})

        app = deploy.loadapp("config:%s" % conf_file, name=app_name)

        # Log the options used when starting if we're in debug mode...
        if CONF.debug:
            CONF.log_opt_values(logger, logging.DEBUG)

        return app
    except (LookupError, ImportError) as e:
        msg = (_("Unable to load %(app_name)s from "
                 "configuration file %(conf_file)s."
                 "\nGot: %(e)r") % {'app_name': app_name,
                                    'conf_file': conf_file,
                                    'e': e})
        logger.error(msg)
        raise RuntimeError(msg)


def set_config_defaults():
    """This method updates all configuration default values."""
    set_cors_middleware_defaults()

    # TODO(gmann): Remove setting the default value of config policy_file
    # once oslo_policy change the default value to 'policy.yaml'.
    # https://github.com/openstack/oslo.policy/blob/a626ad12fe5a3abd49d70e3e5b95589d279ab578/oslo_policy/opts.py#L49
    DEFAULT_POLICY_FILE = 'policy.yaml'
    opts.set_defaults(cfg.CONF, DEFAULT_POLICY_FILE)


def set_cors_middleware_defaults():
    """Update default configuration options for oslo.middleware."""
    cors.set_defaults(
        allow_headers=['Content-MD5',
                       'X-Image-Meta-Checksum',
                       'X-Storage-Token',
                       'Accept-Encoding',
                       'X-Auth-Token',
                       'X-Identity-Status',
                       'X-Roles',
                       'X-Service-Catalog',
                       'X-User-Id',
                       'X-Tenant-Id',
                       'X-OpenStack-Request-ID'],
        expose_headers=['X-Image-Meta-Checksum',
                        'X-Auth-Token',
                        'X-Subject-Token',
                        'X-Service-Token',
                        'X-OpenStack-Request-ID'],
        allow_methods=['GET',
                       'PUT',
                       'POST',
                       'DELETE',
                       'PATCH']
    )
