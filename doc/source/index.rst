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
     'size_in_bytes': '5368709120'}
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
     'size_in_bytes': '5368709120',
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
  x-image-meta-size_in_bytes    5368709120
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
  x-image-meta-size_in_bytes    5368709120
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
 * The response's `Content-Type` header shall be equal to the value of
   the `x-image-meta-size_in_bytes` header
 * The image data itself will be the body of the HTTP response returned
   from the request, which will have content-type of
   `application/octet-stream`.
 * The response may have an optional content-encoding of `gzip`


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
there is a Glance server running at the address http://glance.openstack.org
on port `9292`.

Requesting a List of Public VM Images
-------------------------------------

We want to see a list of available virtual machine images that the Glance
server knows about.

Using Glance's Client, we can do this using the following code::

  from glance import client

  c = client.Client("http://glance.openstack.org", 9292)

  print c.get_images()


Requesting Detailed Metadata on Public VM Images
------------------------------------------------

We want to see more detailed information on available virtual machine images
that the Glance server knows about.

Using Glance's Client, we can do this using the following code::

  from glance import client

  c = client.Client("http://glance.openstack.org", 9292)

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

  c = client.Client("http://glance.openstack.org", 9292)

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

  c = client.Client("http://glance.openstack.org", 9292)

  meta, image_data = c.get_image("http://glance.openstack.org/images/1")

  print meta


.. toctree::
    :maxdepth: 1

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
