.. -*- rst -*-

Metadata definition properties
******************************

Creates, lists, shows details for, updates, and deletes metadata definition
properties.

*Since API v2.2*

Create property
~~~~~~~~~~~~~~~

.. rest_method::  POST /v2/metadefs/namespaces/{namespace_name}/properties

Creates a property definition in a namespace.

The schema is a subset of the JSON property definition schema.

Normal response codes: 201

Error response codes: 400, 404


Request
-------

.. rest_parameters:: metadefs-parameters.yaml

   - namespace_name: namespace_name
   - name: name
   - title: title
   - type: type
   - additionalItems: additionalItems
   - description: property-description-in-request
   - default: default
   - items: items
   - operators: operators
   - enum: enum
   - maximum: maximum
   - minItems: minItems
   - readonly: readonly
   - minimum: minimum
   - maxItems: maxItems
   - maxLength: maxLength
   - uniqueItems: uniqueItems
   - pattern: pattern
   - minLength: minLength

Request Example
---------------

.. literalinclude:: samples/metadef-property-create-request.json
   :language: json


Response Parameters
-------------------

.. rest_parameters:: metadefs-parameters.yaml

   - additionalItems: additionalItems
   - description: property-description
   - title: title
   - default: default
   - items: items
   - operators: operators
   - enum: enum
   - maximum: maximum
   - minItems: minItems
   - readonly: readonly
   - minimum: minimum
   - maxItems: maxItems
   - maxLength: maxLength
   - uniqueItems: uniqueItems
   - pattern: pattern
   - type: type
   - minLength: minLength
   - name: name

Response Example
----------------

.. literalinclude:: samples/metadef-property-create-response.json
   :language: json


List properties
~~~~~~~~~~~~~~~

.. rest_method::
   GET /v2/metadefs/namespaces/{namespace_name}/properties

Lists property definitions in a namespace.

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

   - properties: properties-dict


Response Example
----------------

.. literalinclude:: samples/metadef-properties-list-response.json
   :language: json


Show property definition
~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::
   GET /v2/metadefs/namespaces/{namespace_name}/properties/{property_name}

Shows the definition for a property.

If you use the ``resource_type`` query parameter, the API removes the prefix of
the resource type from the property name before it submits the query. This
enables you to look for a property name that starts with a prefix from an
associated resource type.

The response body shows a single property entity.


Normal response codes: 200

Error response codes: 401, 403, 404


Request
-------

.. rest_parameters:: metadefs-parameters.yaml

   - property_name: property_name
   - namespace_name: namespace_name
   - resource_type: resource_type-in-query


Response Parameters
-------------------

.. rest_parameters:: metadefs-parameters.yaml

   - additionalItems: additionalItems
   - description: property-description
   - title: title
   - default: default
   - items: items
   - operators: operators
   - enum: enum
   - maximum: maximum
   - minItems: minItems
   - readonly: readonly
   - minimum: minimum
   - maxItems: maxItems
   - maxLength: maxLength
   - uniqueItems: uniqueItems
   - pattern: pattern
   - type: type
   - minLength: minLength
   - name: name



Response Example
----------------

.. literalinclude:: samples/metadef-property-details-response.json
   :language: json




Update property definition
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::
   PUT /v2/metadefs/namespaces/{namespace_name}/properties/{property_name}

Updates a property definition.

Normal response codes: 200

Error response codes: 400, 401, 403, 404, 409


Request
-------

.. rest_parameters:: metadefs-parameters.yaml

   - namespace_name: namespace_name
   - property_name: property_name
   - name: name-property
   - title: title
   - type: type
   - additionalItems: additionalItems
   - description: description
   - default: default
   - items: items
   - operators: operators
   - enum: enum
   - maximum: maximum
   - minItems: minItems
   - readonly: readonly
   - minimum: minimum
   - maxItems: maxItems
   - maxLength: maxLength
   - uniqueItems: uniqueItems
   - pattern: pattern
   - minLength: minLength

Request Example
---------------

.. literalinclude:: samples/metadef-property-create-request.json
   :language: json


Response Parameters
-------------------

.. rest_parameters:: metadefs-parameters.yaml

   - additionalItems: additionalItems
   - description: description
   - title: title
   - default: default
   - items: items
   - operators: operators
   - enum: enum
   - maximum: maximum
   - minItems: minItems
   - readonly: readonly
   - minimum: minimum
   - maxItems: maxItems
   - maxLength: maxLength
   - uniqueItems: uniqueItems
   - pattern: pattern
   - type: type
   - minLength: minLength
   - name: name-property



Response Example
----------------

.. literalinclude:: samples/metadef-property-update-response.json
   :language: json



Remove property definition
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::
   DELETE /v2/metadefs/namespaces/{namespace_name}/properties/{property_name}

Removes a property definition from a namespace.

.. note::
    If the namespace containing the property is protected, that is, if the
    ``protected`` attribute of the namespace is ``true``, then you must first
    set the ``protected`` attribute to ``false`` on the namespace before you
    will be permitted to delete the property.

    * If you try to delete a property from a protected namespace, the call
      returns the ``403`` response code.
    * To change the ``protected`` attribute of a namespace, use the
      :ref:`Update namespace <v2-update-namespace>` call.

When you successfully delete a property from a namespace, the
response is empty and the response code is ``204``.

Normal response codes: 204

Error response codes: 401, 403, 404


Request
-------

.. rest_parameters:: metadefs-parameters.yaml

   - property_name: property_name
   - namespace_name: namespace_name

