.. -*- rst -*-

Stores
******

A multiple store backend support is introduced in the Rocky release
as a part of the EXPERIMENTAL Image API v2.8.

.. note:: The Multi Store feature is introduced as EXPERIMENTAL in Rocky and
          its use in production systems is currently **not supported**.
          However we encourage people to use this feature for testing
          purposes and report the issues so that we can make it stable and
          fully supported in Stein release.

In version 2.7 of the API, this call will return a 404 (Not Found).
Use the :ref:`API versions call <versions-call>` to determine
what API verisons are available in your cloud.

List of available store backends for glance.

.. _store-discovery-call:

List stores
~~~~~~~~~~~

.. rest_method::  GET /v2/info/stores

Lists stores.

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
