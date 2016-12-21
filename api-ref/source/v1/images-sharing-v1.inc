.. -*- rst -*-

Sharing
*******

Image sharing provides a means for one tenant (the "producer") to make a
private image available to other tenants (the "consumers").  This ability
can unfortunately be misused to spam tenants' image lists, so these calls
may not be exposed in some deployments.  (The Images v2 API has a more
sophisticated sharing scheme that contains an anti-spam provision.)

Add member to image
~~~~~~~~~~~~~~~~~~~

.. rest_method::  PUT /v1/images/{image_id}/members/{member_id}

Adds the tenant whose tenant ID is ``member_id`` as a member of the
image denoted by ``image_id``.

By default, an image member cannot further share the image with other
tenants.  This behavior can be overridden by supplying a request body
with the call that specifies ``can_share`` as ``true``.

Thus:

- If you omit the request body, this call adds the specified tenant as a
  member of the image with the ``can_share`` attribute set to ``false``.
- If you include a request body, the ``can_share`` attribute will be set
  to the appropriate boolean value you have supplied in the request body.
- If the specified tenant is already a member, and there is no request
  body, the membership (including the ``can_share`` attribute) remains
  unmodified.
- If the specified tenant is already a member and the request includes
  a body, the ``can_share`` attribute of the tenant will be set to whatever
  value is specified in the request body.

Normal response codes: 204

Error response codes: 404


Request
-------

.. rest_parameters:: parameters.yaml

   - image_id: image_id-in-path
   - member_id: member_id-in-path
   - can_share: can_share
   - member_id: member_id


Request Example
---------------

.. literalinclude:: samples/image-member-add-request.json
   :language: json


Replace membership list for an image
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  PUT /v1/images/{image_id}/members

Replaces the membership list for an image so that the tenants whose
tenant IDs are listed in the member objects comprising the request body
become all and only the members of the image denoted by ``image_id``.

If the ``can_share`` attribute is omitted for in any member object:

- If the member already exists on the image, that member's ``can_share``
  setting remains unchanged.
- If the member did not already exist on the image, that member's
  ``can_share`` attribute is set to ``false``.

Normal response codes: 204

Error response codes: 404


Request
-------

.. rest_parameters:: parameters.yaml

   - image_id: image_id-in-path
   - memberships: memberships

Request Example
---------------

.. literalinclude:: samples/image-members-add-request.json
   :language: json


Remove member
~~~~~~~~~~~~~

.. rest_method::  DELETE /v1/images/{image_id}/members/{member_id}

Removes a member from an image.

Normal response codes: 204

Error response codes: 404


Request
-------

.. rest_parameters:: parameters.yaml

   - image_id: image_id-in-path
   - member_id: member_id-in-path


List shared images
~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1/shared-images/{owner_id}

Lists the VM images that an owner shares. The ``owner_id`` is the tenant ID
of the image owner.

Normal response codes: 200

Error response codes: 404


Request
-------

.. rest_parameters:: parameters.yaml

   - owner_id: owner_id-in-path


Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

   - shared_images: shared_images


Response Example
----------------

.. literalinclude:: samples/shared-images-list-response.json
   :language: json
