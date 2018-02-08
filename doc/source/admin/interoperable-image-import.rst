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

The EXPERIMENTAL version 2.6 of the Image Service API introduces a Minimal
Viable Product of the interoperable image import process described in the
Glance design document `Image Import Refactor`_.  The API calls available
in the current implementation are described in the `Interoperable Image
Import`_ section of the Image Service API reference.  Here's how to configure
Glance to enable the interoperable image import process.

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

* in the default options group:

  * ``enable_image_import`` must be set to **True** (the default is
    False).  When False, the **/versions** API response does not
    include the v2.6 API and calls to the import URIs will behave
    like they do in v2.5, that is, they'll return a 404 response.

  * ``node_staging_uri`` must specify a location writable by the glance
    user.  If you have multiple Glance API nodes, this should be a
    reference to a shared filesystem available to all the nodes.

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
containing this object must be present in the ``glance/async/flows/plugins``
directory.  The plugin file must contain a ``get_flow`` function that returns a
Taskflow Task object wrapped in a linear flow.  See the ``no_op`` plugin,
located at ``glance/async/flows/plugins/no_op.py`` for an example of how to do
this.

Specifying the plugins to be used
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

First, the plugin code must exist in the directory
``glance/async/flows/plugins``.  The name of a plugin is the filename (without
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

  no_op = glance.async.flows.plugins.no_op:get_flow

Make sure any plugin you want to use is included here.

Third, the plugin must be listed in the ``glance-image-import.conf`` file as
one of the plugin names in the list providing the value for the
``image_import_plugins`` option.  Plugins are executed in the order they are
specified in this list.

.. _`Image Import Refactor`: https://specs.openstack.org/openstack/glance-specs/specs/mitaka/approved/image-import/image-import-refactor.html
.. _`Interoperable Image Import`: https://developer.openstack.org/api-ref/image/v2/index.html#interoperable-image-import
.. _`Stevedore`: https://docs.openstack.org/stevedore
.. _`Taskflow`: https://docs.openstack.org/taskflow
.. _`Taskflow "Task" object`: https://docs.openstack.org/taskflow/latest/user/atoms.html#task

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
   ``policy.json`` file.  By default, this policy is unrestricted (that is,
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
       inject = "property1":"value1","property2":"value2",...

   The first section, ``image_import_opts``, is used to enable the plugin by
   specifying the plugin name as one of the elements of the list that is the
   value of the `image_import_plugins` parameter.  The plugin name is simply
   the module name under glance/async/flows/plugins/

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
     value should be quoted and separated by a colon (':') as shown in the
     example above.

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

.. _`Inject metadata properties automatically to non-admin images`: https://specs.openstack.org/openstack/glance-specs/specs/queens/approved/glance/inject-automatic-metadata.html
