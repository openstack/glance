..
      Copyright 2010 OpenStack, LLC
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

Using Glance Programmatically with Glance's Client
==================================================

While it is perfectly acceptable to issue HTTP requests directly to Glance
via its RESTful API, sometimes it is better to be able to access and modify
image resources via a client class that removes some of the complexity and
tedium of dealing with raw HTTP requests.

Glance includes a client class for just this purpose. You can retrieve
metadata about an image, change metadata about an image, remove images, and
of course retrieve an image itself via this client class.

Below are some examples of using Glance's Client class.  We assume that
there is a Glance server running at the address `glance.example.com`
on port `9292`.

Requesting a List of Public VM Images
-------------------------------------

We want to see a list of available virtual machine images that the Glance
server knows about.

Using Glance's Client, we can do this using the following code

.. code-block:: python

  from glance.client import Client

  c = Client("glance.example.com", 9292)

  print c.get_images()


Requesting Detailed Metadata on Public VM Images
------------------------------------------------

We want to see more detailed information on available virtual machine images
that the Glance server knows about.

Using Glance's Client, we can do this using the following code

.. code-block:: python

  from glance.client import Client

  c = Client("glance.example.com", 9292)

  print c.get_images_detailed()

Filtering Images Returned via ``get_images()`` and ``get_images_detailed()``
----------------------------------------------------------------------------

Both the ``get_images()`` and ``get_images_detailed()`` methods take query
parameters that serve to filter the returned list of images. 

When calling, simply pass an optional dictionary to the method containing
the filters by which you wish to limit results, with the filter keys being one
or more of the below:

* ``name: NAME``

  Filters images having a ``name`` attribute matching ``NAME``.

* ``container_format: FORMAT``

  Filters images having a ``container_format`` attribute matching ``FORMAT``

  For more information, see :doc:`About Disk and Container Formats <formats>`

* ``disk_format: FORMAT``

  Filters images having a ``disk_format`` attribute matching ``FORMAT``

  For more information, see :doc:`About Disk and Container Formats <formats>`

* ``status: STATUS``

  Filters images having a ``status`` attribute matching ``STATUS``

  For more information, see :doc:`About Image Statuses <statuses>`

* ``size_min: BYTES``

  Filters images having a ``size`` attribute greater than or equal to ``BYTES``

* ``size_max: BYTES``

  Filters images having a ``size`` attribute less than or equal to ``BYTES``

Here's a quick example that will return all images less than or equal to 5G
in size and in the `saving` status.

.. code-block:: python

  from glance.client import Client

  c = Client("glance.example.com", 9292)

  filters = {'status': 'saving', 'size_max': (5 * 1024 * 1024 * 1024)}
  print c.get_images_detailed(filters=filters)

Sorting Images Returned via ``get_images()`` and ``get_images_detailed()``
--------------------------------------------------------------------------

Two parameters are available to sort the list of images returned by
these methods.

* ``sort_key: KEY``

  Images can be ordered by the image attribute ``KEY``. Acceptable values:
  ``id``, ``name``, ``status``, ``container_format``, ``disk_format``,
  ``created_at`` (default) and ``updated_at``.

* ``sort_dir: DIR``

  The direction of the sort may be defined by ``DIR``. Accepted values:
  ``asc`` for ascending or ``desc`` (default) for descending.

The following example will return a list of images sorted alphabetically
by name in ascending order.

.. code-block:: python

  from glance.client import Client

  c = Client("glance.example.com", 9292)

  print c.get_images(sort_key='name', sort_dir='asc')


Requesting Detailed Metadata on a Specific Image
------------------------------------------------

We want to see detailed information for a specific virtual machine image
that the Glance server knows about.

We have queried the Glance server for a list of public images and the
data returned includes the `uri` field for each available image. This
`uri` field value contains the exact location needed to get the metadata
for a specific image.

Continuing the example from above, in order to get metadata about the
first public image returned, we can use the following code

