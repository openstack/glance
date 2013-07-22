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

Notifications
=============

Notifications can be generated for several events in the image lifecycle.
These can be used for auditing, troubleshooting, etc.

Strategies
----------

* logging

  This strategy uses the standard Python logging infrastructure with
  the notifications ending up in file specificed by the log_file
  configuration directive.

* rabbit

  This strategy sends notifications to a rabbitmq queue. This can then
  be processed by other services or applications.

* qpid

  This strategy is similar to rabbit. It sends notifications to an AMQP
  message queue via Qpid.

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
