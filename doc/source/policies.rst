..
      Copyright 2012 OpenStack, LLC
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

Policies
========

Glance's API calls may be restricted to certain sets of users using
a Policy configuration file.

This document explains exactly how policies work and how the policy
configuration file is constructed.

Basics
------

A policy is composed of a set of rules that are used by the Policy "Brain"
in determining if a particular action may be performed by a particular
role.

Constructing a Policy Configuration File
----------------------------------------

Policy configuration files are simply serialized JSON dictionaries that
contain sets of rules. Each top-level key is the name of a rule. Each rule
is a string that describes an action that may be performed in the Glance API.

The actions that may have a rule enforced on them are:

* ``get_images`` - Allowed to call the ``GET /images`` and
  ``GET /images/detail`` API calls

* ``get_image`` - Allowed to call the ``HEAD /images/<IMAGE_ID>`` and
  ``GET /images/<IMAGE_ID>`` API calls

* ``add_image`` - Allowed to call the ``POST /images`` API call

* ``modify_image`` - Allowed to call the ``PUT /images/<IMAGE_ID>`` API call

* ``delete_image`` - Allowed to call the ``DELETE /images/<IMAGE_ID>`` API call

To limit an action to a particular role or roles, you list the roles like so ::

  {
    "delete_image": ["role:admin", "role:superuser"]
  }

The above would add a rule that only allowed users that had roles of either
"admin" or "superuser" to delete an image.

Examples
--------

Example 1. (The default policy configuration)

 ::

  {
      "default": []
  }

Note that an empty JSON list means that all methods of the
Glance API are callable by anyone.

Example 2. Disallow modification calls to non-admins

 ::

  {
      "default": [],
      "add_image": ["role:admin"],
      "modify_image": ["role:admin"],
      "delete_image": ["role:admin"]
  }
