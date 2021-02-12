.. -*- rst -*-

.. _image-sharing:

Sharing
*******

Images may be shared among projects by creating *members* on the image.  Image
members have read-only privileges on the image.  The following calls allow you
to create, list, update, and delete image members.

.. note::

   An image member is an identifier for a consumer with whom the image is
   shared.  In OpenStack clouds, where the value of the ``owner`` property
   of an image is a project ID, the appropriate identifier to use for the
   ``member_id`` is the consumer's project ID (which used to be called the
   "tenant ID").

   * Image sharing is project-to-project.  Thus *all the individual users
     in the consuming project have access to the image*.  You cannot share
     an image with only one specific user in the target project.

When an image is shared, the member is given immediate access to the image.
In order to prevent spamming other users' image lists, a shared image does not
appear in a member's image list until the member "accepts" the image.

Only the image owner may create members.  Only an image member may modify his
or her member status.

.. TODO(rosmaita): update the following reference when the "narrative" API
   docs have a final resting place

For a conceptual overview of image sharing, including a suggested workflow,
please consult `Image API v2 Sharing`_.

.. _Image API v2 Sharing:
    http://specs.openstack.org/openstack/glance-specs/specs/api/v2/sharing-image-api-v2.html

.. note::

   If you don't want to maintain a sharing relationship with particular
   image consumers, but instead want to make an image available to *all*
   users, you may update your image's ``visibility`` property to
   ``community``.

   * In some clouds, the ability to "communitize" an image may be prohibited
     or restricted to trusted users.  Please consult your cloud's local
     documentation for details.

Create image member
~~~~~~~~~~~~~~~~~~~

.. rest_method::  POST /v2/images/{image_id}/members

Adds a tenant ID as an image member.
*(Since Image API v2.1)*


Preconditions

- The image must exist.

- The image must have a ``visibility`` value of ``shared``.

- You must be the owner of the image.

Synchronous Postconditions

- With correct permissions, you can see the member status of the
  image member as ``pending`` through API calls.

Troubleshooting

- Even if you have correct permissions, if the ``visibility``
  attribute is not set to ``shared``, the request returns the HTTP
  ``403`` response code. Ensure that you meet the preconditions and
  run the request again. If the request fails again, review your
  API request.

- If the member is already a member for the image, the service
  returns the ``Conflict (409)`` response code. If you meant to
  specify a different member, run the request again.


Normal response codes: 200

Error response codes: 400, 401, 403, 404, 409, 413


Request
-------

.. rest_parameters:: images-parameters.yaml

   - image_id: image_id-in-path
   - member: member_id

Request Example
---------------

.. literalinclude:: samples/image-member-create-request.json
   :language: json



Response Parameters
-------------------

.. rest_parameters:: images-parameters.yaml

   - created_at: created_at
   - image_id: image_id-in-body
   - member_id: member_id
   - schema: schema-member
   - status: member_status
   - updated_at: updated_at

Response Example
----------------

.. literalinclude:: samples/image-member-create-response.json
   :language: json


Show image member details
~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/images/{image_id}/members/{member_id}

Shows image member details.
*(Since Image API v2.1)*

Response body is a single image member entity.

Preconditions

- The image must exist.

- The image must have a ``visibility`` value of ``shared``.

- You must be the owner or the member of the image who's referenced in the
  call.


Normal response codes: 200

Error response codes: 400, 401, 404


Request
-------

.. rest_parameters:: images-parameters.yaml

   - image_id: image_id-in-path
   - member_id: member_id-in-path


Response Parameters
-------------------

.. rest_parameters:: images-parameters.yaml

   - created_at: created_at
   - image_id: image_id-in-body
   - member_id: member_id
   - schema: schema-member
   - status: member_status
   - updated_at: updated_at


Response Example
----------------

.. literalinclude:: samples/image-member-details-response.json
   :language: json


List image members
~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v2/images/{image_id}/members

Lists the tenants that share this image.
*(Since Image API v2.1)*

