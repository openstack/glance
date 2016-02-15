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

==================
Basic architecture
==================

OpenStack Glance has a client-server architecture that provides a REST API
to the user through which requests to the server can be performed.

A Glance Domain Controller manages the internal server operations
that is divided into layers. Specific tasks are implemented
by each layer.

All the file (Image data) operations are performed using
glance_store library, which is responsible for interaction with external
storage back ends and (or) local filesystem(s). The glance_store library
provides a uniform interface to access the backend stores.

Glance uses a central database (Glance DB) that is shared amongst all
the components in the system and is sql-based by default. Other types
of database backends are somewhat supported and used by operators
but are not extensively tested upstream.

.. figure:: /images/architecture.png
   :figwidth: 100%
   :align: center
   :alt: OpenStack Glance Architecture

.. centered:: Image 1. OpenStack Glance Architecture

Following components are present in the Glance architecture:

* **A client** - any application that makes use of a Glance server.

* **REST API** - Glance functionalities are exposed via REST.

* **Database Abstraction Layer (DAL)** - an application programming interface
(API) that unifies the communication between Glance and databases.

* **Glance Domain Controller** - middleware that implements the main
Glance functionalities such as authorization, notifications, policies,
database connections.

* **Glance Store** - used to organize interactions between Glance and various
data stores.

* **Registry Layer** - optional layer that is used to organise secure
communication between the domain and the DAL by using a separate service.
