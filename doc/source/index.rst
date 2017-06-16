..
      Copyright 2010 OpenStack Foundation
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

==================================
Welcome to Glance's documentation!
==================================

The Image service (glance) project provides a service where users can upload
and discover data assets that are meant to be used with other services.
This currently includes images and metadata definitions.

Glance image services include discovering, registering, and
retrieving virtual machine (VM) images. Glance has a RESTful API that allows
querying of VM image metadata as well as retrieval of the actual image.

.. include:: deprecation-note.inc

VM images made available through Glance can be stored in a variety of
locations from simple filesystems to object-storage systems like the
OpenStack Swift project.

.. toctree::
   :maxdepth: 2

   user/index
   admin/index
   install/index
   configuration/index
   cli/index
   contributor/index

.. toctree::
   :maxdepth: 1

   glossary
