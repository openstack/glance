.. -*- rst -*-

.. note: You can get a 400 on a GET if you pass a request body
         (see router.py)

Image Schemas
*************

Gets a JSON-schema document that represents the various entities talked
about by the Images v2 API.

.. _images-schema:

Show images schema
~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/schemas/images

*(Since Images v2.0)*

Shows a JSON schema document that represents an *images* entity.

An images entity is a container of image entities.

The following schema is solely an example. Consider only the
response to the API call as authoritative.

Normal response codes: 200

Error response codes: 400, 401


Request
-------

This operation has no request parameters and does not accept a request body.


Response Example
----------------

.. literalinclude:: samples/schemas-images-list-response.json
   :language: json

.. _image-schema:

Show image schema
~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/schemas/image

*(Since Images v2.0)*

Shows a JSON schema document that represents an *image* entity.

The following schema is solely an example. Consider only the
response to the API call as authoritative.

Normal response codes: 200

Error response codes: 400, 401


Request
-------

This operation has no request parameters and does not accept a request body.


Response Example
----------------

.. literalinclude:: samples/schemas-image-show-response.json
   :language: json

.. _image-members-schema:

Show image members schema
~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/schemas/members

*(Since Images v2.1)*

Shows a JSON schema document that represents an *image members* entity.

An image members entity is a container of image member entities.

The following schema is solely an example. Consider only the
response to the API call as authoritative.

Normal response codes: 200

Error response codes: 400, 401


Request
-------

This operation has no request parameters and does not accept a request body.


Response Example
----------------

.. literalinclude:: samples/schemas-image-members-list-response.json
   :language: json

.. _image-member-schema:

Show image member schema
~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/schemas/member

*(Since Images v2.1)*

Shows a JSON schema document that represents an *image member* entity.

The following schema is solely an example. Consider only the
response to the API call as authoritative.

Normal response codes: 200

Error response codes: 400, 401


Request
-------

This operation has no request parameters and does not accept a request body.


Response Example
----------------

.. literalinclude:: samples/schemas-image-member-show-response.json
   :language: json
