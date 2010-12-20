.. Glance documentation master file, created by
   sphinx-quickstart on Tue May 18 13:50:15 2010.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to Glance's documentation!
==================================

The Glance project provides services for discovering, registering, and
retrieving virtual machine images. Glance has a RESTful API that allows
querying of VM image metadata as well as retrieval of the actual image.

VM images made available through Glance can be stored in a variety of
locations from simple filesystems to object-storage systems like the
OpenStack Swift project.

.. toctree::
    :maxdepth: 1

Overview
========

The Glance project provides services for discovering, registering, and
retrieving virtual machine images. Glance has a RESTful API that allows
querying of VM image metadata as well as retrieval of the actual image.

.. toctree::
    :maxdepth: 1

The Glance API
==============

Glance has a RESTful API that exposes both metadata about registered virtual
machine images and the image data itself.

A host that runs the `bin/glance-api` service is said to be a *Glance API
Server*.

Assume there is a Glance API server running at the URL
http://glance.openstack.org. 

Let's walk through how a user might request information from this server.

Requesting a List of Public VM Images
-------------------------------------

We want to see a list of available virtual machine images that the Glance
server knows about.

We issue a `GET` request to http://glance.openstack.org/images/ to retrieve
this list of available *public* images. The data is returned as a JSON-encoded
mapping in the following format::

  {'images': [
    {'uri': 'http://glance.openstack.org/images/1',
     'name': 'Ubuntu 10.04 Plain',
     'type': 'kernel',
     'size': '5368709120'}
    ...]}

Notes:

 * All images returned from the above `GET` request are *public* images


Requesting Detailed Metadata on Public VM Images
------------------------------------------------

We want to see more detailed information on available virtual machine images
that the Glance server knows about.

We issue a `GET` request to http://glance.openstack.org/images/detail to
retrieve this list of available *public* images. The data is returned as a
JSON-encoded mapping in the following format::

  {'images': [
    {'uri': 'http://glance.openstack.org/images/1',
     'name': 'Ubuntu 10.04 Plain 5GB',
     'type': 'kernel',
     'size': '5368709120',
     'store': 'swift',
     'created_at': '2010-02-03 09:34:01',
     'updated_at': '2010-02-03 09:34:01',
     'deleted_at': '',
     'status': 'available',
     'is_public': True,
     'properties': {'distro': 'Ubuntu 10.04 LTS'}},
    ...]}

Notes:

 * All images returned from the above `GET` request are *public* images
 * All timestamps returned are in UTC
 * The `updated_at` timestamp is the timestamp when an image's metadata
   was last updated, not it's image data, as all image data is immutable
   once stored in Glance
 * The `properties` field is a mapping of free-form key/value pairs that
   have been saved with the image metadata


Requesting Detailed Metadata on a Specific Image
------------------------------------------------

We want to see detailed information for a specific virtual machine image
that the Glance server knows about.

We have queried the Glance server for a list of public images and the
data returned includes the `uri` field for each available image. This
`uri` field value contains the exact location needed to get the metadata
for a specific image.

Continuing the example from above, in order to get metadata about the
first public image returned, we can issue a `HEAD` request to the Glance
server for the image's URI.

We issue a `HEAD` request to http://glance.openstack.org/images/1 to
retrieve complete metadata for that image. The metadata is returned as a
set of HTTP headers that begin with the prefix `x-image-meta-`. The
following shows an example of the HTTP headers returned from the above
`HEAD` request::

  x-image-meta-uri              http://glance.openstack.org/images/1
  x-image-meta-name             Ubuntu 10.04 Plain 5GB
  x-image-meta-type             kernel
  x-image-meta-size             5368709120
  x-image-meta-store            swift
  x-image-meta-created_at       2010-02-03 09:34:01
  x-image-meta-updated_at       2010-02-03 09:34:01
  x-image-meta-deleted_at       
  x-image-meta-status           available
  x-image-meta-is_public        True
  x-image-meta-property-distro  Ubuntu 10.04 LTS

Notes:

 * All timestamps returned are in UTC
 * The `x-image-meta-updated_at` timestamp is the timestamp when an
   image's metadata was last updated, not it's image data, as all 
   image data is immutable once stored in Glance
 * There may be multiple headers that begin with the prefix
   `x-image-meta-property-`.  These headers are free-form key/value pairs
   that have been saved with the image metadata. The key is the string
   after `x-image-meta-property-` and the value is the value of the header


Retrieving a Virtual Machine Image
----------------------------------

