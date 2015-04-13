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

OpenStack Glance has a client-server architecture and provides a user
REST API through which requests to the server are performed.

Internal server operations are managed by a Glance Domain Controller
divided into layers. Each layer implements its own task.

All the files operations are performed using glance_store library
which is responsible for interaction with external storage back ends or
local filesystem, and provides a uniform interface to access.

Glance uses an sql-based central database (Glance DB) that is shared
with all the components in the system.

.. figure:: /images/architecture.png
   :figwidth: 100%
   :align: center
   :alt: OpenStack Glance Architecture

.. centered:: Image 1. OpenStack Glance Architecture

The Glance architecture consists of several components:

* **A client** - any application that uses Glance server.

* **REST API** - exposes Glance functionality via REST.

* **Database Abstraction Layer (DAL)** - an application programming interface
  which unifies the communication between Glance and databases.

* **Glance Domain Controller** - middleware that implements the main
  Glance functionalities: authorization, notifications, policies,
  database connections.

* **Glance Store** - organizes interactions between Glance and various
  data stores.

* **Registry Layer** - optional layer organizing secure communication between
  the domain and the DAL by using a separate service.
