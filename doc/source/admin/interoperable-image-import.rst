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

.. code-block:: none

   "get_task": "",
   "get_tasks": "",
   "add_task": "",
   "modify_task": "",
   "tasks_api_access": "role:admin",


.. _`Image Import Refactor`: https://specs.openstack.org/openstack/glance-specs/specs/mitaka/approved/image-import/image-import-refactor.html
.. _`Interoperable Image Import`: https://developer.openstack.org/api-ref/image/v2/index.html#interoperable-image-import
