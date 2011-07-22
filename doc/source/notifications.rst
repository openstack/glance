..
      Copyright 2011 OpenStack, LLC
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

Notifications can be generated for each upload, update or delete image
event. These can be used for auditing, troubleshooting, etc.

Strategies
----------

* logging

  This strategy uses the standard Python logging infrastructure with
  the notifications ending up in file specificed by the log_file
  configuration directive.

* rabbit

  This strategy sends notifications to a rabbitmq queue. This can then
  be processed by other services or applications.

* noop

  This strategy produces no notifications. It is the default strategy.

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

WARN and ERROR events contain a text message in the payload.

* image.upload

  For INFO events, it is the image metadata.

* image.update

  For INFO events, it is the image metadata.

* image.delete

  For INFO events, it is the image id.
