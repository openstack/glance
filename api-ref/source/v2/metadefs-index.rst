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

:tocdepth: 3

=============================================
Metadata Definitions Service API v2 (CURRENT)
=============================================

.. rest_expand_all::

Metadefs
********

General information
~~~~~~~~~~~~~~~~~~~

The Metadata Definitions Service ("metadefs", for short) provides a common API
for vendors, operators, administrators, services, and users to meaningfully
define available key:value pairs that can be used on different types of cloud
resources (for example, images, artifacts, volumes, flavors, aggregates,
and other resources).

To get you started, Glance contains a default catalog of metadefs that may be
installed at your site; see the `README
<https://github.com/openstack/glance/tree/master/etc/metadefs/README>`_ in the
code repository for details.

Once a common catalog of metadata definitions has been created, the catalog is
available for querying through the API.  Note that this service stores only the
*catalog*, because metadefs are meta-metadata.  Metadefs provide information
*about* resource metadata, but do not themselves serve as actual metadata.

Actual key:value pairs are stored on the resources to which they apply using
the metadata facilities provided by the appropriate API.  (For example, the
Images API would be used to put specific key:value pairs on a virtual machine
image.)

A metadefs definition includes a property's key, its description, its
constraints, and the resource types to which it can be associated.  See
`Metadata Definition Concepts
<https://docs.openstack.org/glance/latest/user/metadefs-concepts.html>`_ in the
Glance Developer documentation for more information.

.. note:: By default, only admins can manipulate the data exposed by
          this API, but all users may list and show public
          resources. This changed from a default of "open to all" in
          the Wallaby release.

.. include:: metadefs-namespaces.inc
.. include:: metadefs-resourcetypes.inc
.. include:: metadefs-namespaces-objects.inc
.. include:: metadefs-namespaces-properties.inc
.. include:: metadefs-namespaces-tags.inc
.. include:: metadefs-schemas.inc
