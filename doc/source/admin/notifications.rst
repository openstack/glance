..
      Copyright 2011-2013 OpenStack Foundation
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

.. _notifications:

Notifications
=============

Notifications can be generated for several events in the image lifecycle.
These can be used for auditing, troubleshooting, etc.

Notification Drivers
--------------------

* log

  This driver uses the standard Python logging infrastructure with
  the notifications ending up in file specified by the log_file
  configuration directive.

* messaging

  This strategy sends notifications to a message queue configured
  using oslo.messaging configuration options.

* noop

  This strategy produces no notifications. It is the default strategy.

Notification Types
------------------

* ``image.create``

  Emitted when an image record is created in Glance.  Image record creation is
  independent of image data upload.

* ``image.prepare``

  Emitted when Glance begins uploading image data to its store.

* ``image.upload``

  Emitted when Glance has completed the upload of image data to its store.

* ``image.activate``

  Emitted when an image goes to `active` status.  This occurs when Glance
  knows where the image data is located.

* ``image.send``

  Emitted upon completion of an image being sent to a consumer.

* ``image.update``

  Emitted when an image record is updated in Glance.

* ``image.delete``

  Emitted when an image deleted from Glance.

* ``task.run``

  Emitted when a task is picked up by the executor to be run.

* ``task.processing``

  Emitted when a task is sent over to the executor to begin processing.

* ``task.success``

  Emitted when a task is successfully completed.

* ``task.failure``

  Emitted when a task fails.

Content
-------

Every message contains a handful of attributes.

* message_id

  UUID identifying the message.

* publisher_id

  The hostname of the glance instance that generated the message.

* event_type

  Event that generated the message.

* priority

  One of WARN, INFO or ERROR.

* timestamp

  UTC timestamp of when event was generated.

* payload

  Data specific to the event type.

Payload
-------

* image.send

  The payload for INFO, WARN, and ERROR events contain the following:

  image_id
    ID of the image (UUID)
  owner_id
    Tenant or User ID that owns this image (string)
  receiver_tenant_id
    Tenant ID of the account receiving the image (string)
  receiver_user_id
    User ID of the account receiving the image (string)
  destination_ip
    The receiver's IP address to which the image was sent (string)
  bytes_sent
    The number of bytes actually sent

* image.create

  For INFO events, it is the image metadata.
  WARN and ERROR events contain a text message in the payload.

* image.prepare

  For INFO events, it is the image metadata.
  WARN and ERROR events contain a text message in the payload.

* image.upload

  For INFO events, it is the image metadata.
  WARN and ERROR events contain a text message in the payload.

* image.activate

  For INFO events, it is the image metadata.
  WARN and ERROR events contain a text message in the payload.

* image.update

  For INFO events, it is the image metadata.
  WARN and ERROR events contain a text message in the payload.

* image.delete

  For INFO events, it is the image id.
  WARN and ERROR events contain a text message in the payload.

* task.run

  The payload for INFO, WARN, and ERROR events contain the following:

  task_id
    ID of the task (UUID)
  owner
    Tenant or User ID that created this task (string)
  task_type
    Type of the task. Example, task_type is "import". (string)
  status,
    status of the task. Status can be "pending", "processing",
    "success" or "failure". (string)
  task_input
    Input provided by the user when attempting to create a task. (dict)
  result
    Resulting output from a successful task. (dict)
  message
    Message shown in the task if it fails. None if task succeeds. (string)
  expires_at
    UTC time at which the task would not be visible to the user. (string)
  created_at
    UTC time at which the task was created. (string)
  updated_at
    UTC time at which the task was latest updated. (string)

  The exceptions are:-
    For INFO events, it is the task dict with result and message as None.
    WARN and ERROR events contain a text message in the payload.

* task.processing

  For INFO events, it is the task dict with result and message as None.
  WARN and ERROR events contain a text message in the payload.

* task.success

  For INFO events, it is the task dict with message as None and result is a
  dict.
  WARN and ERROR events contain a text message in the payload.

* task.failure

  For INFO events, it is the task dict with result as None and message is
  text.
  WARN and ERROR events contain a text message in the payload.
