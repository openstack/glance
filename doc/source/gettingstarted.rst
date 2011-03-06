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
complies with this API (``glance-registry``).

For more details on Glance's architecture see :doc:`here <architecture>`. For
more information on what a Glance registry server is, see
:doc:`here <registries>`.
