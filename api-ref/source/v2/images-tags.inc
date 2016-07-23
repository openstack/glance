.. -*- rst -*-

Image tags
**********

Adds and deletes image tags.

Image tags may also be modfied by the :ref:`v2-image-update` call.


Add image tag
~~~~~~~~~~~~~

.. rest_method::  PUT /v2/images/{image_id}/tags/{tag}

Adds a tag to an image.
*(Since Image API v2.0)*

Normal response codes: 204

Error response codes: 400, 401, 403, 404, 413


Request
-------

.. rest_parameters:: images-parameters.yaml

   - image_id: image_id-in-path
   - tag: tag-in-path


Delete image tag
~~~~~~~~~~~~~~~~

.. rest_method::  DELETE /v2/images/{image_id}/tags/{tag}

Deletes a tag from an image.
*(Since Image API v2.0)*

Normal response codes: 204

Error response codes: 400, 401, 403, 404


Request
-------

.. rest_parameters:: images-parameters.yaml

   - image_id: image_id-in-path
   - tag: tag-in-path
