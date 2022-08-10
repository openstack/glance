.. -*- rst -*-

Images
******

Creates, lists, shows, updates, deletes, and performs other operations on
images.

General information
~~~~~~~~~~~~~~~~~~~

**Images**

An *image* is represented by a JSON Object, that is, as a set of key:value
pairs.  Some of these keys are *base properties* that are managed by the
Image service. The remainder are properties put on the image by the operator
or the image owner.

.. note::
   Another common term for "image properties" is "image metadata" because
   what we're talking about here are properties that *describe* the image
   data that can be consumed by various OpenStack services (for example,
   by the Compute service to boot a server, or by the Volume service to
   create a bootable volume).

Here's some important information about image properties:

* The base properties are always included in the image representation.  A
  base property that doesn't have a value is displayed with its value set
  to ``null`` (that is, the JSON null data type).

* Additional properties, whose value is always a string data type, are
  only included in the response if they have a value.

* Since version 2.2, the Images API allows an operator to configure
  *property protections*, by which the create, read, update, and delete
  operations on specific image properties may be restricted to particular
  user roles.  Consult the documentation of your cloud operator for details.

* Arguably the most important properties of an image are its *id*, which
  uniquely identifies the image, its *status*, which indicates the current
  situation of the image (which, in turn, indicates what you can do with the
  image), and its *visibility*, which indicates who has access to the image.

* Some properties are used internally by glance and API users are not
  allowed to set or modify them. Examples of these are *id*, *status*,
  and anything prefixed with the *os_glance* namespace.

.. note::
   In addition to image properties, there's usually a data payload that is
   accessible via the image.  In order to give image consumers some guarantees
   about the data payload (for example, that the data associated with image
   ``06b73bc7-9d62-4d37-ad95-d4708f37734f`` is the same today as it was when
   you used it to boot a server yesterday) the Image service controls
   particular image properties (for example, ``checksum``) that cannot be
   modified.  A shorthand way to refer to the way the image data payload is
   related to its representation as an *image* in the Images API is to say that
   "images are immutable".  (This obviously applies to the image data payload,
   not its representation in the Image service.)  See the :ref:`Image Data
   <image-data>` section of this document for more information.

**Image status**

The possible status values for images are presented in the following table.

.. list-table::
    :header-rows: 1

    * - Status
      - Description
    * - queued
      - The Image service reserved an image ID for the image in the catalog
        but did not yet upload any image data.
    * - saving
      - The Image service is in the process of saving the raw data for
        the image into the backing store.
    * - active
      - The image is active and ready for consumption in the Image service.
    * - killed
      - An image data upload error occurred.
    * - deleted
      - The Image service retains information about the image but the image is
        no longer available for use.
    * - pending_delete
      - Similar to the ``deleted`` status.  An image in this state is not
        recoverable.
    * - deactivated
      - The image data is not available for use.
    * - uploading
      - Data has been staged as part of the interoperable image import process.
        It is not yet available for use.
        *(Since Image API 2.6)*
    * - importing
      - The image data is being processed as part of the interoperable image
        import process, but is not yet available for use.
        *(Since Image API 2.6)*

**Image visibility**

The possible values for image visibility are presented in the following table.

.. list-table::
    :header-rows: 1

    * - Visibility
      - Description
    * - ``public``
      - Any user may read the image and its data payload.  Additionally, the
        image appears in the default image list of all users.
    * - ``community``
      - Any user may read the image and its data payload, but the image does
        *not* appear in the default image list of any user other than the
        owner.

        *(This visibility value was added in the Image API v2.5)*
    * - ``shared``
      - An image must have this visibility in order for *image members* to be
        added to it.  Only the owner and the specific image members who have
        been added to the image may read the image or its data payload.

        The image appears in the default image list of the owner.  It also
        appears in the default image list of members who have *accepted* the
        image.  See the :ref:`Image Sharing <image-sharing>` section of this
        document for more information.

        If you do not specify a visibility value when you create an image,
        it is assigned this visibility by default.  Non-owners, however, will
        not have access to the image until they are added as image members.

        *(This visibility value was added in the Image API v2.5)*
    * - ``private``
      - Only the owner image may read the image or its data payload.
        Additionally, the image appears in the owner's default image list.

        *Since Image API v2.5, an image with private visibility cannot have
        members added to it.*

