..
      Copyright 2010 OpenStack, LLC
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

Image Registries
================

Image metadata made available through Glance can be stored in image
`registries`. Image registries are any web service that adheres to the
Glance REST-like API for image metadata.

Glance comes with a server program ``glance-registry`` that acts
as a reference implementation of a Glance Registry.

Please see the document :doc:`on Controlling Servers <controllingservers>`
for more information on starting up the Glance registry server that ships
with Glance.

Glance Registry API
-------------------

Any web service that publishes an API that conforms to the following
REST-like API specification can be used by Glance as a registry.

API in Summary
**************

The following is a brief description of the Glance API::

  GET     /images         Return brief information about public images
  GET     /images/detail  Return detailed information about public images
  GET     /images/<ID>    Return metadata about an image in HTTP headers
  POST    /images         Register metadata about a new image
  PUT     /images/<ID>    Update metadata about an existing image
  DELETE  /images/<ID>    Remove an image's metadata from the registry

Filtering Images Returned via ``GET /images`` and ``GET /images/detail``
------------------------------------------------------------------------

Both the ``GET /images`` and ``GET /images/detail`` requests take query
parameters that serve to filter the returned list of images. The following
list details these query parameters.

* ``name=NAME``

  Filters images having a ``name`` attribute matching ``NAME``.

* ``container_format=FORMAT``

  Filters images having a ``container_format`` attribute matching ``FORMAT``

  For more information, see :doc:`About Disk and Container Formats <formats>`

* ``disk_format=FORMAT``

  Filters images having a ``disk_format`` attribute matching ``FORMAT``

  For more information, see :doc:`About Disk and Container Formats <formats>`

* ``status=STATUS``

  Filters images having a ``status`` attribute matching ``STATUS``

  For more information, see :doc:`About Image Statuses <statuses>`

* ``size_min=BYTES``

  Filters images having a ``size`` attribute greater than or equal to ``BYTES``

* ``size_max=BYTES``

  Filters images having a ``size`` attribute less than or equal to ``BYTES``

These two resources also accept sort parameters:

* ``sort_key=KEY``

  Results will be ordered by the specified image attribute ``KEY``. Accepted
  values include ``id``, ``name``, ``status``, ``disk_format``,
  ``container_format``, ``size``, ``created_at`` (default) and ``updated_at``.

* ``sort_dir=DIR``

  Results will be sorted in the direction ``DIR``. Accepted values are ``asc``
  for ascending or ``desc`` (default) for descending.
  

``POST /images``
----------------

The body of the request will be a JSON-encoded set of data about
the image to add to the registry. It will be in the following format::

  {'image':
    {'id': <ID>|None,
     'name': <NAME>,
     'status': <STATUS>,
     'disk_format': <DISK_FORMAT>,
     'container_format': <CONTAINER_FORMAT>,
     'properties': [ ... ]
    }
  }

The request shall validate the following conditions and return a
``400 Bad request`` when any of the conditions are not met:

* ``status`` must be non-empty, and must be one of **active**, **saving**,
  **queued**, or **killed**

* ``disk_format`` must be non-empty, and must be one of **ari**, **aki**,
  **ami**, **raw**, **iso**, **vhd**, **vdi**, **qcow2**, or **vmdk**

* ``container_format`` must be non-empty, and must be on of **ari**,
  **aki**, **ami**, **bare**, or **ovf**

* If ``disk_format`` *or* ``container_format`` is **ari**, **aki**,
  **ami**, then *both* ``disk_format`` and ``container_format`` must be
  the same.

Examples
********

.. todo::  Complete examples for Glance registry API
