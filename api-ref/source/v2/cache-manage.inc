.. -*- rst -*-

Cache Manage
************

List and manage the cache.


Query cache status
~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/cache

Lists all images in cache or queue.
*(Since Image API v2.14)*

Normal response codes: 200

Error response codes: 400, 401, 403


Request
-------

No request parameters.

Response Parameters
-------------------

.. rest_parameters:: cache-manage-parameters.yaml

   - cached_images: cached_images
   - queued_images: queued_images

Response Example
----------------

.. literalinclude:: samples/cache-list-response.json
   :language: json


Queue image
~~~~~~~~~~~

.. rest_method::  PUT /v2/cache/{image_id}

Queues image for caching.
*(Since Image API v2.14)*

Normal response codes: 202

Error response codes: 400, 401, 403, 404


Request
-------

.. rest_parameters:: images-parameters.yaml

   - image_id: image_id-in-path


Delete image from cache
~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  DELETE /v2/cache/{image_id}

Deletes a image from cache.
*(Since Image API v2.14)*

Normal response codes: 204

Error response codes: 400, 401, 403, 404


Request
-------

.. rest_parameters:: images-parameters.yaml

   - image_id: image_id-in-path


Clear images from cache
~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  DELETE /v2/cache

Clears the cache and its queue.
*(Since Image API v2.14)*

Normal response codes: 204

Error response codes: 400, 401, 403


Request
-------

.. rest_parameters:: images-parameters.yaml

    - x-image-cache-clear-target: cache-clear-header


Clean invalid cached images
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  POST /v2/cache/clean

Cleans up invalid cache entries and stalled incomplete images.
*(Since Image API v2.18)*

Normal response codes: 200

Error response codes: 400, 401, 403

Request
-------

No request parameters.

Request Example
---------------

.. code-block:: http

    POST /v2/cache/clean HTTP/1.1
    Host: example.com
    X-Auth-Token: <token>


Prune image cache directory
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  POST /v2/cache/prune

Prunes cached images when the cache size exceeds the maximum
configured size. Removes least recently accessed images until
the cache size is within the limit.
*(Since Image API v2.18)*

Normal response codes: 200

Error response codes: 400, 401, 403

Request
-------

No request parameters.

Request Example
---------------

.. code-block:: http

    POST /v2/cache/prune HTTP/1.1
    Host: example.com
    X-Auth-Token: <token>

Response Parameters
-------------------

.. rest_parameters:: cache-manage-parameters.yaml

   - total_bytes_pruned: total_bytes_pruned
   - total_files_pruned: total_files_pruned

Response Example
----------------

.. code-block:: json

    {
        "total_files_pruned": 5,
        "total_bytes_pruned": 104857600
    }
