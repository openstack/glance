.. -*- rst -*-

.. _image-import-process:

Interoperable image import
**************************

An interoperable image import process is introduced in the Image API v2.6.

Use the :ref:`API versions call <versions-call>` to determine what API versions
are available in your cloud.

General information
~~~~~~~~~~~~~~~~~~~

The exact workflow you use for interoperable image import depends upon
the import methods available in the cloud in which you want to import
an image.  Each of these methods is well defined (which is what makes
this process interoperable among different OpenStack clouds).

Two import methods are defined, ``glance-direct`` and ``web-download``.

.. note::

   Use the :ref:`Import Method Discovery <import-discovery-call>` call
   to determine what import methods are available in the cloud to which
   you wish to import an image.

The first step in each interoperable image import method is the same: you must
create an image record.  This will give you an image id to work with.  This
image id is how the OpenStack Image service will understand that the other
calls you make are referring to this particular image.

Thus, the first step is:

1.  Create an image record using the :ref:`Image Create <image-create>`
    API call.  You must do this first so that you have an image id to
    work with for the other calls.

    In a cloud in which interoperable image import is enabled, the
    :ref:`Image Create <image-create>` response will include a
    ``OpenStack-image-import-methods`` header listing the types of
    import methods available in that cloud.  Alternatively, these
    methods may be determined independently of creating an image by making
    the :ref:`Import Method Discovery <import-discovery-call>` call.

The glance-direct import method
-------------------------------

The ``glance-direct`` workflow has **three** parts:

1.  Create an image record as described above.

2.  Upload the image data to a staging area using the :ref:`Image Stage
    <image-stage-call>` API call.  Note that this image data is not
    accessible until after the third step has successfully completed.

3.  Issue the :ref:`Image Import <image-import-call>` call to complete
    the import process.  You will specify that you are using the
    ``glance-direct`` import method in the body of the import call.

The web-download import method
------------------------------

The ``web-download`` workflow has **two** parts:

1.  Create an image record as described above.

2.  Issue the :ref:`Image Import <image-import-call>` call to complete
    the import process.  You will specify that you are using the
    ``web-download`` import method in the body of the import call.

.. _image-stage-call:

Stage binary image data
~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  PUT /v2/images/{image_id}/stage

Places the binary image data in a staging area.  It is not stored in
the storage backend and is not accessible for download until after
the :ref:`Image Import <image-import-call>` call is made.
*(Since Image API v2.6)*

Set the ``Content-Type`` request header to ``application/octet-stream``.

Example call:

::

   curl -i -X PUT -H "X-Auth-Token: $token" \
      -H "Content-Type: application/octet-stream" \
      -d @/home/glance/my.to-import.qcow2 \
      $image_url/v2/images/{image_id}/stage

**Preconditions**

Before you can stage binary image data, you must meet the following
preconditions:

- The image record must exist.

- The image status must be ``queued``.

- Your image storage quota must be sufficient.

- The size of the data that you want to store must not exceed the
  size that the OpenStack Image service allows.

**Synchronous Postconditions**

- With correct permissions, you can see the image status as
  ``uploading`` through API calls.

**Troubleshooting**

- If you cannot store the data, either your request lacks required
  information or you exceeded your allotted quota. Ensure that you
  meet the preconditions and run the request again. If the request
  fails again, review your API request.

- The storage back ends for storing the data must have enough free
  storage space to accommodate the size of the data.

Normal response codes: 204

Error response codes: 400, 401, 403, 404, 405, 409, 410, 413, 415, 503

If the image import process is not enabled in your cloud, this request
will result in a 404 response code with an appropriate message.


Request
-------

.. rest_parameters:: images-parameters.yaml

   - Content-type: Content-Type-data
   - image_id: image_id-in-path


.. _image-import-call:

Import an image
~~~~~~~~~~~~~~~

.. rest_method::  POST /v2/images/{image_id}/import

Signals the Image Service to complete the image import workflow
by processing data that has been made available to the OpenStack
image service.
*(Since Image API v2.6)*

In the ``glance-direct`` workflow, the data has been made available to the
Image service via the :ref:`Stage binary image data <image-stage-call>` API
call.

In the ``web-download`` workflow, the data is made available to the Image
service by being posted to an accessible location with a URL that you know.

Example call: ``curl -i -X POST -H "X-Auth-Token: $token"
$image_url/v2/images/{image_id}/import``

The JSON request body specifies what import method you wish to use
for this image request.

**Preconditions**

Before you can complete the interoperable image import workflow, you must meet
the following preconditions:

- The image record must exist.

- You must set the disk and container formats in the image record.  (This can
  be done at the time of image creation, or you can make the :ref:`Image Update
  <v2-image-update>` API call.

- Your image storage quota must be sufficient.

- The size of the data that you want to store must not exceed the
  size that the OpenStack Image service allows.

**Additional Preconditions**

If you are using the ``glance-direct`` import method:

- The image status must be ``uploading``.  (This indicates that the image
  data has been uploaded to the stage.)

- The body of your request must indicate that you are using the
  ``glance-direct`` import method.

If you are using the ``web-download`` import method:

- The image status must be ``queued``.  (This indicates that no image data
  has yet been associated with the image.)

- The body of your request must indicate that you are using the
  ``web-download`` import method, and it must contain the URL at which the data
  is to be found.

  .. note::
     The acceptable set of URLs for the ``web-download`` import method may be
     restricted in a particular cloud.  Consult the cloud's local documentation
     for details.

**Synchronous Postconditions**

- With correct permissions, you can see the image status as
  ``importing`` through API calls.  (Be aware, however, that if the import
  process completes before you make the API call, the image may already
  show as ``active``.)

Normal response codes: 202

Error response codes: 400, 401, 403, 404, 405, 409, 410, 413, 415, 503

If the image import process is not enabled in your cloud, this request
will result in a 404 response code with an appropriate message.


Request
-------

.. rest_parameters:: images-parameters.yaml

   - Content-type: Content-Type-json
   - image_id: image_id-in-path
   - method: method-in-request

Request Example - glance-direct import method
---------------------------------------------

.. literalinclude:: samples/image-import-g-d-request.json
   :language: json

Request Example - web-download import method
--------------------------------------------

.. literalinclude:: samples/image-import-w-d-request.json
   :language: json


.. _import-discovery-call:

Import methods and values discovery
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/info/import

Returns information concerning the constraints around image import in
the cloud in which the call is made, for example, supported container
formats, supported disk formats, maximum image size, etc.  This call
contains a ``import-methods`` field consisting of an array of string
identifiers indicating what import methods are supported in the cloud
in which the call is made.
*(Since Image API v2.6)*

.. note::
   In the Image API v2.6, this discovery call contains
   **only** the ``import-methods`` field.

Normal response codes: 200

Error response codes: 400, 401, 403


Request
-------

There are no request parameters.

This call does not allow a request body.


Response Parameters
-------------------

.. rest_parameters:: images-parameters.yaml

   - import-methods: import-methods


Response Example
----------------

.. literalinclude:: samples/image-info-import-response.json
   :language: json