Note that the descriptions above discuss *read* access to images.  Only the
image owner (or an administrator) has write access to image properties and the
image data payload.  Further, in order to promise image immutability, the Image
service will allow even the owner (or an administrator) only write-once
permissions to specific image properties and the image data payload.

.. _image-create:

Create image
~~~~~~~~~~~~

.. rest_method::  POST /v2/images

Creates a catalog record for an operating system disk image.
*(Since Image API v2.0)*

The ``Location`` response header contains the URI for the image.

A multiple store backend support is introduced in the Rocky release
as a part of the EXPERIMENTAL Image API v2.8. Since Image API v2.8 a
new header ``OpenStack-image-store-ids`` which contains the list of
available stores will be included in response. This header is only
included if multiple backend stores are supported.

The response body contains the new image entity.

Synchronous Postconditions

- With correct permissions, you can see the image status as
  ``queued`` through API calls.

Normal response codes: 201

Error response codes: 400, 401, 403, 409, 413, 415


Request
-------

.. rest_parameters:: images-parameters.yaml

   - container_format: container_format-in-request
   - disk_format: disk_format-in-request
   - id: id-in-request
   - min_disk: min_disk-in-request
   - min_ram: min_ram-in-request
   - name: name-in-request
   - protected: protected-in-request
   - tags: tags-in-request
   - visibility: visibility-in-request

Additionally, you may include additional properties specified as key:value
pairs, where the value must be a string data type.  Keys are limited
to 255 chars in length.  Available key names may be limited by the cloud's
property protection configuration and reserved namespaces like *os_glance*.

Request Example
---------------

.. literalinclude:: samples/image-create-request.json
   :language: json

Response Parameters
-------------------

.. rest_parameters:: images-parameters.yaml

   - Location: Location
   - OpenStack-image-import-methods: import-header
   - OpenStack-image-store-ids: stores-header
   - checksum: checksum
   - container_format: container_format
   - created_at: created_at
   - disk_format: disk_format
   - file: file
   - id: id
   - min_disk: min_disk
   - min_ram: min_ram
   - name: name
   - os_hash_algo: os_hash_algo
   - os_hash_value: os_hash_value
   - os_hidden: os_hidden
   - owner: owner
   - protected: protected
   - schema: schema-image
   - self: self
   - size: size
   - status: status
   - tags: tags
   - updated_at: updated_at
   - virtual_size: virtual_size
   - visibility: visibility
   - direct_url: direct_url
   - locations: locations

The response may also include additional properties specified as key:value
pairs if additional properties were specified in the request.

Response Example
----------------

.. literalinclude:: samples/image-create-response.json
   :language: json


Show image
~~~~~~~~~~

.. rest_method::  GET /v2/images/{image_id}

Shows details for an image.
*(Since Image API v2.0)*

The response body contains a single image entity.

Preconditions

- The image must exist.

Normal response codes: 200

Error response codes: 400, 401, 403, 404


Request
-------

.. rest_parameters:: images-parameters.yaml

   - image_id: image_id-in-path


Response Parameters
-------------------

.. rest_parameters:: images-parameters.yaml

   - checksum: checksum
   - container_format: container_format
   - created_at: created_at
   - disk_format: disk_format
   - file: file
   - id: id
   - min_disk: min_disk
   - min_ram: min_ram
   - name: name
   - os_hash_algo: os_hash_algo
   - os_hash_value: os_hash_value
   - os_hidden: os_hidden
   - owner: owner
   - protected: protected
   - schema: schema-image
   - self: self
   - size: size
   - status: status
   - tags: tags
   - updated_at: updated_at
   - virtual_size: virtual_size
   - visibility: visibility
   - direct_url: direct_url
   - locations: locations

