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


Configuring the Glance Client to use Keystone
---------------------------------------------

Once the Glance API and Registry servers have been configured to use Keystone, you
will need to configure the Glance client (``bin/glance``) to use Keystone as
well.

Just as with Nova, the specifying of authentication credentials is done via
environment variables. The only difference being that Glance environment
variables start with `OS_AUTH_` while Nova's begin with `NOVA_`.

If you already have Nova credentials present in your environment, you can use
the included tool, ``tools/nova_to_os_env.sh``, to create Glance-style
credentials. To use this tool, verify that Nova credentials are present by
running::

  $ env | grep NOVA_
  NOVA_USERNAME=<YOUR USERNAME>
  NOVA_API_KEY=<YOUR API KEY>
  NOVA_PROJECT_ID=<YOUR TENANT ID>
  NOVA_URL=<THIS SHOULD POINT TO KEYSTONE>
  NOVA_AUTH_STRATEGY=keystone

.. note::

  If `NOVA_AUTH_STRATEGY=keystone` is not present, add that to your ``novarc`` file
  and re-source it. If the command produces no output at all, then you will need
  to source your ``novarc``.

  Also, make sure that `NOVA_URL` points to Keystone and not the Nova API
  server. Keystone will return the address for Nova and Glance's API servers
  via its "service catalog".

Once Nova credentials are present in the environment, you will need to source
the conervsion script::

  $ source ./tools/nova_to_os_env.sh

The final step is to verify that the `OS_AUTH_` crednetials are present::

  $ env | grep OS_AUTH
  OS_AUTH_USER=<YOUR USERNAME>
  OS_AUTH_KEY=<YOUR API KEY>
  OS_AUTH_TENANT=<YOUR TENANT ID>
  OS_AUTH_URL=<THIS SHOULD POINT TO KEYSTONE>
  OS_AUTH_STRATEGY=keystone

Configuring the Glance servers to use Keystone
----------------------------------------------

Keystone is integrated with Glance through the use of middleware.  The
default configuration files for both the Glance API and the Glance
Registry use a single piece of middleware called ``context``, which
generates a request context without any knowledge of Keystone.  In
order to configure Glance to use Keystone, this ``context`` middleware
must be replaced with two other pieces of middleware: the
``authtoken`` middleware and the ``auth-context`` middleware, both of
which may be found in the Keystone distribution.  The ``authtoken``
middleware performs the Keystone token validation, which is the heart
of Keystone authentication.  On the other hand, the ``auth-context``
middleware performs the necessary tie-in between Keystone and Glance;
it is the component which replaces the ``context`` middleware that
Glance uses by default.

One other important concept to keep in mind is the *request context*.
In the default Glance configuration, the ``context`` middleware sets
up a basic request context; configuring Glance to use
``auth_context`` causes a more advanced context to be configured.  It
is also important to note that the Glance API and the Glance Registry
use two different context classes; this is because the registry needs
advanced methods that are not available in the default context class.
The implications of this will be obvious in the below example for
configuring the Glance Registry.

Configuring Glance API to use Keystone
--------------------------------------

Configuring Glance API to use Keystone is relatively straight
forward.  The first step is to ensure that declarations for the two
pieces of middleware exist in the ``glance-api-paste.ini``.  Here is
an example for ``authtoken``::

  [filter:authtoken]
  paste.filter_factory = keystone.middleware.auth_token:filter_factory
  service_protocol = http
  service_host = 127.0.0.1
  service_port = 5000
  auth_host = 127.0.0.1
  auth_port = 35357
  auth_protocol = http
  auth_uri = http://127.0.0.1:5000/
  admin_token = 999888777666

The actual values for these variables will need to be set depending on
your situation.  For more information, please refer to the Keystone
documentation on the ``auth_token`` middleware, but in short:

* Those variables beginning with ``service_`` are only needed if you
  are using a proxy; they define the actual location of Glance.  That
  said, they must be present.
* Except for ``auth_uri``, those variables beginning with ``auth_``
  point to the Keystone Admin service.  This information is used by
  the middleware to actually query Keystone about the validity of the
  authentication tokens.
* The ``auth_uri`` variable must point to the Keystone Auth service,
  which is the service users use to obtain Keystone tokens.  If the
  user does not have a valid Keystone token, they will be redirected
  to this URI to obtain one.
* The ``admin_token`` variable specifies the administrative token that
  Glance uses in its query to the Keystone Admin service.

The other piece of middleware needed for Glance API is the
``auth-context``::

  [filter:auth_context]
  paste.filter_factory = keystone.middleware.glance_auth_token:filter_factory

Finally, to actually enable using Keystone authentication, the
application pipeline must be modified.  By default, it looks like::

  [pipeline:glance-api]
  pipeline = versionnegotiation context apiv1app

(Your particular pipeline may vary depending on other options, such as
the image cache.)  This must be changed by replacing ``context`` with
``authtoken`` and ``auth-context``::

  [pipeline:glance-api]
  pipeline = versionnegotiation authtoken auth-context apiv1app

Configuring Glance Registry to use Keystone
-------------------------------------------

Configuring Glance Registry to use Keystone is also relatively
straight forward.  The same pieces of middleware need to be added
to ``glance-registry-paste.ini`` as are needed by Glance API;
see above for an example of the ``authtoken`` configuration.
There is a slight difference for the ``auth-context`` middleware,
which should look like this::

  [filter:auth-context]
  context_class = glance.registry.context.RequestContext
  paste.filter_factory = keystone.middleware.glance_auth_token:filter_factory

The ``context_class`` variable is needed to specify the
Registry-specific request context, which contains the extra access
checks used by the Registry.

Again, to enable using Keystone authentication, the appropriate
application pipeline must be selected.  By default, it looks like:

  [pipeline:glance-registry-keystone]
  pipeline = authtoken auth-context registryapp

To enable the above application pipeline, in your main ``glance-registry.conf``
configuration file, select the appropriate deployment flavor like so::

  [paste_deploy]
  flavor = keystone

Sharing Images With Others
--------------------------

It is possible to allow a private image to be shared with one or more
alternate tenants.  This is done through image *memberships*, which
are available via the `members` resource of images.  (For more
details, see :doc:`glanceapi`.)  Essentially, a membership is an
association between an image and a tenant which has permission to
access that image.  These membership associations may also have a
`can_share` attribute, which, if set to `true`, delegates the
authority to share an image to the named tenant.
