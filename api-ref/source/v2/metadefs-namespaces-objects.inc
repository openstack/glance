.. -*- rst -*-

Metadata definition objects
***************************

Creates, lists, shows details for, updates, and deletes metadata definition
objects.

*Since API v2.2*

Create object
~~~~~~~~~~~~~

.. rest_method::  POST /v2/metadefs/namespaces/{namespace_name}/objects

Creates an object definition in a namespace.

Normal response codes: 201

Error response codes: 400, 401, 403, 404, 409


Request
-------

.. rest_parameters:: metadefs-parameters.yaml

   - namespace_name: namespace_name
   - name: object-name
   - description: object-description-in-request
   - properties: object-properties-in-request
   - required: object-required-in-request

Request Example
---------------

.. literalinclude:: samples/metadef-object-create-request.json
   :language: json


Response Parameters
-------------------

.. rest_parameters:: metadefs-parameters.yaml

   - created_at: created_at
   - description: object-description
   - name: object-name
   - properties: object-properties
   - required: object-required
   - schema: object-schema
   - self: self
   - updated_at: updated_at

Response Example
----------------

.. literalinclude:: samples/metadef-object-create-response.json
   :language: json


List objects
~~~~~~~~~~~~

.. rest_method::  GET /v2/metadefs/namespaces/{namespace_name}/objects

Lists object definitions in a namespace.

Returns a subset of the larger collection of namespaces and a link
that you can use to get the next set of namespaces. You should
always check for the presence of a ``next`` link and use it as the
URI in a subsequent HTTP GET request. You should follow this
pattern until a ``next`` link is no longer provided. The next link
preserves any query parameters that you send in your initial
request. You can use the ``first`` link to jump back to the first
page of the collection. If you prefer to paginate through
namespaces manually, use the ``limit`` and ``marker`` parameters.

Use the ``resource_types`` and ``visibility`` query parameters to
filter the response.

For example, set the ``resource_types`` query parameter to
``OS::Glance::Image,OS::Nova::Flavor`` to filter the response to
include only namespaces that are associated with the given resource
types.

You can sort the results of this operation by using the
``sort_key`` and ``sort_dir`` parameters. The API uses the natural
sorting of whatever namespace attribute is provided as the
``sort_key``.


Normal response codes: 200

Error response codes: 401, 403, 404


Request
-------

.. rest_parameters:: metadefs-parameters.yaml

   - namespace_name: namespace_name
   - visibility: visibility-in-query
   - resource_types: resource_types-in-query
   - sort_key: sort_key
   - sort_dir: sort_dir


Response Parameters
-------------------

.. rest_parameters:: metadefs-parameters.yaml

   - display_name: display_name
   - description: description
   - namespace: namespace
   - visibility: visibility
   - protected: protected
   - namespaces: namespaces
   - resource_type_associations: resource_type_associations


Response Example
----------------

.. literalinclude:: samples/metadef-objects-list-response.json
   :language: json



Show object
~~~~~~~~~~~

.. rest_method::  GET /v2/metadefs/namespaces/{namespace_name}/objects/{object_name}

Shows the definition for an object.

The response body shows a single object entity.

Normal response codes: 200

.. yep, 400 if the request includes a body

Error response codes: 400, 401, 403, 404


Request
-------

.. rest_parameters:: metadefs-parameters.yaml

   - namespace_name: namespace_name
   - object_name: object_name

There is no request body.


Response Parameters
-------------------

.. rest_parameters:: metadefs-parameters.yaml

   - created_at: created_at
   - description: object-description
   - name: object-name
   - properties: object-properties
   - required: object-required
   - schema: object-schema
   - self: self
   - updated_at: updated_at


Response Example
----------------

.. literalinclude:: samples/metadef-object-details-response.json
   :language: json



Update object
~~~~~~~~~~~~~

.. rest_method::  PUT /v2/metadefs/namespaces/{namespace_name}/objects/{object_name}

Updates an object definition in a namespace.

The object resource is completely replaced by what you specify in the request
body.  Thus, if you leave out any of the optional parameters, and they exist in
the current object, they will be eliminated by this call.

It is possible to change the name of the object with this call; if you do, note
that the URL for the object (specified by the ``self`` field) will change.

Normal response codes: 200

Error response codes: 400, 401, 403, 404, 409


Request
-------

.. rest_parameters:: metadefs-parameters.yaml

   - namespace_name: namespace_name
   - object_name: object_name
   - name: object-name
   - description: object-description-in-request
   - properties: object-properties-in-request
   - required: object-required-in-request


Request Example
---------------

.. literalinclude:: samples/metadef-object-update-request.json
   :language: json


Response Parameters
-------------------

.. rest_parameters:: metadefs-parameters.yaml

   - created_at: created_at
   - description: object-description
   - name: object-name
   - properties: object-properties
   - required: object-required
   - schema: object-schema
   - self: self
   - updated_at: updated_at


Response Example
----------------

.. literalinclude:: samples/metadef-object-update-response.json
   :language: json



Delete object
~~~~~~~~~~~~~

.. rest_method::  DELETE /v2/metadefs/namespaces/{namespace_name}/objects/{object_name}

Deletes an object definition from a namespace.

.. note::
    If the namespace containing the object is protected, that is, if the
    ``protected`` attribute of the namespace is ``true``, then you must first
    set the ``protected`` attribute to ``false`` on the namespace before you
    will be permitted to delete the object.

    * If you try to delete an object from a protected namespace, the call
      returns the ``403`` response code.
    * To change the ``protected`` attribute of a namespace, use the
      :ref:`Update namespace <v2-update-namespace>` call.

When you successfully delete an object from a namespace, the
response is empty and the response code is ``204``.

Normal response codes: 204

Error response codes: 400, 401, 403, 404


Request
-------

.. rest_parameters:: metadefs-parameters.yaml

   - namespace_name: namespace_name
   - object_name: object_name

There is no request body.

There is no response body.
