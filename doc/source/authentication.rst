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

Glance Authentication With Keystone
===================================

Glance may optionally be integrated with Keystone.  Setting this up is
relatively straightforward: the Keystone distribution includes the
requisite middleware and examples of appropriately modified
``glance-api.conf`` and ``glance-registry.conf`` configuration files
in the ``examples/paste`` directory.  Once you have installed Keystone
and edited your configuration files, newly created images will have
their `owner` attribute set to the tenant of the authenticated users,
and the `is_public` attribute will cause access to those images for
which it is `false` to be restricted to only the owner.

  .. note::

  The exception is those images for which `owner` is set to `null`,
  which may only be done by those users having the ``Admin`` role.
  These images may still be accessed by the public, but will not
  appear in the list of public images.  This allows the Glance
  Registry owner to publish images for beta testing without allowing
  those images to show up in lists, potentially confusing users.


Sharing Images With Others
--------------------------

It is possible to allow a private image to be shared with one or more
alternate tenants.  This is done through image *memberships*, which
are available via the `members` resource of images.  (For more
details, see :ref:`glanceapi`.)  Essentially, a membership is an
association between an image and a tenant which has permission to
access that image.  These membership associations may also have a
`can_share` attribute, which, if set to `true`, delegates the
authority to share an image to the named tenant.
