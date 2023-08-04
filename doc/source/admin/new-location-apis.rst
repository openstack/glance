..
      Copyright 2024 RedHat Inc.
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

.. _new_location_apis:

New Location APIs Support
=========================

Version 2.17 of the Image Service API introduces new Location API calls
which mitigate the security issues
`OSSN-0090 <https://wiki.openstack.org/wiki/OSSN/OSSN-0090>`_ and
`OSSN-0065 <https://wiki.openstack.org/wiki/OSSN/OSSN-0065>`_.

Below are the 2 new locations api glance has introduced in 2023.2 cycle,


Add Location
------------

Add location API is introduced to add the location to an image.

Add location operation is only allowed for service to service interaction
and image owner, when image is in ``queued`` state only. Attempt to add
location for image in other states will be rejected. This is done in order
to prevent malicious users from modifying the image location again and again
since the location added for the first time is the correct one as far as
Glance is concerned.

The use case for old location API for consumers (nova and cinder) is to
create images efficiently with an optimized workflow. This workflow avoids
the hash calculation steps which exists in the generic image create workflow
of glance leading to missing checksum and hash information for those images.
As a result, those images were never cached, as a checksum was required
to validate whether the image is completely cached or not. Adding this
mechanism to calculate the checksum and hash for the image has not only
resolve this issue but it will also improve caching operations since
the checksum of the original and a cached image is compared only when
the entire image was downloaded in the cache.

As the hashing calculation and its verification are time-consuming, we
provide a configuration option to enable/disable this operation. The new
configuration option ``do_secure_hash`` has been introduced to control this
operation. The value of ``do_secure_hash`` is ``True`` by default. This
operation can be disabled by turning this flag to ``False``.
For similar reasons, the hashing calculation will be performed in the
background so that consumers or clients need not to wait for its completion.
If the hash calculation fails, we have a retry mechanism that will retry the
operation as per the value defined of the configuration option
``http_retries`` in the glance-api.conf file. The default value is ``3``.
The operation will be silently ignored if it fails even after the maximum
retries as defined with the ``http_retries`` configuration option.

Similar to the old location API, users (not consumers like Nova or Cinder) can
also pass hashing values as an input to this new API using validation_data,
either it should be supplied from glance client, as a command line argument
or should be provided in the request body when doing direct API request.
In this case, if hashing is enabled in the deployment(i.e., ``do_secure_hash``
is True) then it will validate the calculated hash values with validation_data
and marks the operation as failed if there is a difference. If hashing is
disabled, (i.e., ``do_secure_hash`` is False) then values provided in
validation_data will be set directly to the image.

If hashing is disabled for this API, then we will have an active image,
but again it will fail to cache, so Glance recommends consumers like Nova
and Cinder as well as normal users should keep do_secure_hash enabled.

.. note:: Usage of this API for end users is only allowed if http
          store is enabled in the deployment.

.. note:: In case of ``http`` store, if bad value is passed to
          ``os_hash_value`` in validation data, image remains in
          ``queued`` state as verification of validation_data fails
          which is expected but it stores location of the image which
          should to be popped out instead. The location doesn't get
          deleted because deletion of location is not allowed for ``http``
          store. Here image needs to be deleted as it's of no use.


Get Locations
-------------

Get locations API will return the list of the locations associated to the
image.

This API is introduced to get the locations associated to an image to
abstract the location information from end users so that they are not able
to see where exactly the image is stored.

Get locations operation is strictly allowed for service to service interaction
only, meaning only consumers like nova, cinder etc. will be able to access this
API.
