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

Image Registries
================

Image metadata made available through Glance can be stored in image
`registries`. Image registries are any web service that adheres to the
Glance REST-like API for image metadata.

Glance comes with a server program ``glance-registry`` that acts
as a reference implementation of a Glance Registry.

Using ``glance-registry``, the Glance Registry reference implementation
-----------------------------------------------------------------------

As mentioned above, ``glance-registry`` is the reference registry
server implementation that ships with Glance. It uses a SQL database
to store information about an image, and publishes this information
via an HTTP/REST-like interface.

Starting the server
*******************

Starting the Glance registry server is trivial. Simply call the program
from the command line, as the following example shows::

  $> glance-registry
  (5588) wsgi starting up on http://0.0.0.0:9191/

Configuring the server
**********************

There are a few options that can be supplied to the registry server when
starting it up:

* ``verbose``

  Show more verbose/debugging output

* ``sql_connection``

  A proper SQLAlchemy connection string as described `here <http://www.sqlalchemy.org/docs/05/reference/sqlalchemy/connections.html?highlight=engine#sqlalchemy.create_engine>`_

* ``registry_host``

  Address of the host the registry runs on. Defaults to 0.0.0.0.

* ``registry_port``

  Port the registry server listens on. Defaults to 9191.

Glance Registry API
-------------------

Any web service that publishes an API that conforms to the following
REST-like API specification can be used by Glance as a registry.

API in Summary
**************

The following is a brief description of the Glance API::

  GET     /images         Return brief information about public images
  GET     /images/detail  Return detailed information about public images
  GET     /images/<ID>    Return metadata about an image in HTTP headers
  POST    /images         Register metadata about a new image
  PUT     /images/<ID>    Update metadata about an existing image
  DELETE  /images/<ID>    Remove an image's metadata from the registry

Examples
********

.. todo::  Complete examples for Glance registry API
