.. -*- rst -*-

Images
******


Create image
~~~~~~~~~~~~

.. rest_method::  POST /v1/images

Creates a metadata record of a virtual machine (VM) image and optionally
stores the image data.

Image metadata fields are passed as  HTTP headers prefixed with one of
the strings ``x-image-meta-`` or ``x-image-meta-property-``.  See the
API documentation for details.

If there is no request body, an image record will be created in status
``queued``.  This is called *reserving an image*.  The image data can be
uploaded later using the `Update image`_ call.

If image data will be uploaded as part of this request, then the following
image metadata must be included among the request headers:

- ``name``
- ``disk_format``
- ``container_format``

Additionally, if image data is uploaded as part of this request, the API
will return a 400 under the following circumstances:

- The ``x-image-meta-size`` header is present and the length in bytes of
  the request body does not match the value of this header.
- The ``x-image-meta-checksum`` header is present and MD5 checksum generated
  by the backend store while storing the data does not match the value of
  this header.

Normal response codes: 201

Error response codes: 400, 409


Request
-------

.. rest_parameters:: parameters.yaml

   - image data: createImage
   - x-image-meta-name: x-image-meta-name
   - x-image-meta-container_format: x-image-meta-container_format
   - x-image-meta-disk_format: x-image-meta-disk_format


Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

   - location: location
   - image: image-object


Response Example (create with data)
-----------------------------------

  ::

     HTTP/1.1 100 Continue

     HTTP/1.1 201 Created
     Content-Type: application/json
     Content-Length: 491
     Location: http://glance.example.com/v1/images/de2f2211-3ac7-4260-9142-41db0ecfb425
     Etag: 7b1b10607acc1319506185e7227ca30d
     X-Openstack-Request-Id: req-70adeab4-740c-4db3-a002-fd1559ecf40f
     Date: Tue, 10 May 2016 21:41:41 GMT

.. literalinclude:: samples/images-create-with-data-response.json
   :language: json


Response Example (reserve an image)
-----------------------------------

This is an extreme example of reserving an image.  It was created by a POST
with no headers specified and no data passed.  Here's the response:

  ::

     HTTP/1.1 201 Created
     Content-Type: application/json
     Content-Length: 447
     Location: http://glance.example.com/v1/images/6b3ecfca-d445-4946-a8d1-c4938352b251
     X-Openstack-Request-Id: req-db1ff3c7-3d4f-451f-9ef1-c414343f809d
     Date: Tue, 10 May 2016 21:35:14 GMT

.. literalinclude:: samples/images-create-reserve-response.json
   :language: json



List images
~~~~~~~~~~~

.. rest_method::  GET /v1/images

Lists all VM images available to the user making the call.  This list will
include all public images, any images owned by the requestor, and any images
shared with the requestor.

Various query filters can be applied to the URL to restrict the content of
the response.

Normal response codes: 200

Error response codes: 400, 403

.. note:: need to add info about sorting and pagination

Request
-------

.. rest_parameters:: parameters.yaml

   - name: name-in-query
   - container_format: container_format-in-query
   - disk_format: disk_format-in-query
   - status: status-in-query
   - size_min: size_min
   - size_max: size_max
   - changes-since: changes-since


Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

   - images: images-list


Response Example
----------------

.. literalinclude:: samples/images-list-response.json
   :language: json


List images with details
~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1/images/detail

Lists all available images with details.

Various query filters can be applied to the URL to restrict the content of
the response.

Normal response codes: 200

Error response codes: 400, 403

.. note:: need to add info about sorting and pagination


Request
-------

.. rest_parameters:: parameters.yaml

   - name: name-in-query
   - container_format: container_format-in-query
   - disk_format: disk_format-in-query
   - status: status-in-query
   - size_min: size_min
   - size_max: size_max
   - changes-since: changes-since


Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

   - images: images-detail-list
   - previous: previous
   - next: next


Response Example
----------------

.. literalinclude:: samples/images-list-details-response.json
   :language: json


Update image
~~~~~~~~~~~~

.. rest_method::  PUT /v1/images/{image_id}

Updates the metadata for an image or uploads an image file.

Image metadata is updated by passing HTTP headers prefixed with one of the
strings ``x-image-meta-`` or ``x-image-meta-property-``.  See the API
documentation for details.

If the image is in ``queued`` status, image data may be added by
including it in the request body.  Otherwise, attempting to add data
will result in a 409 Conflict response.

If the request contains a body, the API will return a 400 under the following
circumstances:

- The ``x-image-meta-size`` header is present and the length in bytes of
  the request body does not match the value of this header.
- The ``x-image-meta-checksum`` header is present and MD5 checksum generated
  by the backend store while storing the data does not match the value of
  this header.

Normal response codes: 200

Error response codes: 400, 404, 409


Request
-------

.. rest_parameters:: parameters.yaml

   - image_id: image_id-in-path


Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

   - image: image-object



Response Example
----------------

.. literalinclude:: samples/image-update-response.json
   :language: json


Show image details and image data
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1/images/{image_id}

Returns the image metadata as headers; the image data is returned in the
body of the response.

Standard image properties are returned in headers prefixed by
``x-image-meta-`` (for example, ``x-image-meta-name``).  Custom image
properties are returned in headers prefixed by the string
``x-image-meta-property-`` (for example, ``x-image-meta-property-foo``).

Normal response codes: 200

Error response codes: 404, 403


Request
-------

.. rest_parameters:: parameters.yaml

   - image_id: image_id-in-path



Show image metadata
~~~~~~~~~~~~~~~~~~~

.. rest_method::  HEAD /v1/images/{image_id}

Returns the image metadata information as response headers.

The Image system does not return a response body for the HEAD
operation.

If the request succeeds, the operation returns the ``200`` response
code.

Normal response codes: 200

Error response codes: 404, 409


Request
-------

.. rest_parameters:: parameters.yaml

   - image_id: image_id-in-path


Response Example
----------------

  ::

     X-Image-Meta-Checksum: 8a40c862b5735975d82605c1dd395796
     X-Image-Meta-Container_format: aki
     X-Image-Meta-Created_at: 2016-01-06T03:22:20.000000
     X-Image-Meta-Deleted: false
     X-Image-Meta-Disk_format: aki
     X-Image-Meta-Id: 03bc0a8b-659c-4de9-b6bd-13c6e86e6455
     X-Image-Meta-Is_public: true
     X-Image-Meta-Min_disk: 0
     X-Image-Meta-Min_ram: 0
     X-Image-Meta-Name: cirros-0.3.4-x86_64-uec-kernel
     X-Image-Meta-Owner: 13cc6052265b41529e2fd0fc461fa8ef
     X-Image-Meta-Protected: false
     X-Image-Meta-Size: 4979632
     X-Image-Meta-Status: deactivated
     X-Image-Meta-Updated_at: 2016-02-25T03:02:05.000000
     X-Openstack-Request-Id: req-d5208320-28ed-4c22-b628-12dc6456d983


Delete image
~~~~~~~~~~~~

.. rest_method::  DELETE /v1/images/{image_id}

Deletes an image.

Normal response codes: 204

Error response codes: 404, 403


Request
-------

.. rest_parameters:: parameters.yaml

   - image_id: image_id-in-path
