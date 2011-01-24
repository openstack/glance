..
      Copyright 2011 OpenStack, LLC
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

Quick Guide to Getting Started with Glance
==========================================

Glance is a server that provides the following services:

* Ability to store and retrieve virtual machine images
* Ability to store and retrieve metadata about these virtual machine images
* FUTURE: Convert a virtual machine image from one format to another
* FUTURE: Help caching proxies such as Varnish or Squid cache machine images

Communication with Glance occurs via a REST-like HTTP interface.

However, Glance includes a :doc:`Client <client>` class that makes working with Glance
easy and straightforward.

In the Cactus release, there will be also command-line tools for
interacting with Glance.

Overview of Glance Architecture
-------------------------------

There are two main parts to Glance's architecture:

* Glance API server
* Glance Registry server(s)

Glance API Server
*****************

The API server is the main interface for Glance. It routes requests from
clients to registries of image metadata and to its **backend stores**, which
are the mechanisms by which Glance actually saves incoming virtual machine
images.

The backend stores that Glance can work with are as follows:

* **Swift**

  Swift is the highly-available object storage project in OpenStack. More
  information can be found about Swift `here <http://swift.openstack.org>`_.

* **Filesystem**

  The default backend that Glance uses to store virtual machine images
  is the filesystem backend. This simple backend writes image files to the
  local filesystem.

* **S3**

  This backend allows Glance to store virtual machine images in Amazon's
  S3 service.

* **HTTP**

  Glance can read virtual machine images that are available via
  HTTP somewhere on the Internet.  This store is **readonly**

Glance Registry Servers
***********************

Glance registry servers are servers that conform to the Glance Registry API.
Glance ships with a reference implementation of a registry server that
complies with this API (``bin/glance-registry``).


Starting Up Glance's Servers
----------------------------

To get started using Glance, you must first start the Glance API server. 
After installing Glance, starting up the Glance API server is easy. Simply
start the ``glance-api`` program, like so::

  $> glance-api

Configuring the Glance API server
*********************************

There are a few options that can be supplied to the API server when
starting it up:

* ``verbose``

  Show more verbose/debugging output

* ``api_host``

  Address of the host the registry runs on. Defaults to 0.0.0.0.

* ``api_port``

  Port the registry server listens on. Defaults to 9292.

* ``default_store``

  The store that the Glance API server will use by default to store
  images that are added to it. The default value is `filesystem`, and
  possible choices are: `filesystem`, `swift`, and `s3`.

* ``filesystem_store_datadir``

  Directory where the filesystem store can write images to. This directory
  must be writeable by the user that runs ``glance-api``

.. todo::

Link to docs on the different stores when the documentation on Glance
stores is complete.
