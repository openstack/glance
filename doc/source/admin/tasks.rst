..
      Copyright 2015 OpenStack Foundation
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

.. _tasks:

Tasks
=====

Conceptual Overview
-------------------

Image files can be quite large, and processing images (converting an image from
one format to another, for example) can be extremely resource intensive.
Additionally, a one-size-fits-all approach to processing images is not
desirable.  A public cloud will have quite different security concerns than,
for example, a small private cloud run by an academic department in which all
users know and trust each other.  Thus a public cloud deployer may wish to run
various validation checks on an image that a user wants to bring in to the
cloud, whereas the departmental cloud deployer may view such processing as a
waste of resources.

To address this situation, Glance contains *tasks*.  Tasks are intended to
offer end users a front end to long running asynchronous operations -- the type
of operation you kick off and don't expect to finish until you've gone to the
coffee shop, had a pleasant chat with your barista, had a coffee, had a
pleasant walk home, etc.  The asynchronous nature of tasks is emphasized up
front in order to set end user expectations with respect to how long the task
may take (hint: longer than other Glance operations).  Having a set of
operations performed by tasks allows a deployer flexibility with respect to how
many operations will be processed simultaneously, which in turn allows
flexibility with respect to what kind of resources need to be set aside for
task processing.  Thus, although large cloud deployers are certainly interested
in tasks for the alternative custom image processing workflow they enable,
smaller deployers find them useful as a means of controlling resource
utilization.

An additional reason tasks have been introduced into Glance is to support
Glance's role in the OpenStack ecosystem.  Glance provides cataloging, storage,
and delivery of virtual machine images.  As such, it needs to be responsive to
other OpenStack components.  Nova, for instance, requests images from Glance in
order to boot instances; it uploads images to Glance as part of its workflow
for the Nova image-create action; and it uses Glance to provide the data for
the image-related API calls that are defined in the Compute API that Nova
instantiates.  It is necessary to the proper functioning of an OpenStack cloud
that these synchronous operations not be compromised by excess load caused by
non-essential functionality such as image import.

By separating the tasks resource from the images resource in the Images API,
it's easier for deployers to allocate resources and route requests for tasks
separately from the resources required to support Glance's service role.  At
the same time this separation avoids confusion for users of an OpenStack cloud.
Responses to requests to ``/v2/images`` should return fairly quickly, while
requests to ``/v2/tasks`` may take a while.

In short, tasks provide a common API across OpenStack installations for users
of an OpenStack cloud to request image-related operations, yet at the same time
tasks are customizable for individual cloud providers.

Conceptual Details
------------------

A Glance task is a request to perform an asynchronous image-related
operation. The request results in the creation of a *task resource* that
can be polled for information about the status of the operation.

A specific type of resource distinct from the traditional Glance image resource
is appropriate here for several reasons:

* A dedicated task resource can be developed independently of the traditional
  Glance image resource, both with respect to structure and workflow.

* There may be multiple tasks (for example, image export or image conversion)
  operating on an image simultaneously.

* A dedicated task resource allows for the delivery to the end user of clear,
  detailed error messages specific to the particular operation.

* A dedicated task resource respects the principle of least surprise.  For
  example, an import task does not create an image in Glance until it's clear
  that the bits submitted pass the deployer's tests for an allowable image.

Upon reaching a final state (``success`` or ``error``) a task resource is
assigned an expiration datetime that's displayed in the ``expires_at`` field.
(The time between final state and expiration is configurable.)  After that
datetime, the task resource is subject to being deleted.  The result of the
task (for example, an imported image) will still exist.

For details about the defined task statuses, please see :ref:`task-statuses`.

Tasks expire eventually because there's no reason to keep them around,
as the user will have the result of the task, which was the point of creating
the task in the first place.  The reason tasks aren't instantly deleted is that
there may be information contained in the task resource that's not easily
available elsewhere.  (For example, a successful import task will eventually
result in the creation of an image in Glance, and it would be useful to know
the UUID of this image.  Similarly, if the import task fails, we want to give
the end user time to read the task resource to analyze the error message.)

Task Entities
-------------

A task entity is represented by a JSON-encoded data structure defined by the
JSON schema available at ``/v2/schemas/task``.

A task entity has an identifier (``id``) that is guaranteed to be unique within
the endpoint to which it belongs. The id is used as a token in request URIs to
interact with that specific task.

In addition to the usual properties you'd expect (for example, ``created_at``,
``self``, ``type``, ``status``, ``updated_at``, etc.),
tasks have these properties of interest:

* ``input``: this is defined to be a JSON blob, the exact content of which will
  depend upon the requirements set by the specific cloud deployer.  The intent
  is that each deployer will document these requirements for end users.

* ``result``: this is also defined to be a JSON blob, the content of which will
  be documented by each cloud deployer.  The ``result`` element will be null
  until the task has reached a final state, and if the final status is
  ``failure``, the result element remains null.

* ``message``: this string field is expected to be null unless the task has
  entered ``failure`` status.  At that point, it contains an informative
  human-readable message concerning the reason(s) for the task failure.
