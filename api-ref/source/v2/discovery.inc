.. -*- rst -*-

Image Service Info (Discovery)
******************************

General information
~~~~~~~~~~~~~~~~~~~

These calls allow you to discover useful information about what
services you may consume from a particular deployment of the
OpenStack Image Service.


.. _import-discovery-call:

Import methods and values discovery
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/info/import

Returns information concerning the constraints around image import in
the cloud in which the call is made, for example, supported container
formats, supported disk formats, maximum image size, etc.  This call
contains a ``import-methods`` field consisting of an array of string
identifiers indicating what import methods are supported in the cloud
in which the call is made.
*(Since Image API v2.6)*

.. note::
   In the Image API v2.6-2.8, this discovery call contains
   **only** the ``import-methods`` field.

Normal response codes: 200

Error response codes: 400, 401, 403


Request
-------

There are no request parameters.

This call does not allow a request body.


Response Parameters
-------------------

.. rest_parameters:: images-parameters.yaml

   - import-methods: import-methods


Response Example
----------------

.. literalinclude:: samples/image-info-import-response.json
   :language: json


.. _store-discovery-call:

List stores
~~~~~~~~~~~

.. rest_method::  GET /v2/info/stores

A multiple store backend support is introduced in the Rocky release
as a part of the EXPERIMENTAL Image API v2.8.

In version 2.7 of the API, this call will return a 404 (Not Found).
Use the :ref:`API versions call <versions-call>` to determine
what API versions are available in your cloud.

Normal response codes: 200

Error response codes: 404


Request
-------

There are no request parameters.

This call does not allow a request body.


Response Parameters
-------------------

.. rest_parameters:: discovery-parameters.yaml

   - stores: stores


Response Example
----------------

.. literalinclude:: samples/stores-list-response.json
   :language: json

Quota usage
~~~~~~~~~~~

.. rest_method:: GET /v2/info/usage

The user's quota and current usage are displayed, if enabled by
server-side configuration.

Normal response codes: 200

Request
-------

There are no request parameters.

This call does not allow a request body.

Response Example
----------------

.. literalinclude:: samples/usage-response.json
   :language: json

List stores detail
~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/info/stores/detail

Lists all the backend stores, with detail, accessible to admins,
for non-admin user API will return bad request.

Normal response codes: 200

Error response codes: 403, 404


Request
-------

There are no request parameters.

This call does not allow a request body.


Response Parameters
-------------------

.. rest_parameters:: discovery-parameters.yaml

   - stores: stores-detail


Response Example
----------------

.. literalinclude:: samples/stores-list-detail-response.json
   :language: json

