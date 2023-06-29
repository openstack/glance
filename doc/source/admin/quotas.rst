..
      Copyright 2021 Red Hat, Inc.
      Licensed under the Apache License, Version 2.0 (the "License"); you may
      not use this file except in compliance with the License. You may obtain
      a copy of the License at

          http://www.apache.org/licenses/LICENSE-2.0

      Unless required by applicable law or agreed to in writing, software
      distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
      WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
      License for the specific language governing permissions and limitations
      under the License.

.. versionadded:: 23.0.0 (Xena)

   This functionality was first introduced in the 23.0.0 (Xena) release. Prior
   to this, only global resource limits were supported.

.. _quotas:

Per-Tenant Quotas
=================

Glance supports resource consumption quotas on tenants through the use
of Keystone's unified limits functionality. Resource limits are
*registered* in Keystone with suitable default values, and may be
overridden on a per-tenant basis. When a resource consumption attempt
is made in Glance, the current consumption is computed and compared
against the limit set in Keystone; the request is denied if the user
is over the specified limit.

Due to the design of Glance, most of the storage-focused quotas in
Glance are **soft limits**. Since Glance allows clients to stream image
data of unknown total size during an upload or import operation, it is
not possible to determine if quota has been exceeded until *after* the
operation has completed. Thus, a user is permitted to go over their
quota for a single operation, and then denied additional stored on
subsequent operations. There are object-focused quotas that can help
operators limit the damage caused by multiple large competing data
streams. Those details are covered below.

.. note::

  Glance also has legacy global resource limits that may be ignored if
  per-tenant quotas are enabled. Currently the ``user_storage_quota``
  limit will be ignored if per-tenant quotas are used.

See the Keystone docs for more information on `unified limits
<https://docs.openstack.org/keystone/latest/admin/unified-limits.html>`_.

Quota Resource Types
--------------------

Glance supports quota limits on multiple areas of resource
consumption. Limits are enforced at the time in which resource
consumption is attempted, so setting an existing user's quota for any
item below the current usage will only prevent them from consuming
*more* data until they free up space.

Total Image Size
~~~~~~~~~~~~~~~~

The ``image_size_total`` limit defines the maximum amount of storage
(in MiB) that the tenant may consume across all of their active
images. Images with multiple locations contribute to this count
according to the number of places the image is stored. Thus, if you
have a single 1GiB image stored in four locations, the usage will be
considered to be 4GiB.

Total Staging Size
~~~~~~~~~~~~~~~~~~

The :ref:`iir` function uses a two-step upload
process, whereby a user first uploads an image into the *staging*
store, and then subsequently *imports* the image to the final
destination(s). The staging store is generally local storage on the
API workers themselves, and thus is likely at somewhat of a premium,
compared to the bulk shared storage allocated for general images. The
``image_stage_total`` limit defines the total amount of staging space
that may be used. This should be set to a value sufficient to allow
a user to import one or more images at the same time, according to
your desired level of parallelism. It may be appropriate to provide
the user with a very generous ``image_size_total`` quota, but a
relatively restrictive ``image_stage_total`` allocation, effectively
limiting them to one image being imported at any given point.

Keep in mind that images being imported using the ``web-download``
method will need to fit within this allocation as well, as those are
first downloaded to the staging store before being imported to the
final destination(s). Images being copied from one store to another
using the ``copy-image`` method are similarly affected. Note that the
conventional image upload method does not stage the image, and thus is
not impacted by this limit.

Total Number of Images
~~~~~~~~~~~~~~~~~~~~~~

The ``image_count_total`` limit controls the maximum number of image
objects that the user may have, regardless of the individual or
collective sizes or impact to storage. This limit may be useful if you
wish to prevent users from taking thousands of small server snapshots
without ever deleting them.

Total Number of In-Progress Uploads
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Because Glance can not enforce storage-focused quotas until after a
stream is finished, it may be useful to limit the number of parallel
upload operations that can be in-progress at any single point. The
``image_count_uploading`` limit provides this control, and affects
conventional image upload, pre-import stage (including
``web-download`` and ``glance-direct``), as well as any ``copy-image``
operations that may be pending. It may be desirable to limit untrusted
users to a single in-progress image upload, which will limit the
amount of damage a malicious user may be able to inflict on your image
storage if they initiate multiple simultaneous unbounded upload
streams.

Quota Strategies
----------------

Below are a couple of use-case example strategies for different types
of deployments. In all cases, it makes sense for ``image_size_total``
and ``image_stage_total`` to be set to at least the size of the
largest image you expect a user to use. The global limit on a single
image (see configuration item ``image_size_cap``) may be relevant as
well. Users with an ``image_count_total`` of zero will be unable to
create any images, and with an ``image_count_uploading`` of zero will
be able to upload data to any images.

#. **Public cloud, users are billed per-byte**: In this case, it
   probably makes sense to set fairly high default quota limits for
   each of the above resource classes, allowing users to consume as
   much as they are willing to pay for. It still may be desirable to
   set ``image_stage_total`` to something modest to prevent
   overrunning limited staging space, if you have import enabled.

#. **Private cloud, trusted users are billed by quota**: In this case,
   each user pays for the amount of resource they are *allowed* to
   consume, instead of what they *are* consuming. Generally this
   involves billing total space, so ``image_size_total`` is set to
   their allotment, potentially with some upper bound on total images
   via ``image_count_total``. If they are somewhat trusted or
   low-impact customers, limiting the staging usage and upload count
   is probably not necessary, and can be left unbounded or set to some
   high upper bound.

#. **Private cloud, semi-trusted third party users**: This case may be
   similar to either of the above in terms of paying for allotment or
   strict usage. However, the lack of full trust may suggest limiting
   the total number of image uploads to something like 10% of their
   compute quota (to allow for snapshots) and limiting staging usage
   to enough for one or two image imports at a time.

Configuring Glance for Per-Tenant Quotas
----------------------------------------

#. Register quota limits (optional):

   .. include:: ../install/register-quotas.rst

#. Tell Glance to use Keystone quotas

.. include:: ../install/configure-quotas.rst
