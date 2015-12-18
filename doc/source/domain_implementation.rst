..
      Copyright 2016 OpenStack Foundation
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
Glance domain model implementation
==================================

Gateway and basic layers
~~~~~~~~~~~~~~~~~~~~~~~~

The domain model contains the following layers:

#. :ref:`authorization`
#. :ref:`notifier`
#. :ref:`property`
#. :ref:`policy`
#. :ref:`quota`
#. :ref:`location`
#. :ref:`database`

The schema below shows a stack that contains the Image domain layers and
their locations:

.. figure:: /images/glance_layers.png
   :figwidth: 100%
   :align: center
   :alt: Image domain layers

.. _authorization:

Authorization
-------------

The first layer of the domain model provides a verification of whether an
image itself or its property can be changed. An admin or image owner can
apply the changes. The information about a user is taken from the request
``context`` and is compared with the image ``owner``. If the user cannot
apply a change, a corresponding error message appears.

.. _property:

Property protection
-------------------

The second layer of the domain model is optional. It becomes available if you
set the ``property_protection_file`` parameter in the Glance configuration
file.

There are two types of image properties in Glance:

* *Core properties*, as specified in the image schema
* *Meta properties*, which are the arbitrary key/value pairs that can be added
  to an image

The property protection layer manages access to the meta properties
through Glance’s public API calls. You can restrict the access in the
property protection configuration file.

.. _notifier:

Notifier
--------

On the third layer of the domain model, the following items are added to
the message queue:

#. Notifications about all of the image changes
#. All of the exceptions and warnings that occurred while using an image

.. _policy:

Policy
------

The fourth layer of the domain model is responsible for:

#. Defining access rules to perform actions with an image. The rules are
   defined in the :file:`etc/policy.json` file.
#. Monitoring of the rules implementation.

.. _quota:

Quota
-----

On the fifth layer of the domain model, if a user has an admin-defined size
quota for all of his uploaded images, there is a check that verifies whether
this quota exceeds the limit during an image upload and save:

* If the quota does not exceed the limit, then the action to add an image
  succeeds.
* If the quota exceeds the limit, then the action does not succeed and a
  corresponding error message appears.

.. _location:

Location
--------

The sixth layer of the domain model is used for interaction with the store via
the ``glance_store`` library, like upload and download, and for managing an
image location. On this layer, an image is validated before the upload. If
the validation succeeds, an image is written to the ``glance_store`` library.

This sixth layer of the domain model is responsible for:

#. Checking whether a location URI is correct when a new location is added
#. Removing image data from the store when an image location is changed
#. Preventing image location duplicates

.. _database:

Database
--------

On the seventh layer of the domain model:

* The methods to interact with the database API are implemented.
* Images are converted to the corresponding format to be recorded in the
  database. And the information received from the database is
  converted to an Image object.
