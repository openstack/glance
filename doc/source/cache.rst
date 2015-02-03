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

Prefetching Images into the Image Cache
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Some installations have base (sometimes called "golden") images that are
very commonly used to boot virtual machines. When spinning up a new API
server, administrators may wish to prefetch these image files into the
local image cache to ensure that reads of those popular image files come
from a local cache.

To queue an image for prefetching, you can use one of the following methods:

 * If the ``cache_manage`` middleware is enabled in the application pipeline,
   you may call ``PUT /queued-images/<IMAGE_ID>`` to queue the image with
   identifier ``<IMAGE_ID>``

   Alternately, you can use the ``glance-cache-manage`` program to queue the
   image. This program may be run from a different host than the host
   containing the image cache. Example usage::

     $> glance-cache-manage --host=<HOST> queue-image <IMAGE_ID>

   This will queue the image with identifier ``<IMAGE_ID>`` for prefetching

Once you have queued the images you wish to prefetch, call the
``glance-cache-prefetcher`` executable, which will prefetch all queued images
concurrently, logging the results of the fetch for each image.

Finding Which Images are in the Image Cache
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You can find out which images are in the image cache using one of the
following methods:

  * If the ``cachemanage`` middleware is enabled in the application pipeline,
    you may call ``GET /cached-images`` to see a JSON-serialized list of
    mappings that show cached images, the number of cache hits on each image,
    the size of the image, and the times they were last accessed.

    Alternately, you can use the ``glance-cache-manage`` program. This program
    may be run from a different host than the host containing the image cache.
    Example usage::

    $> glance-cache-manage --host=<HOST> list-cached

  * You can issue the following call on \*nix systems (on the host that contains
    the image cache)::

      $> ls -lhR $IMAGE_CACHE_DIR

    where ``$IMAGE_CACHE_DIR`` is the value of the ``image_cache_dir``
    configuration variable.

    Note that the image's cache hit is not shown using this method.

Manually Removing Images from the Image Cache
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If the ``cachemanage`` middleware is enabled, you may call
``DELETE /cached-images/<IMAGE_ID>`` to remove the image file for image
with identifier ``<IMAGE_ID>`` from the cache.

Alternately, you can use the ``glance-cache-manage`` program. Example usage::

  $> glance-cache-manage --host=<HOST> delete-cached-image <IMAGE_ID>
