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

Image Statuses
==============

Images in Glance can be in one of four statuses:

* ``queued``

  Denotes an image identifier has been reserved for an image in Glance (or
  more specifically, reserved in the registries Glance uses) and that no
  actual image data has yet to be uploaded to Glance

* ``saving``

  Denotes that an image's raw image data is currently being uploaded to
  Glance

* ``active``

  Denotes an image that is fully available in Glance

* ``killed``

  Denotes that an error occurred during the uploading of an image's data,
  and that the image is not readable


.. note::

  When an image is registered with a call to `POST /images` and there
  is an `x-image-meta-location` header present, that image will never be in
  the `saving` status (as the image data is already available in some other
  location)
