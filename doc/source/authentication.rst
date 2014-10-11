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

Authentication With Keystone
============================

Glance may optionally be integrated with Keystone.  Setting this up is
relatively straightforward, as the Keystone distribution includes the
necessary middleware. Once you have installed Keystone
and edited your configuration files, newly created images will have
their `owner` attribute set to the tenant of the authenticated users,
and the `is_public` attribute will cause access to those images for
which it is `false` to be restricted to only the owner, users with
admin context, or tenants/users with whom the image has been shared.


Configuring the Glance servers to use Keystone
----------------------------------------------

Keystone is integrated with Glance through the use of middleware. The
default configuration files for both the Glance API and the Glance
Registry use a single piece of middleware called ``unauthenticated-context``,
which generates a request context containing blank authentication
information. In order to configure Glance to use Keystone, the
``authtoken`` and ``context`` middlewares must be deployed in place of the
``unauthenticated-context`` middleware. The ``authtoken`` middleware performs
the authentication token validation and retrieves actual user authentication
information. It can be found in the Keystone distribution.

Configuring Glance API to use Keystone
--------------------------------------

Configuring Glance API to use Keystone is relatively straight
forward.  The first step is to ensure that declarations for the two
pieces of middleware exist in the ``glance-api-paste.ini``.  Here is
an example for ``authtoken``::

  [filter:authtoken]
  paste.filter_factory = keystonemiddleware.auth_token:filter_factory
  identity_uri = http://127.0.0.1:35357
  admin_user = glance_admin
  admin_tenant_name = service_admins
  admin_password = password1234

The actual values for these variables will need to be set depending on
your situation.  For more information, please refer to the Keystone
documentation on the ``auth_token`` middleware, but in short:

* The ``identity_uri`` variable points to the Keystone Admin service.
  This information is used by the middleware to actually query Keystone about
  the validity of the authentication tokens.
* The admin auth credentials (``admin_user``, ``admin_tenant_name``,
  ``admin_password``) will be used to retrieve an admin token. That
  token will be used to authorize user tokens behind the scenes.

Finally, to actually enable using Keystone authentication, the
application pipeline must be modified.  By default, it looks like::

  [pipeline:glance-api]
  pipeline = versionnegotiation unauthenticated-context apiv1app

Your particular pipeline may vary depending on other options, such as
the image cache. This must be changed by replacing ``unauthenticated-context``
with ``authtoken`` and ``context``::

  [pipeline:glance-api]
  pipeline = versionnegotiation authtoken context apiv1app

Configuring Glance Registry to use Keystone
-------------------------------------------

Configuring Glance Registry to use Keystone is also relatively
straight forward.  The same middleware needs to be added
to ``glance-registry-paste.ini`` as was needed by Glance API;
see above for an example of the ``authtoken`` configuration.

Again, to enable using Keystone authentication, the appropriate
application pipeline must be selected.  By default, it looks like::

  [pipeline:glance-registry-keystone]
  pipeline = authtoken context registryapp

To enable the above application pipeline, in your main ``glance-registry.conf``
configuration file, select the appropriate deployment flavor by adding a
``flavor`` attribute in the ``paste_deploy`` group::

  [paste_deploy]
  flavor = keystone

.. note::
  If your authentication service uses a role other than ``admin`` to identify
  which users should be granted admin-level privileges, you must define it
  in the ``admin_role`` config attribute in both ``glance-registry.conf`` and
  ``glance-api.conf``.
