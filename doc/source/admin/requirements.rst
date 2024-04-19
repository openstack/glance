..
      Copyright 2016-present OpenStack Foundation
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

Requirements
============


External Requirements Affecting Glance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Like other OpenStack projects, Glance uses some external libraries for a subset
of its features. Some examples include the ``qemu-img`` utility used by the
tasks feature, ``pydev`` to debug using popular IDEs, ``python-xattr`` for
Image Cache using "xattr" driver.

On the other hand, if ``dnspython`` is installed in the environment, Glance
provides a workaround to make it work with IPV6.

Additionally, some libraries like ``xattr`` are not compatible when
using Glance on Windows (see :ref:`the documentation on config options
affecting the Image Cache <configuring>`).


Guideline to include your requirement in the requirements.txt file
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

As described above, we don't include all the possible requirements needed by
Glance features in the source tree requirements file. So, when an operator
decides to use an **advanced feature** in Glance, we ask them to check the
documentation/guidelines for those features to set up the feature in a workable
way. In order to reduce the operator pain, the development team likes to work
with different operators to figure out when a popular feature should have its
dependencies included in the requirements file. However, there's a tradeoff in
including more of requirements in source tree as it becomes more painful for
packagers. So, it is a bit of a haggle among different stakeholders and a
judicious decision is taken by the project PTL or release liaison to determine
the outcome.

To simplify the identification of an **advanced feature** in Glance we can
think of it as something not being used and deployed by most of the
upstream/known community members.

To name a few features that have been identified as advanced:

* glance tasks
* image signing
* image prefetcher
* glance db purge utility
* image locations


Steps to include your requirement in the requirements.txt file
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. First step is to propose a change against the ``openstack/requirements``
project to include the requirement(s) as a part of ``global-requirements`` and
``upper-constraints`` files.

2. If your requirement is not a part of the project, you will have to propose a
change adding that requirement to the requirements.txt file in Glance. Please
include a ``Depends-On: <ChangeID>`` flag in the commit message, where the
``ChangeID`` is the gerrit ID of corresponding change against
``openstack/requirements`` project.

3. A sync bot then syncs the global requirements into project requirements on a
regular basis, so any updates to the requirements are synchronized on a timely
basis.
