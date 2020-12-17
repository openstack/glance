..
      Copyright 2013 OpenStack Foundation
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

.. _property-protections:

Property Protections
====================

There are two types of image properties in Glance:

* Core Properties, as specified by the image schema.

* Meta Properties, which are arbitrary key/value pairs that can be added to an
  image.

Access to meta properties through Glance's public API calls may be
restricted to certain sets of users, using a property protections configuration
file.

This document explains exactly how property protections are configured and what
they apply to.


Constructing a Property Protections Configuration File
------------------------------------------------------

A property protections configuration file follows the format of the Glance API
configuration file, which consists of sections, led by a ``[section]`` header
and followed by ``name = value`` entries.  Each section header is a regular
expression matching a set of properties to be protected.

.. note::

  Section headers must compile to a valid regular expression, otherwise
  glance api service will not start. Regular expressions
  will be handled by python's re module which is PERL like.

Each section describes four key-value pairs, where the key is one of
``create/read/update/delete``, and the value is a comma separated list of user
roles that are permitted to perform that operation in the Glance API.
**If any of the keys are not specified, then the glance api service will
not start successfully.**

In the list of user roles, ``@`` means all roles and ``!`` means no role.
**If both @ and ! are specified for the same rule then the glance api service
will not start**

.. note::

  Only one policy rule is allowed per property operation. **If multiple are
  specified, then the glance api service will not start.**

The path to the file should be specified in the ``[DEFAULT]`` section of
``glance-api.conf`` as follows.

::

  property_protection_file=/path/to/file

If this config value is not specified, property protections are not enforced.
**If the path is invalid, glance api service will not start successfully.**

The file may use either roles or policies to describe the property protections.
The config value should be specified in the ``[DEFAULT]`` section of
``glance-api.conf`` as follows.

::

  property_protection_rule_format=<roles|policies>

The default value for ``property_protection_rule_format`` is ``roles``.

Property protections are applied in the order specified in the configuration
file.  This means that if for example you specify a section with ``[.*]`` at
the top of the file, all proceeding sections will be ignored.

If a property does not match any of the given rules, all operations will be
disabled for all roles.

If an operation is misspelled or omitted, that operation will be disabled for
all roles.

Disallowing ``read`` operations will also disallow ``update/delete``
operations.

A successful HTTP request will return status ``200 OK``. If the user is not
permitted to perform the requested action, ``403 Forbidden`` will be returned.