.. code-block:: python

  from glance.client import Client

  c = Client("glance.example.com", 9292)

  print c.get_image_meta("http://glance.example.com/images/1")

Retrieving a Virtual Machine Image
----------------------------------

We want to retrieve that actual raw data for a specific virtual machine image
that the Glance server knows about.

We have queried the Glance server for a list of public images and the
data returned includes the `uri` field for each available image. This
`uri` field value contains the exact location needed to get the metadata
for a specific image.

Continuing the example from above, in order to get both the metadata about the
first public image returned and its image data, we can use the following code

.. code-block:: python

  from glance.client import Client

  c = Client("glance.example.com", 9292)

  meta, image_file = c.get_image("http://glance.example.com/images/1")

  print meta

  f = open('some_local_file', 'wb')
  for chunk in image_file:
      f.write(chunk)
  f.close()

.. note::

  The return from Client.get_image() is a tuple of (`metadata`, `file`)
  where `metadata` is a mapping of metadata about the image and `file` is a
  generator that yields chunks of image data.

Adding a New Virtual Machine Image
----------------------------------

We have created a new virtual machine image in some way (created a
"golden image" or snapshotted/backed up an existing image) and we
wish to do two things:

* Store the disk image data in Glance
* Store metadata about this image in Glance

We can do the above two activities in a single call to the Glance client.
Assuming, like in the examples above, that a Glance API server is running
at `glance.example.com`, we issue a call to `glance.client.Client.add_image`.

The method signature is as follows::

  glance.client.Client.add_image(image_meta, image_data=None)

The `image_meta` argument is a mapping containing various image metadata. 
The `image_data` argument is the disk image data and is an optional argument.

The list of metadata that `image_meta` can contain are listed below.

* `name`

  This key/value is required. Its value should be the name of the image.

  Note that the name of an image *is not unique to a Glance node*. It
  would be an unrealistic expectation of users to know all the unique
  names of all other user's images.

* `id`

  This key/value is optional. 

  When present, Glance will use the supplied identifier for the image.
  If the identifier already exists in that Glance node, then a
  `glance.common.exception.Duplicate` will be raised.

  When this key/value is *not* present, Glance will generate an identifier
  for the image and return this identifier in the response (see below)

* `store`

  This key/value is optional. Valid values are one of `file`, `s3` or `swift`

  When present, Glance will attempt to store the disk image data in the
  backing store indicated by the value. If the Glance node does not support
  the backing store, Glance will raise a `glance.common.exception.BadRequest`

  When not present, Glance will store the disk image data in the backing
  store that is marked default. See the configuration option `default_store`
  for more information.

* `type`

  This key/values is required. Valid values are one of `kernel`, `machine`,
  `raw`, or `ramdisk`.

* `size`

  This key/value is optional.

  When present, Glance assumes that the expected size of the request body
  will be the value. If the length in bytes of the request body *does not
  match* the value, Glance will raise a `glance.common.exception.BadRequest`

  When not present, Glance will calculate the image's size based on the size
  of the request body.

* `is_public`

  This key/value is optional.

  When present, Glance converts the value to a boolean value, so "on, 1, true"
  are all true values. When true, the image is marked as a public image,
  meaning that any user may view its metadata and may read the disk image from
  Glance.

  When not present, the image is assumed to be *not public* and specific to
  a user.

* `properties`

  This key/value is optional.

  When present, the value is assumed to be a mapping of free-form key/value
  attributes to store with the image.

  For example, if the following is the value of the `properties` key in the
  `image_meta` argument::

    {'distro': 'Ubuntu 10.10'}

  Then a key/value pair of "distro"/"Ubuntu 10.10" will be stored with the
  image in Glance.

  There is no limit on the number of free-form key/value attributes that can
  be attached to the image with `properties`.  However, keep in mind that there
  is a 8K limit on the size of all HTTP headers sent in a request and this
  number will effectively limit the number of image properties.

  If the `image_data` argument is omitted, Glance will add the `image_meta`
  mapping to its registries and return the newly-registered image metadata,
  including the new image's identifier. The `status` of the image will be
  set to the value `queued`.

