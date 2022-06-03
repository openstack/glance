.. -*- rst -*-

Cache Manage
************

List and manage the cache.


Query cache status
~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/cache/

Lists all images in cache or queue.
*(Since Image API v2.14)*

Normal response codes: 200

Error response codes: 400, 401, 403


Request
-------

No request parameters.


Queue image
~~~~~~~~~~~

.. rest_method::  PUT /v2/cache/{image_id}/

Queues image for caching.
*(Since Image API v2.14)*

Normal response codes: 202

Error response codes: 400, 401, 403, 404


Request
-------

   - image_id: image_id-in-path


Delete image from cache
~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  DELETE /v2/cache/{image_id}/

Deletes a image from cache.
*(Since Image API v2.14)*

Normal response codes: 204

Error response codes: 400, 401, 403, 404


Request
-------

   - image_id: image_id-in-path


Clear images from cache
~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  DELETE /v2/cache/

Clears the cache and its queue.
*(Since Image API v2.14)*

Normal response codes: 204

Error response codes: 400, 401, 403


Request
-------

.. rest_parameters:: images-parameters.yaml

    - x-image-cache-clear-target: cache-clear-header
