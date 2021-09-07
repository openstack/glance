.. -*- rst -*-

Stores
******

Multi-store backend support allows for storing copies of an image in multiple places.

Delete image from store
~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  DELETE /v2/stores/{store_id}/{image_id}

This API allows you to delete a copy of the image from a specific store.
*(Since Image API v2.10)*

.. note::
    * This API will not allow deletion of the last location for an image.

Normal response codes: 204

Error response codes: 400, 401, 403, 404, 409

Request
-------

.. rest_parameters:: images-parameters.yaml

   - store_id: store-in-path
   - image_id: image_id-in-path

