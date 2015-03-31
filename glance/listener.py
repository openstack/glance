# Copyright (c) 2014 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from oslo.config import cfg
from oslo import messaging
from oslo_log import log as logging
import stevedore

from glance import i18n
from glance.openstack.common import service as os_service

LOG = logging.getLogger(__name__)
_ = i18n._
_LE = i18n._LE


class NotificationEndpoint(object):

    def __init__(self):
        self.plugins = get_plugins()
        self.notification_target_map = dict()
        for plugin in self.plugins:
            try:
                event_list = plugin.obj.get_notification_supported_events()
                for event in event_list:
                    self.notification_target_map[event.lower()] = plugin.obj
            except Exception as e:
                LOG.error(_LE("Failed to retrieve supported notification"
                              " events from search plugins "
                              "%(ext)s: %(e)s") %
                          {'ext': plugin.name, 'e': e})

    def info(self, ctxt, publisher_id, event_type, payload, metadata):
        event_type_l = event_type.lower()
        if event_type_l in self.notification_target_map:
            plugin = self.notification_target_map[event_type_l]
            handler = plugin.get_notification_handler()
            handler.process(
                ctxt,
                publisher_id,
                event_type,
                payload,
                metadata)


class ListenerService(os_service.Service):
    def __init__(self, *args, **kwargs):
        super(ListenerService, self).__init__(*args, **kwargs)
        self.listeners = []

    def start(self):
        super(ListenerService, self).start()
        transport = messaging.get_transport(cfg.CONF)
        targets = [
            messaging.Target(topic="notifications", exchange="glance")
        ]
        endpoints = [
            NotificationEndpoint()
        ]
        listener = messaging.get_notification_listener(
            transport,
            targets,
            endpoints)
        listener.start()
        self.listeners.append(listener)

    def stop(self):
        for listener in self.listeners:
            listener.stop()
            listener.wait()
        super(ListenerService, self).stop()


def get_plugins():
    namespace = 'glance.search.index_backend'
    ext_manager = stevedore.extension.ExtensionManager(
        namespace, invoke_on_load=True)
    return ext_manager.extensions