We want to retrieve that actual raw data for a specific virtual machine image
that the Glance server knows about.

We have queried the Glance server for a list of public images and the
data returned includes the `uri` field for each available image. This
`uri` field value contains the exact location needed to get the metadata
for a specific image.

Continuing the example from above, in order to get metadata about the
first public image returned, we can issue a `HEAD` request to the Glance
server for the image's URI.

We issue a `GET` request to http://glance.openstack.org/images/1 to
retrieve metadata for that image as well as the image itself encoded
into the response body.

The metadata is returned as a set of HTTP headers that begin with the
prefix `x-image-meta-`. The following shows an example of the HTTP headers
returned from the above `GET` request::

  x-image-meta-uri              http://glance.openstack.org/images/1
  x-image-meta-name             Ubuntu 10.04 Plain 5GB
  x-image-meta-type             kernel
  x-image-meta-size             5368709120
  x-image-meta-store            swift
  x-image-meta-created_at       2010-02-03 09:34:01
  x-image-meta-updated_at       2010-02-03 09:34:01
  x-image-meta-deleted_at       
  x-image-meta-status           available
  x-image-meta-is_public        True
  x-image-meta-property-distro  Ubuntu 10.04 LTS

Notes:

 * All timestamps returned are in UTC
 * The `x-image-meta-updated_at` timestamp is the timestamp when an
   image's metadata was last updated, not it's image data, as all 
   image data is immutable once stored in Glance
 * There may be multiple headers that begin with the prefix
   `x-image-meta-property-`.  These headers are free-form key/value pairs
   that have been saved with the image metadata. The key is the string
   after `x-image-meta-property-` and the value is the value of the header
 * The response's `Content-Length` header shall be equal to the value of
   the `x-image-meta-size` header
 * The image data itself will be the body of the HTTP response returned
   from the request, which will have content-type of
   `application/octet-stream`.


.. toctree::
    :maxdepth: 1


Adding a New Virtual Machine Image
----------------------------------

We have created a new virtual machine image in some way (created a
"golden image" or snapshotted/backed up an existing image) and we
wish to do two things:

 * Store the disk image data in Glance
 * Store metadata about this image in Glance

We can do the above two activities in a single call to the Glance API.
Assuming, like in the examples above, that a Glance API server is running
at `glance.openstack.org`, we issue a `POST` request to add an image to
Glance::

  POST http://glance.openstack.org/images/

The metadata about the image is sent to Glance in HTTP headers. The body
of the HTTP request to the Glance API will be the MIME-encoded disk
image data.


Adding Image Metadata in HTTP Headers
*************************************

Glance will view as image metadata any HTTP header that it receives in a
`POST` request where the header key is prefixed with the strings
`x-image-meta-` and `x-image-meta-property-`.

The list of metadata headers that Glance accepts are listed below.

 * `x-image-meta-name`

   This header is required. Its value should be the name of the image.

   Note that the name of an image *is not unique to a Glance node*. It
   would be an unrealistic expectation of users to know all the unique
   names of all other user's images.

 * `x-image-meta-id`

   This header is optional. 
   
   When present, Glance will use the supplied identifier for the image.
   If the identifier already exists in that Glance node, then a
   `409 Conflict` will be returned by Glance.

   When this header is *not* present, Glance will generate an identifier
   for the image and return this identifier in the response (see below)

 * `x-image-meta-store`

   This header is optional. Valid values are one of `file` or `swift`

   When present, Glance will attempt to store the disk image data in the
   backing store indicated by the value of the header. If the Glance node
   does not support the backing store, Glance will return a `400 Bad Request`.

   When not present, Glance will store the disk image data in the backing
   store that is marked default. See the configuration option `default_store`
   for more information.

 * `x-image-meta-type`

   This header is required. Valid values are one of `kernel`, `machine`, `raw`,
   or `ramdisk`.

 * `x-image-meta-size`

   This header is optional.

   When present, Glance assumes that the expected size of the request body
   will be the value of this header. If the length in bytes of the request
   body *does not match* the value of this header, Glance will return a
   `400 Bad Request`.

   When not present, Glance will calculate the image's size based on the size
   of the request body.

 * `x-image-meta-is_public`

   This header is optional.

   When present, Glance converts the value of the header to a boolean value,
   so "on, 1, true" are all true values. When true, the image is marked as
   a public image, meaning that any user may view its metadata and may read
   the disk image from Glance.

   When not present, the image is assumed to be *not public* and specific to
   a user.

 * `x-image-meta-property-*`

   When Glance receives any HTTP header whose key begins with the string prefix
   `x-image-meta-property-`, Glance adds the key and value to a set of custom,
   free-form image properties stored with the image.  The key is the
   lower-cased string following the prefix `x-image-meta-property-` with dashes
   and punctuation replaced with underscores.

   For example, if the following HTTP header were sent::

      x-image-meta-property-distro  Ubuntu 10.10

   Then a key/value pair of "distro"/"Ubuntu 10.10" will be stored with the
   image in Glance.

   There is no limit on the number of free-form key/value attributes that can
   be attached to the image.  However, keep in mind that the 8K limit on the
   size of all HTTP headers sent in a request will effectively limit the number
   of image properties.
  