If the image owner makes this call, the complete member list is
returned.

If a user who is an image member makes this call, the member list
contains only information for that user.

If a user who is not an image member makes this call, the call
returns the HTTP ``404`` response code.

Preconditions

- The image must exist.

- The image must have a ``visibility`` value of ``shared``.

- You must be the owner or a member of the image.


Normal response codes: 200

Error response codes: 400, 401, 403, 404


Request
-------

.. rest_parameters:: images-parameters.yaml

   - image_id: image_id-in-path


Response Parameters
-------------------

.. rest_parameters:: images-parameters.yaml

   - members: members
   - schema: schema-members


Response Example
----------------

.. literalinclude:: samples/image-members-list-response.json
   :language: json


Update image member
~~~~~~~~~~~~~~~~~~~

.. rest_method::  PUT /v2/images/{image_id}/members/{member_id}

Sets the status for an image member.
*(Since Image API v2.1)*

This call allows an image member to change his or her *member status*.

When an image is shared with you, you have immediate access to the image.  What
updating your member status on the image does for you is that it affects
whether the image will appear in your image list response.

- When an image is shared with you, your member_status is ``pending``.  You
  won't see the image unless you go looking for it, either by making a show
  image detail request using the image's ID, or by making an image list call
  specifically looking for a shared image in member status ``pending``.  This
  way, other users cannot "spam" your image list with images you may not want
  to see.

- If you want to see a particular shared image in your image list, then you
  must use this call to change your member status on the image to ``accepted``.

- The image owner can see what your member status is on an image, but the owner
  *cannot* change the status.  Only you (or an administrator) can do that.

- There are three member status values: ``pending``, ``accepted``, and
  ``rejected``.  The ``pending`` and ``rejected`` statuses are functionally
  identical.  The difference is that ``pending`` indicates to the owner that
  you haven't updated the image, so perhaps you aren't aware that it's been
  shared with you.  The ``rejected`` status indicates that you are aware that
  the image exists and you specifically decided that you don't want to see it
  in your image list response.

For a more detailed discussion of image sharing, please consult `Image API v2
Sharing`_.

Preconditions

- The image must exist.

- The image must have a ``visibility`` value of ``shared``.

- You must be the member of the image referenced in the call.

Synchronous Postconditions

- If you update the member status to ``accepted`` and have the
  correct permissions, you see the image in list images responses.

- With correct permissions, you can make API calls to see the
  updated member status of the image.


Normal response codes: 200

Error response codes: 400, 401, 404, 403


Request
-------

.. rest_parameters:: images-parameters.yaml

   - image_id: image_id-in-path
   - member_id: member_id-in-path
   - status: member_status

Request Example
---------------

.. literalinclude:: samples/image-member-update-request.json
   :language: json



Response Parameters
-------------------

.. rest_parameters:: images-parameters.yaml

   - created_at: created_at
   - image_id: image_id-in-body
   - member_id: member_id
   - schema: schema-member
   - status: member_status
   - updated_at: updated_at


Response Example
----------------

.. literalinclude:: samples/image-member-update-response.json
   :language: json


Delete image member
~~~~~~~~~~~~~~~~~~~

.. rest_method::  DELETE /v2/images/{image_id}/members/{member_id}

Deletes a tenant ID from the member list of an image.
*(Since Image API v2.1)*

Preconditions

- The image must exist.

- The image must have a ``visibility`` value of ``shared``.

- You must be the owner of the image.

Synchronous Postconditions

- The API removes the member from the image members.

Troubleshooting

- Even if you have correct permissions, if you are not the owner of
  the image or you specify an incorrect image ID or member ID, the
  call returns the HTTP ``403`` or ``404`` response code. Ensure
  that you meet the preconditions and run the request again. If the
  request fails again, review your API request URI.

Normal response codes: 204

Error response codes: 400, 401, 403, 404


Request
-------

.. rest_parameters:: images-parameters.yaml

   - image_id: image_id-in-path
   - member_id: member_id-in-path