The response may also include additional properties specified as key:value
pairs if such properties have been added to the image by the owner or an
administrator.

Response Example
----------------

.. literalinclude:: samples/image-show-response.json
   :language: json


Show tasks associated with image
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/images/{image_id}/tasks

Shows tasks associated with an image.
*(Since Image API v2.12)*

The response body contains list of tasks, possibly empty, associated
with the specified image.

Preconditions

- The image must exist.

Normal response codes: 200

Error response codes: 404


Request
-------

.. rest_parameters:: images-parameters.yaml

   - image_id: image_id-in-path


Response Parameters
-------------------

.. rest_parameters:: images-parameters.yaml

   - tasks: tasks

Response Example
----------------

.. literalinclude:: samples/image-tasks-show-response.json
   :language: json


List images
~~~~~~~~~~~

.. rest_method::  GET /v2/images

Lists public virtual machine (VM) images.
*(Since Image API v2.0)*

**Pagination**

Returns a subset of the larger collection of images and a link that you can use
to get the next set of images. You should always check for the presence of a
``next`` link and use it as the URI in a subsequent HTTP GET request. You
should follow this pattern until a ``next`` link is no longer provided.

The ``next`` link preserves any query parameters that you send in your initial
request. You can use the ``first`` link to jump back to the first page of the
collection. If you prefer to paginate through images manually, use the
``limit`` and ``marker`` parameters.

**Query Filters**

The list operation accepts query parameters to filter the response.

A client can provide direct comparison filters by using most image attributes,
such as ``name=Ubuntu``, ``visibility=public``, and so on.

To filter using image tags, use the filter ``tag`` (note the singular).  To
filter on multiple tags, include each tag separately in the query.  For
example, to find images with the tag **ready**, include ``tag=ready`` in your
query string.  To find images tagged with **ready** and **approved**, include
``tag=ready&tag=approved`` in your query string.  (Note that only images
containing *both* tags will be included in the response.)

A client cannot use any ``link`` in the json-schema, such as self, file, or
schema, to filter the response.

You can list VM images that have a status of ``active``, ``queued``, or
``saving``.

**The** ``in`` **Operator**

As a convenience, you may specify several values for any of the following
fields by using the ``in`` operator:

* container_format
* disk_format
* id
* name
* status

For most of these, usage is straight forward.  For example, to list images
in queued or saving status, use:

``GET /v2/images?status=in:saving,queued``

To find images in a particular list of image IDs, use:

``GET /v2/images?id=in:3afb79c1-131a-4c38-a87c-bc4b801d14e6,2e011209-660f-44b5-baf2-2eb4babae53d``

