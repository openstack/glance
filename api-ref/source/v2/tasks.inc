.. -*- rst -*-

Tasks
*****

Creates, lists, and shows details for tasks.

*(Since API v2.2)*


General Information
~~~~~~~~~~~~~~~~~~~

**API Status**

This API was made admin-only by default in the OpenStack Mitaka release.  Thus
the following calls may not be available to end users in your cloud.  Please
consult your cloud provider's documentation for more information.

**Conceptual Overview**

Please see the `Tasks <https://docs.openstack.org/glance/latest/admin/tasks.html>`_
section of the Glance Developers Documentation for a conceptual overview of
tasks.

**Task Status**

The possible status values for tasks are presented in the following table.

.. list-table::
    :header-rows: 1

    * - Status
      - Description
    * - pending
      - The task is waiting for execution.
    * - processing
      - Execution of the task is underway.
    * - success
      - The task completed successfully.  The ``result`` element should be
        populated.
    * - failure
      - The task failed to complete.  The ``message`` element should be a
        non-empty string.


Create task
~~~~~~~~~~~

.. rest_method::  POST /v2/tasks

Creates a task.

Normal response codes: 201

Error response codes: 401, 413, 415


Request
-------

.. rest_parameters:: tasks-parameters.yaml

   - type: type
   - input: input


Request Example
---------------

.. literalinclude:: samples/task-create-request.json
   :language: json


Response Parameters
-------------------

.. rest_parameters:: tasks-parameters.yaml

   - created_at: created_at
   - id: id
   - input: input
   - message: message
   - owner: owner
   - result: result
   - schema: schema-task
   - self: self
   - status: status
   - type: type
   - updated_at: updated_at

Response Example
----------------

.. literalinclude:: samples/task-create-response.json
   :language: json


List tasks
~~~~~~~~~~

.. rest_method::  GET /v2/tasks

Lists tasks.

Normal response codes: 200

Error response codes: 403, 404, 413


Request
-------

.. rest_parameters:: tasks-parameters.yaml

   - limit: limit
   - marker: marker
   - sort_dir: sort_dir
   - sort_key: sort_key
   - status: status-in-query
   - type: type-in-query


Response Parameters
-------------------

.. rest_parameters:: tasks-parameters.yaml

   - first: first
   - next: next
   - schema: schema-tasks
   - tasks: tasks


Response Example
----------------

.. literalinclude:: samples/tasks-list-response.json
   :language: json


Show task details
~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/tasks/{task_id}

Shows details for a task.


Normal response codes: 200

Error response codes: 404


Request
-------

.. rest_parameters:: tasks-parameters.yaml

   - task_id: task_id


Response Parameters
-------------------

.. rest_parameters:: tasks-parameters.yaml

   - created_at: created_at
   - expires_at: expires_at
   - id: id
   - input: input
   - message: message
   - owner: owner
   - result: result
   - schema: schema-task
   - self: self
   - status: status
   - type: type
   - updated_at: updated_at


Response Example (task status: processing)
------------------------------------------

.. literalinclude:: samples/task-show-processing-response.json
   :language: json

Response Example (task status: success)
------------------------------------------

.. literalinclude:: samples/task-show-success-response.json
   :language: json

Response Example (task status: failure)
---------------------------------------

.. literalinclude:: samples/task-show-failure-response.json
   :language: json