.. toctree::
    :maxdepth: 1

Image Identifiers
=================

Images are uniquely identified by way of a URI that
matches the following signature::

  <Glance Server Location>/images/<ID>

where `<Glance Server Location>` is the resource location of the Glance service
that knows about an image, and `<ID>` is the image's identifier that is
*unique to that Glance server*.

.. toctree::
    :maxdepth: 1

Image Registration
==================

Image metadata made available through Glance can be stored in image
*registries*. Image registries are any web service that adheres to the
Glance RESTful API for image metadata.

.. toctree::
    :maxdepth: 1

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
there is a Glance server running at the address `glance.openstack.org`
on port `9292`.

Requesting a List of Public VM Images
-------------------------------------

We want to see a list of available virtual machine images that the Glance
server knows about.

Using Glance's Client, we can do this using the following code::

  from glance import client

  c = client.Client("glance.openstack.org", 9292)

  print c.get_images()


Requesting Detailed Metadata on Public VM Images
------------------------------------------------

We want to see more detailed information on available virtual machine images
that the Glance server knows about.

Using Glance's Client, we can do this using the following code::

  from glance import client

  c = client.Client("glance.openstack.org", 9292)

  print c.get_images_detailed()


Requesting Detailed Metadata on a Specific Image
------------------------------------------------

We want to see detailed information for a specific virtual machine image
that the Glance server knows about.

We have queried the Glance server for a list of public images and the
data returned includes the `uri` field for each available image. This
`uri` field value contains the exact location needed to get the metadata
for a specific image.

Continuing the example from above, in order to get metadata about the
first public image returned, we can use the following code::

  from glance import client

  c = client.Client("glance.openstack.org", 9292)

  print c.get_image_meta("http://glance.openstack.org/images/1")


Retrieving a Virtual Machine Image
----------------------------------

We want to retrieve that actual raw data for a specific virtual machine image
that the Glance server knows about.

We have queried the Glance server for a list of public images and the
data returned includes the `uri` field for each available image. This
`uri` field value contains the exact location needed to get the metadata
for a specific image.

Continuing the example from above, in order to get both the metadata about the
first public image returned and its image data, we can use the following code::

  from glance import client

  c = client.Client("glance.openstack.org", 9292)

  meta, image_file = c.get_image("http://glance.openstack.org/images/1")

  print meta

  f = open('some_local_file', 'wb')
  for chunk in image_file:
      f.write(chunk)
  f.close()

Note that the return from Client.get_image() is a tuple of (`metadata`, `file`)
where `metadata` is a mapping of metadata about the image and `file` is a
generator that yields chunks of image data.


.. toctree::
    :maxdepth: 1


Adding a New Virtual Machine Image
----------------------------------

We have created a new virtual machine image in some way (created a
"golden image" or snapshotted/backed up an existing image) and we
wish to do two things:

 * Store the disk image data in Glance
 * Store metadata about this image in Glance

We can do the above two activities in a single call to the Glance client.
Assuming, like in the examples above, that a Glance API server is running
at `glance.openstack.org`, we issue a call to `glance.client.Client.add_image`.

The method signature is as follows::

  glance.client.Client.add_image(image_meta, image_data=None)

The `image_meta` argument is a mapping containing various image metadata. The
`image_data` argument is the disk image data.

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

   This key/value is optional. Valid values are one of `file` or `swift`

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

As a complete example, the following code would add a new machine image to
Glance::

  from glance.client import Client

  c = Client("glance.openstack.org", 9292)

  meta = {'name': 'Ubuntu 10.10 5G',
          'type': 'machine',
          'is_public': True,
          'properties': {'distro': 'Ubuntu 10.10'}}

  new_meta = c.add_image(meta, open('/path/to/image.tar.gz'))

  print 'Stored image. Got identifier: %s' % new_meta['id']


.. toctree::
    :maxdepth: 1

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
