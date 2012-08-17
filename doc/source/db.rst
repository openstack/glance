..
      Copyright 2012 OpenStack, LLC
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

Database Management
===================

The default metadata driver for glance uses sqlalchemy, which implies there
exists a backend database which must be managed. The ``glance-manage`` binary
provides a set of commands for making this easier.


Initializing an Empty Database
------------------------------

    glance-manage db_sync

This will take an empty database and create the necessary tables.


Determining the Database Version
--------------------------------

    glance-manage db_version

This will print the version of a glance database.


Upgrading an Existing Database
------------------------------

    glance-manage db_sync <VERSION>

This will take an existing database and upgrade it to the specified VERSION.


Downgrading an Existing Database
--------------------------------

    glance-manage downgrade <VERSION>

This will downgrade an existing database from the current version to the
specified VERSION.