As a complete example, the following code would add a new machine image to
Glance

.. code-block:: python

  from glance.client import Client

  c = Client("glance.example.com", 9292)

  meta = {'name': 'Ubuntu 10.10 5G',
          'type': 'machine',
          'is_public': True,
          'properties': {'distro': 'Ubuntu 10.10'}}

  new_meta = c.add_image(meta, open('/path/to/image.tar.gz'))

  print 'Stored image. Got identifier: %s' % new_meta['id']

Requesting Image Memberships
----------------------------

We want to see a list of the other system tenants that may access a given
virtual machine image that the Glance server knows about.

Continuing from the example above, in order to get the memberships for the
image with ID 1, we can use the following code

.. code-block:: python

  from glance.client import Client

  c = Client("glance.example.com", 9292)

  members = c.get_image_members(1)

.. note::

  The return from Client.get_image_members() is a list of dictionaries.  Each
  dictionary has a `member_id` key, mapping to the tenant the image is shared
  with, and a `can_share` key, mapping to a boolean value that identifies
  whether the member can further share the image.

Requesting Member Images
------------------------

We want to see a list of the virtual machine images a given system tenant may
access.

Continuing from the example above, in order to get the images shared with
'tenant1', we can use the following code

.. code-block:: python

  from glance.client import Client

  c = Client("glance.example.com", 9292)

  images = c.get_member_images('tenant1')

.. note::

  The return from Client.get_member_images() is a list of dictionaries.  Each
  dictionary has an `image_id` key, mapping to an image shared with the member,
  and a `can_share` key, mapping to a boolean value that identifies whether
  the member can further share the image.

Adding a Member To an Image
---------------------------

We want to authorize a tenant to access a private image.

Continuing from the example above, in order to share the image with ID 1
with 'tenant1', and to allow 'tenant2' to not only access the image but to also
share it with other tenants, we can use the following code

.. code-block:: python

  from glance.client import Client

  c = Client("glance.example.com", 9292)

  c.add_member(1, 'tenant1')
  c.add_member(1, 'tenant2', True)

.. note::

  The Client.add_member() function takes one optional argument, the `can_share`
  value.  If one is not provided and the membership already exists, its current
  `can_share` setting is left alone.  If the membership does not already exist,
  then the `can_share` setting will default to `False`, and the membership will
  be created.  In all other cases, existing memberships will be modified to use
  the specified `can_share` setting, and new memberships will be created with
  it.  The return value of Client.add_member() is not significant.

Removing a Member From an Image
-------------------------------

We want to revoke a tenant's authorization to access a private image.

Continuing from the example above, in order to revoke the access of 'tenant1'
to the image with ID 1, we can use the following code

.. code-block:: python

  from glance.client import Client

  c = Client("glance.example.com", 9292)

  c.delete_member(1, 'tenant1')

.. note::

  The return value of Client.delete_member() is not significant.

Replacing a Membership List For an Image
----------------------------------------

All existing image memberships may be revoked and replaced in a single
operation.

Continuing from the example above, in order to replace the membership list
of the image with ID 1 with two entries--the first allowing 'tenant1' to
access the image, and the second allowing 'tenant2' to access and further
share the image, we can use the following code

.. code-block:: python

  from glance.client import Client

  c = Client("glance.example.com", 9292)

  c.replace_members(1, {'member_id': 'tenant1', 'can_share': False},
                    {'member_id': 'tenant2', 'can_share': True})

.. note::

  The first argument to Client.replace_members() is the opaque identifier of
  the image; the remaining arguments are dictionaries with the keys
  `member_id` (mapping to a tenant name) and `can_share`.  Note that
  `can_share` may be omitted, in which case any existing membership for the
  specified member will be preserved through the replace operation.

  The return value of Client.replace_members() is not significant.
