.. -*- rst -*-

Metadata definition namespaces
******************************

Creates, lists, shows details for, updates, and deletes metadata
definition namespaces. Defines namespaces that can contain property
definitions, object definitions, and resource type associations.

*Since API v2.2*


Create namespace
~~~~~~~~~~~~~~~~

.. rest_method::  POST /v2/metadefs/namespaces

Creates a namespace.

A namespace must be unique across all users.  Attempting to create an already
existing namespace will result in a 409 (Conflict) response.

The ``Location`` response header contains the newly-created URI for
the namespace.

Normal response codes: 201

Error response codes: 400, 401, 403, 409


Request
-------

.. rest_parameters:: metadefs-parameters.yaml

   - namespace: namespace
   - display_name: display_name
   - description: description
   - visibility: visibility-in-request
   - protected: protected-in-request

The request body may also contain properties, objects, and resource type
associations, or these can be added later by the :ref:`v2-update-namespace`
call.

Request Example
---------------

.. literalinclude:: samples/metadef-namespace-create-request-simple.json
   :language: json


Response Parameters
-------------------

.. rest_parameters:: metadefs-parameters.yaml

   - Location: Location
   - created_at: created_at
   - description: description
   - display_name: display_name
   - namespace: namespace
   - owner: owner
   - protected: protected
   - schema: schema-namespace
   - self: self
   - updated_at: updated_at
   - visibility: visibility

If the request body contained properties, objects, or resource type
associations, these will be included in the response.


Response Example
----------------

.. code-block:: console

    HTTP/1.1 201 Created
    Content-Length: 427
    Content-Type: application/json; charset=UTF-8
    Location: http://glance.openstack.example.org/v2/metadefs/namespaces/FredCo::SomeCategory::Example
    X-Openstack-Request-Id: req-6d4a8ad2-c018-4bfc-8fe5-1a36c23c43eb
    Date: Thu, 19 May 2016 16:05:48 GMT

.. literalinclude:: samples/metadef-namespace-create-response-simple.json
   :language: json


List namespaces
~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/metadefs/namespaces

Lists available namespaces.

Returns a list of namespaces to which the authenticated user has access.  If
the list is too large to fit in a single response, either because of operator
configuration or because you've included a ``limit`` query parameter in the
request to restrict the response size, the response will contain a link that
you can use to get the next page of namespaces. Check for the presence of a
``next`` link and use it as the URI in a subsequent HTTP GET request. Follow
this pattern until a ``next`` link is no longer provided.

The ``next`` link preserves any query parameters that you send in your initial
request. You can use the ``first`` link to return to the first page in the
collection. If you prefer to paginate through namespaces manually, use the
``limit`` and ``marker`` parameters.

The list operation accepts the ``resource_types`` and ``visibility`` query
parameters, which you can use to filter the response.

To sort the results of this operation, use the ``sort_key`` and ``sort_dir``
parameters. The API uses the natural sorting order in the namespace attribute
that you provide as the ``sort_key`` parameter.

Normal response codes: 200

Error response codes: 401, 403, 404


Request
-------

.. rest_parameters:: metadefs-parameters.yaml

   - limit: limit
   - marker: marker
   - visibility: visibility-in-query
   - resource_types: resource_types-in-query
   - sort_key: sort_key
   - sort_dir: sort_dir

Response Parameters
-------------------

.. rest_parameters:: metadefs-parameters.yaml

   - first: first
   - namespaces: namespaces
   - next: next
   - schema: schema-namespaces

Response Example
----------------

.. literalinclude:: samples/metadef-namespaces-list-response.json
   :language: json


Get namespace details
~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/metadefs/namespaces/{namespace_name}

Gets details for a namespace.

The response body shows a single namespace entity with all details
including properties, objects, and resource type associations.

If the namespace contains a resource type association that specifies a prefix,
you may optionally include the name of the resource type as a query parameter.
In that case, the prefix will be applied to all property names in the response.
(See below for an example.)

Normal response codes: 200

.. returns 400 if a request body is sent

Error response codes: 400, 401, 403, 404


Request
-------

.. rest_parameters:: metadefs-parameters.yaml

   - namespace_name: namespace_name
   - resource_type: resource_type-in-query-namespace-detail

The request does not take a body.


Response Parameters
-------------------

.. rest_parameters:: metadefs-parameters.yaml

   - created_at: created_at
   - description: description
   - display_name: display_name
   - namespace: namespace
   - objects: objects
   - owner: owner
   - properties: properties-dict
   - protected: protected
   - resource_type_associations: resource_type_associations
   - schema: schema-namespace
   - self: self
   - visibility: visibility


Response Example
----------------

.. literalinclude:: samples/metadef-namespace-details-response.json
   :language: json

Response Example (with resource_type query parameter)
-----------------------------------------------------

This is the result of the following request:

``GET /v2/metadefs/namespaces/OS::Compute::Libvirt?resource_type=OS::Glance::Image``

Note that the name of each property has had the appropriate prefix applied to
it.

.. literalinclude:: samples/metadef-namespace-details-with-rt-response.json
   :language: json


.. _v2-update-namespace:

Update namespace
~~~~~~~~~~~~~~~~

.. rest_method::  PUT /v2/metadefs/namespaces/{namespace_name}

Updates a namespace.

.. note::
   Be careful using this call, especially when all you want to do is change the
   ``protected`` value so that you can delete some objects, properties, or
   resource type associations in the namespace.

   While only the ``namespace`` is required in the request body, if this call
   is made with *only* the ``namespace`` in request body, the other attributes
   listed below will be set to their default values -- which in the case of
   ``description`` and ``display_name``, is null.

   So if you want to change *only* the ``protected`` value with this call, be
   sure to also include the current values of the following parameters in the
   request body:

   - ``description``
   - ``display_name``
   - ``namespace``
   - ``visibility``

   The objects, properties, and resource type associations in a namespace
   are unaffected by this call.

Normal response codes: 200

Error response codes: 400, 401, 403, 404, 409


Request
-------

.. rest_parameters:: metadefs-parameters.yaml

   - namespace_name: namespace_name
   - description: description
   - display_name: display_name
   - namespace: namespace
   - protected: protected-in-request
   - visibility: visibility-in-request

Request Example
---------------

.. literalinclude:: samples/metadef-namespace-update-request.json
   :language: json

Response Parameters
-------------------

.. rest_parameters:: metadefs-parameters.yaml

   - created_at: created_at
   - description: description
   - display_name: display_name
   - namespace: namespace
   - owner: owner
   - protected: protected
   - schema: schema-namespace
   - self: self
   - updated_at: updated_at
   - visibility: visibility


Response Example
----------------

.. literalinclude:: samples/metadef-namespace-update-response.json
   :language: json


Delete namespace
~~~~~~~~~~~~~~~~

.. rest_method::  DELETE /v2/metadefs/namespaces/{namespace_name}

Deletes a namespace and its properties, objects, and any resource type
associations.

.. note::

    If the namespace is protected, that is, if the ``protected`` attribute of
    the namespace is ``true``, then you must first set the ``protected``
    attribute to ``false`` on the namespace before you will be permitted to
    delete it.

    * If you try to delete a protected namespace, the call returns the ``403``
      response code.
    * To change the ``protected`` attribute of a namespace, use the
      :ref:`Update namespace <v2-update-namespace>` call.

A successful operation returns the HTTP ``204`` (No Content) response code.

Normal response codes: 204

Error response codes: 400, 401, 403, 404


Request
-------

.. rest_parameters:: metadefs-parameters.yaml

   - namespace_name: namespace_name

The request does not take a body.

The request does not return a body.
