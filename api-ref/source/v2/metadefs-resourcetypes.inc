.. -*- rst -*-

Metadata definition resource types
**********************************

Lists resource types. Also, creates, lists, and removes resource type
associations in a namespace.

*Since API v2.2*


List resource types
~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/metadefs/resource_types

Lists all available resource types.

Using the other API calls in this section, you can create and maintain
*resource type associations* between metadata definition namespaces and the
resource types that are returned by this call.

Normal response codes: 200

Error response codes: 400, 401, 404


Request
-------

There are no request parameters.


Response Parameters
-------------------

.. rest_parameters:: metadefs-parameters.yaml

   - resource_types: resource_types-list


Response Example
----------------

.. literalinclude:: samples/metadef-resource-types-list-response.json
   :language: json


Create resource type association
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::
   POST /v2/metadefs/namespaces/{namespace_name}/resource_types

Creates a resource type association between a namespace and the resource
type specified in the body of the request.

.. note::
   If the resource type name specified does not name an existing resource type,
   a new resource type will be created as a side effect of this operation.

Normal response codes: 201

Error response codes: 400, 401, 403, 404, 409


Request
-------

.. rest_parameters:: metadefs-parameters.yaml

   - namespace_name: namespace_name
   - name: name
   - prefix: prefix
   - properties_target: properties_target


Request Example
---------------

.. literalinclude:: samples/metadef-resource-type-create-request.json
   :language: json



Response Parameters
-------------------

.. rest_parameters:: metadefs-parameters.yaml

   - created_at: created_at
   - prefix: prefix
   - properties_target: properties_target
   - name: name
   - updated_at: updated_at


List resource type associations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/metadefs/namespaces/{namespace_name}/resource_types

Lists resource type associations in a namespace.

Normal response codes: 200

Error response codes: 400, 401, 403, 404


Request
-------

.. rest_parameters:: metadefs-parameters.yaml

   - namespace_name: namespace_name

There is no request body.


Response Parameters
-------------------

.. rest_parameters:: metadefs-parameters.yaml

   - resource_type_associations: resource_type_associations



Response Example
----------------

.. literalinclude:: samples/metadef-resource-type-assoc-list-response.json
   :language: json


Remove resource type association
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::
   DELETE /v2/metadefs/namespaces/{namespace_name}/resource_types/{name}

Removes a resource type association in a namespace.

.. note::
    If the namespace containing the association is protected, that is, if the
    ``protected`` attribute of the namespace is ``true``, then you must first
    set the ``protected`` attribute to ``false`` on the namespace before you
    will be permitted to remove the resource type association.

    * If you try to delete a resource type association from a protected
      namespace, the call returns the ``403`` response code.
    * To change the ``protected`` attribute of a namespace, use the
      :ref:`Update namespace <v2-update-namespace>` call.

When you successfully delete a resource type association from a namespace, the
response is empty and the response code is ``204``.

Normal response codes: 204

Error response codes: 400, 401, 403, 404


Request
-------

.. rest_parameters:: metadefs-parameters.yaml

   - namespace_name: namespace_name
   - name: resource_type_name