Using the ``in`` operator with the ``name`` property of images can be a bit
trickier, depending upon how creatively you have named your images.  The
general rule is that if an image name contains a comma (``,``), you must
enclose the entire name in quotation marks (``"``).  As usual, you must URL
encode any characters that require it.

For example, to find images named ``glass, darkly`` or ``share me``, you would
use the following filter specification:

``GET v2/images?name=in:"glass,%20darkly",share%20me``

As with regular filtering by name, you must specify the complete name you are
looking for.  Thus, for example, the query string ``name=in:glass,share`` will
only match images with the exact name ``glass`` or the exact name ``share``.
It will not find an image named ``glass, darkly`` or an image named ``share
me``.

**Size Comparison Filters**

You can use the ``size_min`` and ``size_max`` query parameters to filter images
that are greater than or less than the image size.  The size, in bytes, is the
size of an image on disk.

For example, to filter the container to include only images that are from 1 to
4 MB, set the ``size_min`` query parameter to ``1048576`` and the ``size_max``
query parameter to ``4194304``.

.. _v2-comparison-ops:

**Time Comparison Filters**

You can use a *comparison operator* along with the ``created_at`` or
``updated_at`` fields to filter your results.  Specify the operator first, a
colon (``:``) as a separator, and then the time in `ISO 8601 Format
<https://en.wikipedia.org/wiki/ISO_8601>`_.  Available comparison operators
are:

.. list-table::
    :header-rows: 1

    * - Operator
      - Description
    * - ``gt``
      - Return results more recent than the specified time.
    * - ``gte``
      - Return any results matching the specified time and also any more recent
        results.
    * - ``eq``
      - Return any results matching the specified time exactly.
    * - ``neq``
      - Return any results that do not match the specified time.
    * - ``lt``
      - Return results older than the specified time.
    * - ``lte``
      - Return any results matching the specified time and also any older
        results.

For example:

.. code-block:: console

   GET v2/images?created_at=gt:2016-04-18T21:38:54Z

**Sorting**

You can use query parameters to sort the results of this operation.

- ``sort_key``. Sorts by an image attribute. Sorts in the natural
  sorting direction of the image attribute.

- ``sort_dir``. Sorts in a sort direction.

- ``sort``. Sorts by one or more sets of attribute and sort
  direction combinations. If you omit the sort direction in a set,
  the default is ``desc``.

To sort the response, use the ``sort_key`` and ``sort_dir`` query
parameters:

.. code-block:: console

   GET /v2/images?sort_key=name&sort_dir=asc&sort_key=status&sort_dir=desc

Alternatively, specify the ``sort`` query parameter:

.. code-block:: console

   GET /v2/images?sort=name:asc,status:desc

.. note::
    Although this call has been available since version 2.0 of this API,
    it has been enhanced from release to release.  The filtering and
    sorting functionality and syntax described above apply to the most
    recent release (Newton).  Not everything described above will be
    available in prior releases.

Normal response codes: 200

Error response codes: 400, 401, 403


Request
-------

.. rest_parameters:: images-parameters.yaml

   - limit: limit
   - marker: marker
   - name: name-in-query
   - owner: owner-in-query
   - protected: protected-in-query
   - status: status-in-query
   - tag: tag-in-query
   - visibility: visibility-in-query
   - os_hidden: os_hidden-in-query
   - member_status: member_status-in-query
   - size_max: size_max
   - size_min: size_min
   - created_at: created_at-in-query
   - updated_at: updated_at-in-query
   - sort_dir: sort_dir
   - sort_key: sort_key
   - sort: sort


Response Parameters
-------------------

.. rest_parameters:: images-parameters.yaml

   - images: images
   - first: first
   - next: next
   - schema: schema-images



Response Example
----------------

.. literalinclude:: samples/images-list-response.json
   :language: json


.. _v2-image-update:

Update image
~~~~~~~~~~~~

.. rest_method::  PATCH /v2/images/{image_id}

Updates an image.
*(Since Image API v2.0)*

Conceptually, you update an image record by patching the JSON representation of
the image, passing a request body conforming to one of the following media
types:

- ``application/openstack-images-v2.0-json-patch`` *(deprecated)*
- ``application/openstack-images-v2.1-json-patch`` *(since Image API v2.1)*

Attempting to make a PATCH call using some other media type will provoke a
response code of 415 (Unsupported media type).

The ``application/openstack-images-v2.1-json-patch`` media type provides a
useful and compatible subset of the functionality defined in JavaScript Object
Notation (JSON) Patch `RFC6902 <http://tools.ietf.org/html/rfc6902>`_, which
defines the ``application/json-patch+json`` media type.

.. note::
   The ``application/openstack-images-v2.0-json-patch`` media type is based on
   draft 4 of the standard. Its use is deprecated.

For information about the PATCH method and the available media types, see
`Image API v2 HTTP PATCH media types
<http://specs.openstack.org/openstack/glance-specs/specs/api/v2
/http-patch-image-api-v2.html>`_.

Attempting to modify some image properties will cause the entire request to
fail with a 403 (Forbidden) response code:

- An attempt to modify any of the "base" image properties that are managed by
  the Image Service.  These are the properties specified as read only in the
  :ref:`Image Schema <image-schema>`.

- An attempt to create or modify image properties for which you do not have
  permission to do so *(since Image API v2.2)*.  This depends upon how property
  protections are configured in the OpenStack cloud in which you are making the
  call.  Consult your cloud's documentation for details.

- An attempt to delete the only image location, or to replace the image
  locations with an empty list *(since Image API v2.4)*.

- An attempt to set or modify a property with a reserved name, such as
  anything prefixed with the *os_glance* namespace.

Attempting to add a location path to an image that is not in ``queued`` or
``active`` state will result in a 409 (Conflict) response code
*(since Image API v2.4)*.

Normal response codes: 200

Error response codes: 400, 401, 403, 404, 409, 413, 415


Request
-------

.. rest_parameters:: images-parameters.yaml

   - Content-Type: Content-Type-patch
   - image_id: image_id-in-path

The request body must conform to the
``application/openstack-images-v2.1-json-patch`` media type definition (see
above).


Request Example
---------------

.. literalinclude:: samples/image-update-request.json
   :language: json


Response Parameters
-------------------

.. rest_parameters:: images-parameters.yaml

   - checksum: checksum
   - container_format: container_format
   - created_at: created_at
   - disk_format: disk_format
   - file: file
   - id: id
   - min_disk: min_disk
   - min_ram: min_ram
   - name: name
   - owner: owner
   - os_hash_algo: os_hash_algo
   - os_hash_value: os_hash_value
   - os_hidden: os_hidden
   - protected: protected
   - schema: schema-image
   - self: self
   - size: size
   - status: status
   - tags: tags
   - updated_at: updated_at
   - visibility: visibility
   - direct_url: direct_url
   - locations: locations



Response Example
----------------

.. literalinclude:: samples/image-update-response.json
   :language: json


Delete image
~~~~~~~~~~~~

.. rest_method::  DELETE /v2/images/{image_id}

(Since Image API v2.0) Deletes an image.

You cannot delete images with the ``protected`` attribute set to
``true`` (boolean).

Preconditions

- You can delete an image in any status except ``deleted``.

- The ``protected`` attribute of the image cannot be ``true``.

- You have permission to perform image deletion under the configured image
  deletion policy.

Synchronous Postconditions

- The response is empty and returns the HTTP ``204`` response code.

- The API deletes the image from the images index.

- If the image has associated binary image data in the storage backend, the
  OpenStack Image service deletes the data.

Normal response codes: 204

Error response codes: 400, 401, 403, 404, 409


Request
-------

.. rest_parameters:: images-parameters.yaml

   - image_id: image_id-in-path


Deactivate image
~~~~~~~~~~~~~~~~

.. rest_method::  POST /v2/images/{image_id}/actions/deactivate

Deactivates an image.
*(Since Image API v2.3)*

By default, this operation is restricted to administrators only.

If you try to download a deactivated image, you will receive a 403 (Forbidden)
response code.  Additionally, only administrative users can view image
locations for deactivated images.

The deactivate operation returns an error if the image status is
not ``active`` or ``deactivated``.

Preconditions

- The image must exist.

Normal response codes: 204

Error response codes: 400, 403, 404


Request
-------

.. rest_parameters:: images-parameters.yaml

   - image_id: image_id-in-path


Reactivate image
~~~~~~~~~~~~~~~~

.. rest_method::  POST /v2/images/{image_id}/actions/reactivate

Reactivates an image.
*(Since Image API v2.3)*

By default, this operation is restricted to administrators only.

The reactivate operation returns an error if the image status is
not ``active`` or ``deactivated``.

Preconditions

- The image must exist.

Normal response codes: 204

Error response codes: 400, 403, 404


Request
-------

.. rest_parameters:: images-parameters.yaml

   - image_id: image_id-in-path
