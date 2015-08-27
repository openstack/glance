..
      Copyright 2015 OpenStack Foundation
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

============================
Glance database architecture
============================

Glance Database Public API
~~~~~~~~~~~~~~~~~~~~~~~~~~

Glance DB API contains several methods to process information from
and to a persistent storage. Below you can find a list of public
methods grouped by categories.

Common parameters for image methods
-----------------------------------

The following parameters can be applied to all the below image methods:
 - ``context`` corresponds to a value with glance.context.RequestContext
   object, which stores the information on how a user accesses
   the system, as well as additional request information;
 - ``image_id`` — a string corresponding to the image identifier;
 - ``memb_id`` — a string corresponding to the member identifier
   of the image.

Image basic methods
-------------------

**Image processing methods:**

#. ``image_create(context, values)`` - creates a new image record
   with parameters listed in the *values* dictionary. Returns a
   dictionary representation of a newly created *glance.db.sqlalchemy.
   models.Image* object.
#. ``image_update(context, image_id, values, purge_props=False,
   from_state=None)`` - updates the existing image with an identifier
   *image_id* with values listed in the *values* dictionary. Returns a
   dictionary representation of a newly created *Image* object.

 Optional parameters are:
     - ``purge_props`` - a flag indicating that all the existing
       properties not listed in the *values[‘properties’]* should be
       deleted;
     - ``from_state`` - a string filter indicating that the updated
       image must be in the specified state.

#. ``image_destroy(context, image_id)`` - deletes all the database
   record of an image with an identifier *image_id*, like tags,
   properties, and members, and sets a ‘deleted’ status to all the
   image locations.
#. ``image_get(context, image_id, force_show_deleted=False)`` -
   gets an image with an identifier *image_id* and returns its
   dictionary representation. A parameter *force_show_deleted* is
   a flag that indicates to show image info even if it was
   ‘deleted’, or its ‘pending_delete’ statuses.
#. ``image_get_all(context, filters=None, marker=None, limit=None,
   sort_key=None, sort_dir=None, member_status='accepted',
   is_public=None, admin_as_user=False, return_tag=False)`` - gets
   all the images that match zero or more filters.

 Optional parameters are:
     - ``filters`` - dict of filter keys and values. If a 'properties'
       key is present, it is treated as a dict of key/value filters in
       the attribute of the image properties.
     - ``marker`` - image id after which a page should start;
     - ``limit`` - maximum number of images to return;
     - ``sort_key`` - list of image attributes by which results should
       be sorted;
     - ``sort_dir`` - directions in which results should be sorted
       (asc, desc);
     - ``member_status`` - only returns shared images that have this
       membership status;
     - ``is_public`` - if true, returns only public images. If false,
       returns only private and shared images.
     - ``admin_as_user`` - for backwards compatibility. If true, admin
       receives an equivalent set of images that he would see if he was
       a regular user.
     - ``return_tag`` - indicates whether an image entry in the result
       includes its relevant tag entries. This can improve upper-layer
       query performance and prevent using separated calls.

Image location methods
----------------------

**Image location processing methods:**

#. ``image_location_add(context, image_id, location)`` -
   adds a new location to an image with an identifier image_id. This
   location contains values listed in the dictionary *location*.
#. ``image_location_update(context, image_id, location)`` - updates
   an existing location with an identifier *location[‘id’]*
   for an image with an identifier *image_id* with values listed in
   the dictionary *location*.
#. ``image_location_delete(context, image_id, location_id, status,
   delete_time=None)`` - sets a 'deleted' or 'pending_delete'
   *status* to an existing location record with an identifier
   *location_id* for an image with an identifier *image_id*.

Image property methods
----------------------

.. warning:: There is no public property update method.
   So if you want to modify it, you have to delete it first
   and then create a new one.

**Image property processing methods:**

#. ``image_property_create(context, values)`` - creates
   a property record with parameters listed in the *values* dictionary
   for an image with *values[‘id’]*. Returns a dictionary representation
   of a newly created *ImageProperty* object.
#. ``image_property_delete(context, prop_ref, image_ref)`` - deletes an
   existing property record with a name *prop_ref* for an image with
   an identifier *image_ref*.

Image member methods
--------------------

**Methods to handle image memberships:**

#. ``image_member_create(context, values)`` - creates a member record
   with properties listed in the *values* dictionary for an image
   with *values[‘id’]*. Returns a dictionary representation
   of a newly created *ImageMember* object.
#. ``image_member_update(context, memb_id, values)`` - updates an
   existing member record with properties listed in the *values*
   dictionary for an image with *values[‘id’]*. Returns a dictionary
   representation of an updated member record.
#. ``image_member_delete(context, memb_id)`` - deletes  an existing
   member record with *memb_id*.
#. ``image_member_find(context, image_id=None, member=None, status=None)``
   - returns all members for a given context with optional image
   identifier (*image_id*), member name (*member*), and member status
   (*status*) parameters.
#. ``image_member_count(context, image_id)`` - returns a number of image
   members for an image with *image_id*.

Image tag methods
-----------------

**Methods to process images tags:**

#. ``image_tag_set_all(context, image_id, tags)`` - changes all the
   existing tags for an image with *image_id* to the tags listed
   in the *tags* param. To remove all tags, a user just should provide
   an empty list.
#. ``image_tag_create(context, image_id, value)`` - adds a *value*
   to tags for an image with *image_id*. Returns the value of a
   newly created tag.
#. ``image_tag_delete(context, image_id, value)`` - removes a *value*
   from tags for an image with *image_id*.
#. ``image_tag_get_all(context, image_id)`` - returns a list of tags
   for a specific image.

Image info methods
------------------

The next two methods inform a user about his ability to modify
and view an image. *image* param here is a dictionary representation
of an *Image* object.

#. ``is_image_mutable(context, image)`` - informs a user
   about the possibility to modify an image with a given context.
   Returns True if the image is mutable in this context.
#. ``is_image_visible(context, image, status=None)`` - informs about
   the possibility to observe the image details with a given context
   and optionally with a status. Returns True if the image is visible
   in this context.

**Glance database schema**

.. figure:: /images/glance_db.png
   :figwidth: 100%
   :align: center
   :alt: Glance images DB schema

.. centered:: Image 1. Glance images DB schema


Glance Database Backends
~~~~~~~~~~~~~~~~~~~~~~~~

Migration Backends
------------------

.. list-plugins:: glance.database.migration_backend
   :detailed:

Metadata Backends
-----------------

.. list-plugins:: glance.database.metadata_backend
   :detailed:
