..
      Licensed under the Apache License, Version 2.0 (the "License"); you may
      not use this file except in compliance with the License. You may obtain
      a copy of the License at

          http://www.apache.org/licenses/LICENSE-2.0

      Unless required by applicable law or agreed to in writing, software
      distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
      WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
      License for the specific language governing permissions and limitations
      under the License.

:tocdepth: 2

======================
Image Service Versions
======================

.. rest_expand_all::

.. include:: versions.inc

Version History
***************

**Train changes**

- version 2.9 is CURRENT
- version 2.8 is SUPPORTED
- version 2.7 is SUPPORTED

**Rocky changes**

- version 2.8 is EXPERIMENTAL
- version 2.7 is CURRENT
- version 1.1 is DELETED
- version 1.0 is DELETED

**Queens changes**

- version 2.6 is CURRENT
- version 2.5 is SUPPORTED

**Pike changes**

- version 2.6 is EXPERIMENTAL

**Ocata changes**

- version 2.5 is CURRENT
- version 2.4 is SUPPORTED

**Newton changes**

- version 2.4 is CURRENT
- version 2.3 is SUPPORTED
- version 1.1 is DEPRECATED
- version 1.0 is DEPRECATED

**Kilo changes**

- version 2.3 is CURRENT
- version 1.1 is SUPPORTED

**Havana changes**

- version 2.2 is CURRENT
- version 2.1 is SUPPORTED

**Grizzly changes**

- version 2.1 is CURRENT
- version 2.0 is SUPPORTED

**Folsom changes**

- version 2.0 is CURRENT

**Diablo changes**

- version 1.1 is CURRENT
- version 1.0 is SUPPORTED

**Bexar changes**

- version 1.0 is CURRENT

What happened to the v1 API?
****************************

The Image Service API version 1 was DEPRECATED in the OpenStack Newton release
and removed during the development cycle for the Rocky release.  The last
OpenStack release containing the Image Service API v1 was the Queens release.

The source files for the Image Service API Reference are contained in the
OpenStack Glance source code repository.  The files for the version 1 reference
are no longer in the current development branch, but they may still be found
in the stable branches in the repository.

If you would like to consult the Image Service API version 1 Reference, you can
check out a stable branch from the repository, build it locally, and use a web
browser to read the generated HTML files.

Building the API Reference
~~~~~~~~~~~~~~~~~~~~~~~~~~

You'll need to have the following installed on your system:

* python
* git
* tox

Then:

1. Go to the Glance repository mirror on GitHub:
   https://github.com/openstack/glance

2. Clone the repository to your local system.

3. Checkout the **stable/queens** branch of glance.

4. From the root directory, use tox to build the api-reference:

   ``tox -e api-ref``

5. The HTML version of the Image Service API Reference will be located in the
   ``api-ref/build/html`` directory.  Use your browser to open the
   ``index.html`` file in that directory and you'll be able to browse the API
   Reference.
