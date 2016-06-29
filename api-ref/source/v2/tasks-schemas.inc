.. -*- rst -*-

Task Schemas
************

Gets a JSON-schema document that represents an individual task and a
list of tasks.

.. _tasks-schema:

Show tasks schema
~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/schemas/tasks

*(Since Images v2.2)*

Shows a JSON schema document that represents a list of *tasks*.

An tasks list entity is a container of entities containing abbreviated
information about individual tasks.

The following schema is solely an example. Consider only the
response to the API call as authoritative.

Normal response codes: 200

Error response codes: 401


Request
-------

This operation has no request parameters and does not accept a request body.


Response Example
----------------

.. literalinclude:: samples/schemas-tasks-list-response.json
   :language: json

.. _task-schema:

Show task schema
~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/schemas/task

*(Since Images v2.2)*

Shows a JSON schema document that represents an *task* entity.

The following schema is solely an example. Consider only the
response to the API call as authoritative.

Normal response codes: 200

Error response codes: 401


Request
-------

This operation has no request parameters and does not accept a request body.


Response Example
----------------

.. literalinclude:: samples/schemas-task-show-response.json
   :language: json
