..
      Copyright 2012 OpenStack Foundation
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

Policies
========

Glance's public API calls may be restricted to certain sets of users using a
policy configuration file. This document explains exactly how policies are
configured and what they apply to.

A policy is composed of a set of rules that are used by the policy "Brain" in
determining if a particular action may be performed by the authorized tenant.

Constructing a Policy Configuration File
----------------------------------------

A policy configuration file is a simply JSON object that contain sets of
rules. Each top-level key is the name of a rule. Each rule
is a string that describes an action that may be performed in the Glance API.

The actions that may have a rule enforced on them are:

* ``get_images`` - List available image entities

  * ``GET /v1/images``
  * ``GET /v1/images/detail``
  * ``GET /v2/images``

* ``get_image`` - Retrieve a specific image entity

  * ``HEAD /v1/images/<IMAGE_ID>``
  * ``GET /v1/images/<IMAGE_ID>``
  * ``GET /v2/images/<IMAGE_ID>``

* ``download_image`` - Download binary image data

  * ``GET /v1/images/<IMAGE_ID>``
  * ``GET /v2/images/<IMAGE_ID>/file``

* ``upload_image`` - Upload binary image data

  * ``POST /v1/images``
  * ``PUT /v1/images/<IMAGE_ID>``
  * ``PUT /v2/images/<IMAGE_ID>/file``

* ``copy_from`` - Copy binary image data from URL

  * ``POST /v1/images``
  * ``PUT /v1/images/<IMAGE_ID>``

* ``add_image`` - Create an image entity

  * ``POST /v1/images``
  * ``POST /v2/images``

* ``modify_image`` - Update an image entity

  * ``PUT /v1/images/<IMAGE_ID>``
  * ``PUT /v2/images/<IMAGE_ID>``

* ``publicize_image`` - Create or update public images

  * ``POST /v1/images`` with attribute ``is_public`` = ``true``
  * ``PUT /v1/images/<IMAGE_ID>`` with attribute ``is_public`` = ``true``
  * ``POST /v2/images`` with attribute ``visibility`` = ``public``
  * ``PUT /v2/images/<IMAGE_ID>`` with attribute ``visibility`` = ``public``

* ``communitize_image`` - Create or update community images

  * ``POST /v2/images`` with attribute ``visibility`` = ``community``
  * ``PUT /v2/images/<IMAGE_ID>`` with attribute ``visibility`` = ``community``

* ``delete_image`` - Delete an image entity and associated binary data

  * ``DELETE /v1/images/<IMAGE_ID>``
  * ``DELETE /v2/images/<IMAGE_ID>``

* ``add_member`` - Add a membership to the member repo of an image

  * ``POST /v2/images/<IMAGE_ID>/members``

* ``get_members`` - List the members of an image

  * ``GET /v1/images/<IMAGE_ID>/members``
  * ``GET /v2/images/<IMAGE_ID>/members``

* ``delete_member`` - Delete a membership of an image

  * ``DELETE /v1/images/<IMAGE_ID>/members/<MEMBER_ID>``
  * ``DELETE /v2/images/<IMAGE_ID>/members/<MEMBER_ID>``

* ``modify_member`` - Create or update the membership of an image

  * ``PUT /v1/images/<IMAGE_ID>/members/<MEMBER_ID>``
  * ``PUT /v1/images/<IMAGE_ID>/members``
  * ``POST /v2/images/<IMAGE_ID>/members``
  * ``PUT /v2/images/<IMAGE_ID>/members/<MEMBER_ID>``

* ``manage_image_cache`` - Allowed to use the image cache management API


To limit an action to a particular role or roles, you list the roles like so ::

  {
    "delete_image": ["role:admin", "role:superuser"]
  }

The above would add a rule that only allowed users that had roles of either
"admin" or "superuser" to delete an image.

Writing Rules
-------------

Role checks are going to continue to work exactly as they already do. If the
role defined in the check is one that the user holds, then that will pass,
e.g., ``role:admin``.

To write a generic rule, you need to know that there are three values provided
by Glance that can be used in a rule on the left side of the colon (``:``).
Those values are the current user's credentials in the form of:

- role
- tenant
- owner

The left side of the colon can also contain any value that Python can
understand, e.g.,:

- ``True``
- ``False``
- ``"a string"``
- &c.

Using ``tenant`` and ``owner`` will only work with images. Consider the
following rule::

    tenant:%(owner)s

This will use the ``tenant`` value of the currently authenticated user. It
will also use ``owner`` from the image it is acting upon. If those two
values are equivalent the check will pass. All attributes on an image (as well
as extra image properties) are available for use on the right side of the
colon. The most useful are the following:

- ``owner``
- ``protected``
- ``is_public``

Therefore, you could construct a set of rules like the following::

    {
        "not_protected": "False:%(protected)s",
        "is_owner": "tenant:%(owner)s",
        "is_owner_or_admin": "rule:is_owner or role:admin",
        "not_protected_and_is_owner": "rule:not_protected and rule:is_owner",

        "get_image": "rule:is_owner_or_admin",
        "delete_image": "rule:not_protected_and_is_owner",
        "add_member": "rule:not_protected_and_is_owner"
    }

Examples
--------

Example 1. (The default policy configuration)

::

  {
      "default": ""
  }

Note that an empty JSON list means that all methods of the
Glance API are callable by anyone.

Example 2. Disallow modification calls to non-admins

::

  {
      "default": "",
      "add_image": "role:admin",
      "modify_image": "role:admin",
      "delete_image": "role:admin"
  }
