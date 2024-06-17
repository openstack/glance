..
      Licensed under the Apache License, Version 2.0 (the "License"); you may
      not use this file except in compliance with the License. You may obtain
      a copy of the License at

          http://www.apache.org/licenses/LICENSE-2.0

      Unless required by applicable law or agreed to in writing, software
      distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
      WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
      License for the specific language governing permissions and limitations
      under the License.

.. _iir:

Interoperable Image Import
==========================

Version 2.6 of the Image Service API introduces new API calls that implement an
interoperable image import process.  These API calls, and the workflow for
using them, are described in the `Interoperable Image Import`_ section of the
`Image Service API reference`_.  That documentation explains the end user's
view of interoperable image import.  In this section, we discuss what
configuration options are available to operators.

The interoperable image import process uses Glance tasks, but does *not*
require that the Tasks API be exposed to end users.  Further, it requires
the **taskflow** task executor.  The following configuration options must
be set:

* in the ``[task]`` option group:

  * ``task_executor`` must either be set to **taskflow** or be used in
    its default value

* in the ``[taskflow_executor]`` options group:

  * The default values are fine.  It's a good idea to read through the
    descriptions in the sample **glance-api.conf** file to see what
    options are available.

    .. note::
       You can find an example glance-api.conf_ file in the **etc/**
       subdirectory of the Glance source code tree.  Make sure that you are
       looking in the correct branch for the OpenStack release you are working
       with.

* in the default options group:

  * ``node_staging_uri`` as a ``file:///path/to/dir`` URI (in the
    single-store case) or
    ``[os_glance_staging_store]/filesystem_store_datadir`` as a path
    (in the multi-store case) must specify a location writable by the
    glance user. See `Staging Directory Configuration`_ for more
    details and recommendations.

  * ``enabled_import_methods`` must specify the import methods you are exposing
    at your installation.  The default value for this setting is
    ``['glance-direct','web-download']``.  See the next section for a
    description of these import methods.

Additionally, your policies must be such that an ordinary end user
can manipulate tasks.  In releases prior to Pike, we recommended that
the task-related policies be admin-only so that end users could not
access the Tasks API.  In Pike, a new policy was introduced that controls
access to the Tasks API.  Thus it is now possible to keep the individual
task policies unrestricted while not exposing the Tasks API to end
users.  Thus, the following is the recommended configuration for the
task-related policies:

.. code-block:: ini

   "get_task": "",
   "get_tasks": "",
   "add_task": "",
   "modify_task": "",
   "tasks_api_access": "role:admin",

Image Import Methods
--------------------

Glance provides four import methods that you can make available to your
users: ``glance-direct``, ``web-download``, ``glance-download``, and
``copy-image``. By default, ``glance-download`` is not enabled.

* The ``glance-direct`` import method allows your users to upload image data
  directly to Glance.

* The ``web-download`` method allows an end user to import an image from a
  remote URL.  The image data is retrieved from the URL and stored in the
  Glance backend.  (In other words, this is a *copy-from* operation.)

  .. note::
     The ``web-download`` import method replaces the copy-from functionality
     that was available in the Image API v1 but previously absent from v2.
     Additionally, the Image API v1 was removed in Glance 17.0.0 (Rocky).

* The ``glance-download`` method allows an end user to import an image from a
  remote glance. This import method is used to import an image from another
  openstack region which is federated by the same keystone.

* The ``copy-image`` method allows and end user to copy existing image to
  other Glance backends available in deployment. This import method is
  only used if multiple glance backends are enabled in your deployment.

You control which methods are available to API users by the
``enabled_import_methods`` configuration option in the default section of the
**glance-api.conf** file.

Staging Directory Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

All of the import methods require a staging directory to be
configured. This is essentially a temporary scratch location where the
image can be staged (by the user via ``glance-direct``), downloaded
(by ``web-download``), or pulled from an existing store (as in
``copy-image``) before being copied to a given store location. In the
single-store case, this location is specified by a local filesystem
URI in the ``node_staging_uri`` configuration option, like this:

.. code-block:: ini

   [DEFAULTS]
   node_staging_uri = file:///var/lib/glance/staging

In the multistore case, as described in :ref:`reserved_stores`, the
staging store should be configured with the path:

.. code-block:: ini

   [os_glance_staging_store]
   filesystem_store_datadir = /var/lib/glance/staging

The staging directory for each worker must be configured for all
import methods, and can be either local (recommended) or shared. In
the case of a shared location, all Glance API workers will be
dependent on the shared storage availability, will compete for IO
resources, and may introduce additional network traffic. If `local`
storage is chosen, you must configure each worker with the URL by
which the other workers can reach it directly. This allows one worker
behind a load balancer to stage an image in one request, and another
worker to handle the subsequent import request. As an example:

.. code-block:: ini

   [DEFAULTS]
   worker_self_reference_url = https://glance01.example.com:8000

This assumes you have several glance-api workers named ``glance01``,
``glance02``, etc behind your load balancer.

Note that ``public_endpoint`` will be used as the default if
``worker_self_reference_url`` is not set. As this will generally be
set to the same value across all workers, the result is that all
workers will assume the same identity and thus revert to
shared-staging behavior. If ``public_endpoint`` is set differently for
one or a group of workers, they will be considered isolated and thus
not sharing staging storage.


Configuring the glance-direct method
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For the ``glance-direct`` method, make sure that ``glance-direct`` is included
in the list specified by your ``enabled_import_methods`` setting, and that
staging directory config options are set properly.

Note that in order to use ``glance-direct``, the
``worker_self_reference_url`` configuration option must be set as
above, or all Glance API workers must have their staging directory
mounted to a common location (such as an NFS server).

Configuring the web-download method
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To enable the ``web-download`` import method, make sure that it is included in
the list of methods in the ``enabled_import_methods`` option, and that staging
directory config options are set properly.

Additionally, you have the following configuration available.

Depending on the nature of your cloud and the sophistication of your users,
you may wish to restrict what URIs they may use for the web-download import
method.

.. note::
   You should be aware of OSSN-0078_, "copy_from in Image Service API v1 allows
   network port scan".  The v1 copy_from feature does not have the
   configurability described here.

You can do this by configuring options in the
``[import_filtering_opts]`` section of the **glance-image-import.conf** file.

.. note::
   The **glance-image-import.conf** is an optional file.  (See below for a
   discussion of the default settings if you don't include this file.)

   You can find an example file named glance-image-import.conf.sample_ in
   the **etc/** subdirectory of the Glance source code tree.  Make sure that
   you are looking in the correct branch for the OpenStack release you are
   working with.

You can whitelist ("allow *only* these") or blacklist ("do *not* allow these")
at three levels:

* scheme (``allowed_schemes``, ``disallowed_schemes``)
* host (``allowed_hosts``, ``disallowed_hosts``)
* port (``allowed_ports``, ``disallowed_ports``)

There are six configuration options, but the way it works is that if you
specify both at any level, the whitelist is honored and the blacklist is
ignored.  (So why have both? Well, you may want to whitelist a scheme, but
blacklist a host, and whitelist a particular port.)

Validation of a URI happens as follows:

1. The scheme is checked.

   a. missing scheme: reject
   b. If there's a whitelist, and the scheme is not in it: reject.  Otherwise,
      skip c and continue on to 2.
   c. If there's a blacklist, and the scheme is in it: reject.

2. The hostname is checked.

   a. missing hostname: reject
   b. If there's a whitelist, and the host is not in it: reject.  Otherwise,
      skip c and continue on to 3.
   c. If there's a blacklist, and the host is in it: reject.

3. If there's a port in the URI, the port is checked.

   a. If there's a whitelist, and the port is not in it: reject.  Otherwise,
      skip b and continue on to 4.
   b. If there's a blacklist, and the port is in it: reject.

4. The URI is accepted as valid.

Note that if you allow a scheme, either by whitelisting it or by not
blacklisting it, any URI that uses the default port for that scheme by not
including a port in the URI is allowed.  If it does include a port in the URI,
the URI will be validated according to the above rules.

Default settings
++++++++++++++++

The **glance-image-import.conf** is an optional file.  Here are the default
settings for these options:

* ``allowed_schemes`` - ``['http', 'https']``
* ``disallowed_schemes`` - empty list
* ``allowed_hosts`` - empty list
* ``disallowed_hosts`` - empty list
* ``allowed_ports`` - ``[80, 443]``
* ``disallowed_ports`` - empty list

Thus if you use the defaults, end users will only be able to access URIs
using the http or https scheme.  The only ports users will be able to specify
are 80 and 443.  (Users do not have to specify a port, but if they do, it must
be either 80 or 443.)

.. note::
   The **glance-image-import.conf** is an optional file.  You can find an
   example file named glance-image-import.conf.sample_ in the **etc/**
   subdirectory of the Glance source code tree.  Make sure that you are looking
   in the correct branch for the OpenStack release you are working with.

Configuring the glance-download method
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To enable the ``glance-download`` import method, make sure that it is included
in the list of methods in the ``enabled_import_methods`` option, and that
staging directory config options are set properly.

Additionally, you have the following configuration available.

Depending your needs on image properties you may configure addional properties
to be copied from the remote image to the local image.

You can do this by configuring options in the
``[glance_download_opts]`` section of the **glance-image-import.conf** file.

``extra_properties`` options is a list of properties that should be copied from
the remote image. The properties listed should be read as properties that
"start with" as it allows you to set a namespace instead of explicitly listing
each property of the namespace.

Default values are :
``['hw_', 'trait:', 'os_distro', 'os_secure_boot', 'os_type']``

If you decide to set this option the default values will be totally ignored
unless you explicitly set them.

.. note::
   The ``extra_properties`` option will ignore namespaces reserved by glance,
   meaning that all the properties starting with ``os_glance`` won't be set
   on the local image.

.. note::
   The **glance-image-import.conf** is an optional file.  You can find an
   example file named glance-image-import.conf.sample in the **etc/**
   subdirectory of the Glance source code tree. Make sure that you are looking
   in the correct branch for the OpenStack release you are working with.

Configuring the copy-image method
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For the ``copy-image`` method, make sure that ``copy-image`` is included
in the list specified by your ``enabled_import_methods`` setting as well
as you have multiple glance backends configured in your environment. To
allow copy-image operation to be performed by users on images they do
not own, you can set the `copy_image` policy to something other than
the default, for example::

    "copy_image": "'public':%(visibility)s"

.. _iir_plugins:

Copying existing-image in multiple stores
-----------------------------------------
Starting with Ussuri release, it is possible to copy existing image data
into multiple stores using interoperable image import workflow.

Basically user will be able to copy only those images which are
owned by him. Unless the copying of unowned images are allowed by
cloud operator by enforcing policy check, user will get Forbidden
(Operation not permitted response) for such copy operations. Even if
copying of unowned images is allowed by enforcing policy, ownership of
the image remains unchanged.

Operator or end user can either copy the existing image by specifying
``all_stores`` as True in request body or by passing list of desired
stores in request body. If ``all_stores`` is specified and image data
is already present in some of the available stores then those stores
will be silently excluded from the list of all configured stores, whereas
if ``all_stores`` is False, ``stores`` are specified in explicitly in
request body and if image data is present in any of the specified store
then the request will be rejected. In case of ``all_stores`` is specified
in request body and cloud operator has also configured a read-only
``http`` store then it will be excluded explicitly.

Image will be copied to staging area from one of the available locations
and then import processing will be continued using import workflow as
explained in below ``Importing in multiple stores`` section.

Importing in multiple stores
----------------------------

Starting with Ussuri, it is possible to import data into multiple stores
using interoperable image import workflow.

The status of the image is set to ``active`` according to the value of
``all_stores_must_succeed`` parameter.

* If set to False: the image will be available as soon as an import to
  one store has succeeded.

* If set to True (default): the status is set to ``active`` only when all
  stores have been successfully treated.

Check progress
~~~~~~~~~~~~~~

As each store is treated sequentially, it can take quite some time for the
workflow to complete depending on the size of the image and the number of
stores to import data to.
It is possible to follow task progress by looking at 2 reserved image
properties:

* ``os_glance_importing_to_stores``: This property contains a list of stores
  that has not yet been processed. At the beginning of the import flow, it is
  filled with the stores provided in the request. Each time a store is fully
  handled, it is removed from the list.

* ``os_glance_failed_import``: Each time an import in a store fails, it is
  added to this list. This property is emptied at the beginning of the import
  flow.

These 2 properties are also available in the notifications sent during the
workflow:

.. note:: Example

    An operator calls the import image api with the following parameters::

        curl -i -X POST -H "X-Auth-Token: $token"
             -H "Content-Type: application/json"
             -d '{"method": {"name":"glance-direct"},
                  "stores": ["ceph1", "ceph2"],
                  "all_stores_must_succeed": false}'
            $image_url/v2/images/{image_id}/import

    The upload fails for 'ceph2' but succeed on 'ceph1'. Since the parameter
    ``all_stores_must_succeed`` has been set to 'false', the task ends
    successfully and the image is now active.

    Notifications sent by glance looks like (payload is truncated for
    clarity)::

        {
            "priority": "INFO",
            "event_type": "image.prepare",
            "timestamp": "2019-08-27 16:10:30.066867",
            "payload": {"status": "importing",
                        "name": "example",
                        "backend": "ceph1",
                        "os_glance_importing_to_stores": ["ceph1", "ceph2"],
                        "os_glance_failed_import": [],
                        ...},
            "message_id": "1c8993ad-e47c-4af7-9f75-fa49596eeb10",
            ...
        }

        {
            "priority": "INFO",
            "event_type": "image.upload",
            "timestamp": "2019-08-27 16:10:32.058812",
            "payload": {"status": "active",
                        "name": "example",
                        "backend": "ceph1",
                        "os_glance_importing_to_stores": ["ceph2"],
                        "os_glance_failed_import": [],
                        ...},
            "message_id": "8b8993ad-e47c-4af7-9f75-fa49596eeb11",
            ...
        }

        {
            "priority": "INFO",
            "event_type": "image.prepare",
            "timestamp": "2019-08-27 16:10:33.066867",
            "payload": {"status": "active",
                        "name": "example",
                        "backend": "ceph2",
                        "os_glance_importing_to_stores": ["ceph2"],
                        "os_glance_failed_import": [],
                        ...},
            "message_id": "1c8993ad-e47c-4af7-9f75-fa49596eeb18",
            ...
        }

        {
            "priority": "ERROR",
            "event_type": "image.upload",
            "timestamp": "2019-08-27 16:10:34.058812",
            "payload": "Error Message",
            "message_id": "8b8993ad-e47c-4af7-9f75-fa49596eeb11",
            ...
        }

Customizing the image import process
------------------------------------

When a user issues the image-import call, Glance retrieves the staged image
data, processes it, and saves the result in the backing store.  You can
customize the nature of this processing by using *plugins*.  Some plugins
are provided by the Glance project team, you can use third-party plugins,
or you can write your own.

Technical information
~~~~~~~~~~~~~~~~~~~~~

The import step of interoperable image import is performed by a `Taskflow`_
"flow" object.  This object, provided by Glance, will call any plugins you have
specified in the ``glance-image-import.conf`` file.  The plugins are loaded by
`Stevedore`_ and must be listed in the entry point registry in the namespace
``glance.image_import.plugins``.  (If you are using only plugins provided by
the Glance project team, these are already registered for you.)

A plugin must be written in Python as a `Taskflow "Task" object`_.  The file
containing this object must be present in the ``glance/async_/flows/plugins``
directory.  The plugin file must contain a ``get_flow`` function that returns a
Taskflow Task object wrapped in a linear flow.  See the ``no_op`` plugin,
located at ``glance/async_/flows/plugins/no_op.py`` for an example of how to do
this.

Specifying the plugins to be used
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

First, the plugin code must exist in the directory
``glance/async_/flows/plugins``.  The name of a plugin is the filename (without
extension) of the file containing the plugin code.  For example, a file named
``fred_mertz.py`` would contain the plugin ``fred_mertz``.

Second, the plugin must be listed in the entry point list for the
``glance.image_import.plugins`` namespace.  (If you are using only plugins
provided with Glance, this will have already been done for you, but it never
hurts to check.)  The entry point list is in ``setup.cfg``.  Find the section
with the heading ``[entry_points]`` and look for the line beginning with
``glance.image_import.plugins =``.  It will be followed by a series of lines
of the form::

  <plugin-name> = <module-package-name>:get_flow

For example::

  no_op = glance.async_.flows.plugins.no_op:get_flow

Make sure any plugin you want to use is included here.

Third, the plugin must be listed in the ``glance-image-import.conf`` file as
one of the plugin names in the list providing the value for the
``image_import_plugins`` option.  Plugins are executed in the order they are
specified in this list.

The Image Property Injection Plugin
-----------------------------------
.. list-table::

   * - release introduced
     - Queens (Glance 16.0.0)
   * - configuration file
     - ``glance-image-import.conf``
   * - configuration file section
     - ``[inject_metadata_properties]``

This plugin implements the Glance spec `Inject metadata properties
automatically to non-admin images`_.  One use case for this plugin is a
situation where an operator wants to put specific metadata on images imported
by end users so that virtual machines booted from these images will be located
on specific compute nodes.  Since it's unlikely that an end user (the image
owner) will know the appropriate properties or values, an operator may use
this plugin to inject the properties automatically upon image import.

.. note::

   This plugin may only be used as part of the interoperable image import
   workflow (``POST v2/images/{image_id}/import``).  *It has no effect on the
   image data upload call* (``PUT v2/images/{image_id}/file``).

   You can guarantee that your end users must use interoperable image import by
   restricting the ``upload_image`` policy appropriately in the Glance
   ``policy.yaml`` file.  By default, this policy is unrestricted (that is,
   any authorized user may make the image upload call).

   For example, to allow only admin or service users to make the image upload
   call, the policy could be restricted as follows:

   .. code-block:: text

      "upload_image": "role:admin or (service_user_id:<uuid of nova user>) or
         (service_roles:<service user role>)"

   where "service_role" is the role which is created for the service user
   and assigned to trusted services.

To use the Image Property Injection Plugin, the following configuration is
required.

1. You will need to configure 'glance-image-import.conf' file as shown
   below:

   .. code-block:: ini

       [image_import_opts]
       image_import_plugins = [inject_image_metadata]

       [inject_metadata_properties]
       ignore_user_roles = admin,...
       inject = property1:value1,property2:value2,...

   The first section, ``image_import_opts``, is used to enable the plugin by
   specifying the plugin name as one of the elements of the list that is the
   value of the `image_import_plugins` parameter.  The plugin name is simply
   the module name under glance/async\_/flows/plugins/

   The second section, ``inject_metadata_properties``, is where you set the
   parameters for the injection plugin.  (Note that the values you specify here
   only have an effect if the plugin has been enabled in the
   ``image_import_plugins`` list as described above.)

   * ``ignore_user_roles`` is a comma-separated list of Keystone roles that the
     plugin will ignore.  In other words, if the user making the image import
     call has any of these roles, the plugin will not inject any properties
     into the image.

   * ``inject`` is a comma-separated list of properties and values that will be
     injected into the image record for the imported image.  Each property and
     value should be separated by a colon (':') as shown in the example above.

2. If your use case is such that you don't want to allow end-users to create,
   modify, or delete metadata properties that you are injecting during the
   interoperable image import process, you will need to protect these
   properties using the Glance property protection feature (available since
   the Havana release).

   For example, suppose there is a property named 'property1' that you want
   injected during import, but you only want an administrator or service user
   to be able to create this property, and you want only an administrator to be
   able to modify or delete it.  You could accomplish this by adding the
   following to the property protection configuration file:

   .. code-block:: ini

       [property1]
       create = admin,service_role
       read = admin,service_role,member,_member_
       update = admin
       delete = admin

   See the :ref:`property-protections` section of this Guide for more
   information.

The Image Conversion
--------------------
.. list-table::

   * - release introduced
     - Rocky (Glance 17.0.0)
   * - configuration file
     - ``glance-image-import.conf``
   * - configuration file section
     - ``[image_conversion]``

This plugin implements automated image conversion for Interoperable Image
Import. One use case for this plugin would be environments where Ceph is used
as image back-end and operators want to optimize the back-end capabilities by
ensuring that all images will be in raw format while not putting the burden of
converting the images to their end users.

.. note::

   This plugin may only be used as part of the interoperable image import
   workflow (``POST v2/images/{image_id}/import``).  *It has no effect on the
   image data upload call* (``PUT v2/images/{image_id}/file``).

   You can guarantee that your end users must use interoperable image import by
   restricting the ``upload_image`` policy appropriately in the Glance
   ``policy.yaml`` file.  By default, this policy is unrestricted (that is,
   any authorized user may make the image upload call).

   For example, to allow only admin or service users to make the image upload
   call, the policy could be restricted as follows:

   .. code-block:: text

      "upload_image": "role:admin or (service_user_id:<uuid of nova user>) or
         (service_roles:<service user role>)"

   where "service_role" is the role which is created for the service user
   and assigned to trusted services.

To use the Image Conversion Plugin, the following configuration is
required.

You will need to configure 'glance-image-import.conf' file as shown below:

.. code-block:: ini

   [image_import_opts]
   image_import_plugins = ['image_conversion']

   [image_conversion]
   output_format = raw

.. note::

  The default output format is raw in which case there is no need to have
  'image_conversion' section and its 'output_format' defined in the config
  file.

  The input format needs to be one of the `qemu-img supported ones`_ for this
  feature to work. In case of qemu-img call failing on the source image the
  import process will fail if 'image_conversion' plugin is enabled.

.. note::

  ``image_import_plugins`` config option is a list and multiple plugins can be
  enabled for the import flow. The plugins are not run in parallel. One can
  enable multiple plugins by configuring them in the
  ``glance-image-import.conf`` for example as following:

  .. code-block:: ini

       [image_import_opts]
       image_import_plugins = ['inject_image_metadata', 'image_conversion']

       [inject_metadata_properties]
       ignore_user_roles = admin,...
       inject = "property1":"value1","property2":"value2",...

       [image_conversion]
       output_format = raw

The Image Decompression
-----------------------
.. list-table::

   * - release introduced
     - Ussuri (Glance 20.0.0)
   * - configuration file
     - ``glance-image-import.conf``

This plugin implements automated image decompression for Interoperable Image
Import. One use case for this plugin would be environments where user or
operator wants to use 'web-download' method and the image provider supplies
only compressed images.

.. note::

   This plugin may only be used as part of the interoperable image import
   workflow (``POST v2/images/{image_id}/import``).  *It has no effect on the
   image data upload call* (``PUT v2/images/{image_id}/file``).

   You can guarantee that your end users must use interoperable image import by
   restricting the ``upload_image`` policy appropriately in the Glance
   ``policy.yaml`` file.  By default, this policy is unrestricted (that is,
   any authorized user may make the image upload call).

   For example, to allow only admin or service users to make the image upload
   call, the policy could be restricted as follows:

   .. code-block:: text

      "upload_image": "role:admin or (service_user_id:<uuid of nova user>) or
      (service_roles:<service user role>)"

   where "service_role" is the role which is created for the service user
   and assigned to trusted services.

.. note::

    The plugin will not decompress images whose ``container_format`` is set to
    ``compressed``. This is to maintain the original intent of the image
    creator.

To use the Image Decompression Plugin, the following configuration is
required.

You will need to add "image_decompression" to 'glance-image-import.conf' file
as shown below:

.. code-block:: ini

   [image_import_opts]
   image_import_plugins = ['image_decompression']

.. note::

  The supported archive types for Image Decompression are zip, lha/lzh and gzip.
  Currently the plugin does not support multi-layered archives (like tar.gz).
  Lha/lzh is only supported in case python3 `lhafile` dependency library is
  installed, absence of this dependency will fail the import job where lha file
  is provided. (In this case we know it won't be bootable as the image is
  compressed and we do not have means to decompress it.)

.. note::

  ``image_import_plugins`` config option is a list and multiple plugins can be
  enabled for the import flow. The plugins are not run in parallel. One can
  enable multiple plugins by configuring them in the
  ``glance-image-import.conf`` for example as following:

  .. code-block:: ini

     [image_import_opts]
     image_import_plugins = ['image_decompression', 'image_conversion']

     [image_conversion]
     output_format = raw

  If Image Conversion is used together, decompression must happen first, this
  is ensured by ordering the plugins.

.. _glance-api.conf: https://opendev.org/openstack/glance/src/branch/master/etc/glance-api.conf
.. _glance-image-import.conf.sample: https://opendev.org/openstack/glance/src/branch/master/etc/glance-image-import.conf.sample
.. _`Image Import Refactor`: https://specs.openstack.org/openstack/glance-specs/specs/mitaka/approved/image-import/image-import-refactor.html
.. _`Image Service API reference`: https://docs.openstack.org/api-ref/image/
.. _`Inject metadata properties automatically to non-admin images`: https://specs.openstack.org/openstack/glance-specs/specs/queens/approved/glance/inject-automatic-metadata.html
.. _`Interoperable Image Import`: https://docs.openstack.org/api-ref/image/v2/index.html#interoperable-image-import
.. _OSSN-0078: https://wiki.openstack.org/wiki/OSSN/OSSN-0078
.. _`Stevedore`: https://docs.openstack.org/stevedore
.. _`Taskflow`: https://docs.openstack.org/taskflow
.. _`Taskflow "Task" object`: https://docs.openstack.org/taskflow/latest/user/atoms.html#task
.. _`qemu-img supported ones`: https://github.com/qemu/qemu/blob/master/qemu-img.texi#L599-L725
