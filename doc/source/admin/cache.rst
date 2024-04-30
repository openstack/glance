..
      Copyright 2011 OpenStack Foundation
      All Rights Reserved.

      Licensed under the Apache License, Version 2.0 (the "License"); you may
      not use this file except in compliance with the License. You may obtain
      a copy of the License at

          http://www.apache.org/licenses/LICENSE-2.0

      Unless required by applicable law or agreed to in writing, software
      distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
      WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
      License for the specific language governing permissions and limitations
      under the License.

.. _image-cache:

The Glance Image Cache
======================

The Glance API server may be configured to have an optional local image cache.
A local image cache stores a copy of image files, essentially enabling multiple
API servers to serve the same image file, resulting in an increase in
scalability due to an increased number of endpoints serving an image file.

This local image cache is transparent to the end user -- in other words, the
end user doesn't know that the Glance API is streaming an image file from
its local cache or from the actual backend storage system.

Managing the Glance Image Cache
-------------------------------

While image files are automatically placed in the image cache on successful
requests to ``GET /images/<IMAGE_ID>``, the image cache is not automatically
managed. Here, we describe the basics of how to manage the local image cache
on Glance API servers and how to automate this cache management.

Configuration options for the Image Cache
-----------------------------------------

The Glance cache uses two files: one for configuring the server and
another for the utilities. The ``glance-api.conf`` is for the server
and the ``glance-cache.conf`` is for the utilities.

The following options are in both configuration files. These need the
same values otherwise the cache will potentially run into problems.

- ``image_cache_dir`` This is the base directory where Glance stores
  the cache data (Required to be set, as does not have a default).
- ``image_cache_sqlite_db`` Path to the sqlite file database that will
  be used for cache management. This is a relative path from the
  ``image_cache_dir`` directory (Default:``cache.db``).
- ``image_cache_driver`` The driver used for cache management.
  (Default:``sqlite``)
- ``image_cache_max_size`` The size when the glance-cache-pruner will
  remove the oldest images, to reduce the bytes until under this value.
  (Default:``10 GB``)
- ``image_cache_stall_time`` The amount of time an incomplete image will
  stay in the cache, after this the incomplete image will be deleted.
  (Default:``1 day``)

The following values are the ones that are specific to the
``glance-cache.conf`` and are only required for the prefetcher to run
correctly.

- ``filesystem_store_datadir`` This is used if using the filesystem
  store, points to where the data is kept.
- ``filesystem_store_datadirs`` This is used to point to multiple
  filesystem stores.

Controlling the Growth of the Image Cache
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The image cache has a configurable maximum size (the ``image_cache_max_size``
configuration file option). The ``image_cache_max_size`` is an upper limit
beyond which pruner, if running, starts cleaning the images cache.
However, when images are successfully returned from a call to
``GET /images/<IMAGE_ID>``, the image cache automatically writes the image
file to its cache, regardless of whether the resulting write would make the
image cache's size exceed the value of ``image_cache_max_size``.
In order to keep the image cache at or below this maximum cache size,
you need to run the ``glance-cache-pruner`` executable.

The recommended practice is to use ``cron`` to fire ``glance-cache-pruner``
at a regular interval.

Cleaning the Image Cache
~~~~~~~~~~~~~~~~~~~~~~~~

Over time, the image cache can accumulate image files that are either in
a stalled or invalid state. Stalled image files are the result of an image
cache write failing to complete. Invalid image files are the result of an
image file not being written properly to disk.

To remove these types of files, you run the ``glance-cache-cleaner``
executable.

The recommended practice is to use ``cron`` to fire ``glance-cache-cleaner``
at a semi-regular interval.

Controlling Image Cache using V2 API
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In Yoga, Glance API has added new APIs for managing cache
related operations. In Zed, Glance has removed support of ``cache_images``
periodic job which was used to prefetch all queued images concurrently,
logging the results of the fetch for each image. Instead the image can be
immediately cached once it is queued for caching. You can use below API
calls to control the cache related operations.

To queue an image for immediate caching, you can use one of the following
methods:

* You can call ``PUT /cache/<IMAGE_ID>`` to queue the image for immediate
  caching with identifier ``<IMAGE_ID>``

* Alternately, you can use the ``cache-queue`` command of glance client to
  queue the image for immediate caching.

    $ glance cache-queue <IMAGE_ID>

  This will queue the image with identifier ``<IMAGE_ID>`` for immediate
  caching.

To find out which images are in the image cache use one of the
following methods:

* You can call ``GET /cache`` to see a JSON-serialized list of
  mappings that show cached images, the number of cache hits on each image,
  the size of the image, and the times they were last accessed as well as
  images which are queued for caching.

* Alternately, you can use the ``cache-list`` command of glance
  client. Example usage::

   $ glance cache-list

To delete images which are already cached or queued for caching use one of
the following methods:

* You can call ``DELETE /cache/<IMAGE_ID>`` to remove the image file for image
  with identifier ``<IMAGE_ID>`` from the cache or queued state.

* Alternately, you can use the ``cache-delete`` command of glance
  client. Example usage::

  $ glance cache-delete <IMAGE_ID>

* You can also call ``DELETE /cache`` with header
  ``x-image-cache-clear-target`` to delete either only cached images or
  only queued images or both. Possible values for header are ``cache``,
  ``queue``, ``both``.

* Alternately, you can use the ``cache-clear`` command of glance client
  to delete only cached images or only queued images or both. Example usage::

  $ glance cache-clear (default target is ``both``)
  $ glance cache-clear --target cached
  $ glance cache-clear --target queued

* In Glance, image cache is local to each node, hence cache operations
  must be performed on each node locally. If OpenStack cloud is deployed with
  HA (3/5/7 controllers) then while running the cache related operations it is
  necessary to specify the HOST address using -H option.
  Example usage::

   $ glance --host=<HOST> cache-list

Finding Which Images are in the Image Cache with glance-cache-manage
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You can find out which images are in the image cache using one of the
following methods:

* If the ``cachemanage`` middleware is enabled in the application pipeline,
  you may call ``GET /cached-images`` to see a JSON-serialized list of
  mappings that show cached images, the number of cache hits on each image,
  the size of the image, and the times they were last accessed.

* Alternately, you can use the ``glance-cache-manage`` program. This program
  may be run from a different host than the host containing the image cache.
  Example usage::

   $ glance-cache-manage --host=<HOST> list-cached

* In Glance, image cache is local to each node, hence image cache management
  must be performed on each node locally. If OpenStack cloud is deployed with
  HA (3/5/7 controllers) then while running the cache management it is
  necessary to specify the HOST address using -H option.
  Example usage::

   $ glance-cache-manage --host=<HOST> list-cached

* You can issue the following call on \*nix systems (on the host that contains
  the image cache)::

    $ ls -lhR $IMAGE_CACHE_DIR

  where ``$IMAGE_CACHE_DIR`` is the value of the ``image_cache_dir``
  configuration variable.

  Note that the image's cache hit is not shown using this method.

Manually Removing Images from the Image Cache with glance-cache-manage
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If the ``cachemanage`` middleware is enabled, you may call
``DELETE /cached-images/<IMAGE_ID>`` to remove the image file for image
with identifier ``<IMAGE_ID>`` from the cache.

Alternately, you can use the ``glance-cache-manage`` program. Example usage::

  $ glance-cache-manage --host=<HOST> delete-cached-image <IMAGE_ID>

