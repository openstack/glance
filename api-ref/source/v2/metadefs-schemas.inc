.. -*- rst -*-

Metadata definition schemas
***************************

Gets a JSON-schema document that represents a metadata definition
entity.

*(Since API v2.2)*


Show metadata definition namespace schema
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/schemas/metadefs/namespace

Shows a JSON schema document that represents a metadata definition *namespace* entity.

The following schema document is an example. The authoritative response is the
actual response to the API call.


Normal response codes: 200

Error response codes: 400, 401


Request
-------

There are no request parameters.  The call does not take a request body.


Response Example
----------------

.. literalinclude:: samples/schemas-metadef-namespace-show-response.json
   :language: json



Show metadata definition namespaces schema
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/schemas/metadefs/namespaces

Shows a JSON schema document that represents a metadata definition *namespaces*
entity.

A namespaces entity is a container for *namespace* entities.

The following schema document is an example. The authoritative response is the
actual response to the API call.


Normal response codes: 200

Error response codes: 400, 401


Request
-------

There are no request parameters.  The call does not take a request body.


Response Example
----------------

.. literalinclude:: samples/schemas-metadef-namespaces-list-response.json
   :language: json


.. _md-schema-rt-assoc:

Show metadata definition namespace resource type association schema
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/schemas/metadefs/resource_type

Shows a JSON schema document that represents a metadata definition namespace
*resource type association* entity.

The following schema document is an example. The authoritative response is the
actual response to the API call.


Normal response codes: 200

Error response codes: 400, 401


Request
-------

There are no request parameters.  The call does not take a request body.


Response Example
----------------

.. literalinclude:: samples/schemas-metadef-resource-type-association-show-response.json
   :language: json


Show metadata definition namespace resource type associations schema
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/schemas/metadefs/resource_types

Shows a JSON schema document that represents a metadata definition namespace
*resource type associations* entity.

A resource type associations entity is a container for *resource type
association* entities.

The following schema document is an example. The authoritative response is the
actual response to the API call.


Normal response codes: 200

Error response codes: 400, 401


Request
-------

There are no request parameters.  The call does not take a request body.


Response Example
----------------

.. literalinclude:: samples/schemas-metadef-resource-type-associations-list-response.json
   :language: json


Show metadata definition object schema
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/schemas/metadefs/object

Shows a JSON schema document that represents a metadata definition *object*
entity.

The following schema document is an example. The authoritative response is the
actual response to the API call.


Normal response codes: 200

Error response codes: 400, 401


Request
-------

There are no request parameters.  The call does not take a request body.


Response Example
----------------

.. literalinclude:: samples/schemas-metadef-object-show-response.json
   :language: json


Show metadata definition objects schema
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/schemas/metadefs/objects

Shows a JSON schema document that represents a metadata definition *objects*
entity.

An objects entity is a container for *object* entities.

The following schema document is an example. The authoritative response is the
actual response to the API call.


Normal response codes: 200

Error response codes: 400, 401


Request
-------

There are no request parameters.  The call does not take a request body.


Response Example
----------------

.. literalinclude:: samples/schemas-metadef-objects-list-response.json
   :language: json


.. _md-schema-property:

Show metadata definition property schema
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/schemas/metadefs/property

Shows a JSON schema document that represents a metadata definition *property*
entity.

The following schema document is an example. The authoritative response is the
actual response to the API call.


Normal response codes: 200

Error response codes: 400, 401


Request
-------

There are no request parameters.  The call does not take a request body.


Response Example
----------------

.. literalinclude:: samples/schemas-metadef-property-show-response.json
   :language: json



Show metadata definition properties schema
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/schemas/metadefs/properties

Shows a JSON schema document that represents a metadata definition *properties* entity.

A properties entity is a container for *property* entities.

The following schema document is an example. The authoritative
response is the actual response to the API call.


Normal response codes: 200
Error response codes: 400, 401


Request
-------

There are no request parameters.  The call does not take a request body.


Response Example
----------------

.. literalinclude:: samples/schemas-metadef-properties-list-response.json
   :language: json



.. _md-schema-tag:

Show metadata definition tag schema
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/schemas/metadefs/tag

Shows a JSON schema document that represents a metadata definition *tag* entity.

The following schema document is an example. The authoritative response is the
actual response to the API call.


Normal response codes: 200

Error response codes: 400, 401


Request
-------

There are no request parameters.  The call does not take a request body.


Response Example
----------------

.. literalinclude:: samples/schemas-metadef-tag-show-response.json
   :language: json



Show metadata definition tags schema
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/schemas/metadefs/tags

Shows a JSON schema document that represents a metadata definition *tags*
entity.

A tags entity is a container for *tag* entities.

The following schema document is an example. The authoritative response is the
actual response to the API call.


Normal response codes: 200

Error response codes: 400, 401


Request
-------

There are no request parameters.  The call does not take a request body.


Response Example
----------------

.. literalinclude:: samples/schemas-metadef-tags-list-response.json
   :language: json
