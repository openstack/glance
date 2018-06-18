.. -*- rst -*-

.. _image-data:

Image data
**********

Uploads and downloads raw image data.

*These operations may be restricted to administrators.  Consult your cloud
operator's documentation for details.*


Upload binary image data
~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  PUT /v2/images/{image_id}/file

Uploads binary image data.
*(Since Image API v2.0)*

Set the ``Content-Type`` request header to ``application/octet-stream``.

A multiple store backend support is introduced in the Rocky release
as a part of the EXPERIMENTAL Image API v2.8.

Beginning with API version 2.8, an optional ``X-Image-Meta-Store``
header may be added to the request.  When present, the image data will be
placed into the backing store whose identifier is the value of this
header.  If the store identifier specified is not recognized, a 400 (Bad
Request) response is returned.  When the header is not present, the image
data is placed into the default backing store.

.. note:: The Multi Store feature is introduced as EXPERIMENTAL in Rocky and
          its use in production systems is currently **not supported**.
          However we encourage people to use this feature for testing
          purposes and report the issues so that we can make it stable and
          fully supported in Stein release.

* Store identifiers are site-specific.  Use the :ref:`Store
  Discovery <store-discovery-call>` call to determine what
  stores are available in a particular cloud.
* The default store may be determined from the :ref:`Store
  Discovery <store-discovery-call>` response.
* A default store is always defined, so if you do not have a need
  to use a particular store, simply omit this header and the default store
  will be used.
* For API versions before version 2.8, this header is silently
  ignored.

Example call:

::

   curl -i -X PUT -H "X-Auth-Token: $token" \
      -H "X-Image-Meta-Store: {store_identifier}" \
      -H "Content-Type: application/octet-stream" \
      -d @/home/glance/ubuntu-12.10.qcow2 \
      $image_url/v2/images/{image_id}/file

**Preconditions**

Before you can store binary image data, you must meet the following
preconditions:

- The image must exist.

- You must set the disk and container formats in the image.

- The image status must be ``queued``.

- Your image storage quota must be sufficient.

- The size of the data that you want to store must not exceed the
  size that the OpenStack Image service allows.

**Synchronous Postconditions**

- With correct permissions, you can see the image status as
  ``active`` through API calls.

- With correct access, you can see the stored data in the storage
  system that the OpenStack Image Service manages.

**Troubleshooting**

- If you cannot store the data, either your request lacks required
  information or you exceeded your allotted quota. Ensure that you
  meet the preconditions and run the request again. If the request
  fails again, review your API request.

- The storage back ends for storing the data must have enough free
  storage space to accommodate the size of the data.

Normal response codes: 204

Error response codes: 400, 401, 403, 404, 409, 410, 413, 415, 503


Request
-------

.. rest_parameters:: images-parameters.yaml

   - Content-type: Content-Type-data
   - X-Image-Meta-Store: store-header
   - image_id: image_id-in-path


Download binary image data
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/images/{image_id}/file

Downloads binary image data.
*(Since Image API v2.0)*

Example call: ``curl -i -X GET -H "X-Auth-Token: $token"
$image_url/v2/images/{image_id}/file``

The response body contains the raw binary data that represents the
actual virtual disk. The ``Content-Type`` header contains the
``application/octet-stream`` value. The ``Content-MD5`` header
contains an MD5 checksum of the image data. Use this checksum to
verify the integrity of the image data.

**Preconditions**

- The image must exist.

**Synchronous Postconditions**

- You can download the binary image data in your machine if the
  image has image data.

- If image data exists, the call returns the HTTP ``200`` response code for a
  full image download request.

- If image data exists, the call returns the HTTP ``206`` response code for a
  partial download request.

- If no image data exists, the call returns the HTTP ``204`` (No Content)
  response code.

- If no image record exists, the call returns the HTTP ``404`` response code
  for an attempted full image download request.

- For an unsatisfiable partial download request, the call returns the HTTP
  ``416`` response code.

Normal response codes: 200, 204, 206

Error response codes: 400, 403, 404, 416


Request
-------

.. rest_parameters:: images-parameters.yaml

   - image_id: image_id-in-path
   - Range: Range

Response
--------
.. rest_parameters:: images-parameters.yaml

   - Content-Type: Content-Type-data-response
   - Content-Md5: Content-Md5
   - Content-Length: Content-Length
   - Content-Range: Content-Range
