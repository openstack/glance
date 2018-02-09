# Copyright 2018 Red Hat, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from glance_store import backend
from oslo_config import cfg
from oslo_log import log as logging
from taskflow.patterns import linear_flow as lf
from taskflow import task
from taskflow.types import failure

from glance.common import exception
from glance.common.scripts import utils as script_utils
from glance.i18n import _, _LE

LOG = logging.getLogger(__name__)

CONF = cfg.CONF


import_filtering_opts = [

    cfg.ListOpt('allowed_schemes',
                item_type=cfg.types.String(quotes=True),
                bounds=True,
                default=['http', 'https'],
                help=_("""
Specify the allowed url schemes for web-download.

This option provides whitelisting for uri schemes that web-download import
method will be using. Whitelisting is always priority and ignores any
blacklisting of the schemes but obeys host and port filtering.

For example: If scheme blacklisting contains 'http' and whitelist contains
['http', 'https'] the whitelist is obeyed on http://example.com but any
other scheme like ftp://example.com is blocked even it's not blacklisted.

Possible values:
    * List containing normalized url schemes as they are returned from
    urllib.parse. For example ['ftp','https']

Related options:
    * disallowed_schemes
    * allowed_hosts
    * disallowed_hosts
    * allowed_ports
    * disallowed_ports

""")),
    cfg.ListOpt('disallowed_schemes',
                item_type=cfg.types.String(quotes=True),
                bounds=True,
                default=[],
                help=_("""
Specify the blacklisted url schemes for web-download.

This option provides blacklisting for uri schemes that web-download import
method will be using. Whitelisting is always priority and ignores any
blacklisting of the schemes but obeys host and port filtering. Blacklisting
can be used to prevent specific scheme to be used when whitelisting is not
in use.

For example: If scheme blacklisting contains 'http' and whitelist contains
['http', 'https'] the whitelist is obeyed on http://example.com but any
other scheme like ftp://example.com is blocked even it's not blacklisted.

Possible values:
    * List containing normalized url schemes as they are returned from
    urllib.parse. For example ['ftp','https']
    * By default the list is empty

Related options:
    * allowed_schemes
    * allowed_hosts
    * disallowed_hosts
    * allowed_ports
    * disallowed_ports

""")),
    cfg.ListOpt('allowed_hosts',
                item_type=cfg.types.HostAddress(),
                bounds=True,
                default=[],
                help=_("""
Specify the allowed target hosts for web-download.

This option provides whitelisting for hosts that web-download import
method will be using. Whitelisting is always priority and ignores any
blacklisting of the hosts but obeys scheme and port filtering.

For example: If scheme blacklisting contains 'http' and whitelist contains
['http', 'https'] the whitelist is obeyed on http://example.com but any
other scheme like ftp://example.com is blocked even it's not blacklisted.
Same way the whitelisted example.com is only obeyed on the allowed schemes
and or ports. Whitelisting of the host does not allow all schemes and ports
accessed.

Possible values:
    * List containing normalized hostname or ip like it would be returned
    in the urllib.parse netloc without the port
    * By default the list is empty

Related options:
    * allowed_schemes
    * disallowed_schemes
    * disallowed_hosts
    * allowed_ports
    * disallowed_ports

""")),
    cfg.ListOpt('disallowed_hosts',
                item_type=cfg.types.HostAddress(),
                bounds=True,
                default=[],
                help=_("""
Specify the blacklisted hosts for web-download.

This option provides blacklisting for hosts that web-download import
method will be using. Whitelisting is always priority and ignores any
blacklisting but obeys scheme and port filtering.

For example: If scheme blacklisting contains 'http' and whitelist contains
['http', 'https'] the whitelist is obeyed on http://example.com but any
other scheme like ftp://example.com is blocked even it's not blacklisted.
The blacklisted example.com is obeyed on any url pointing to that host
regardless of what their scheme or port is.

Possible values:
    * List containing normalized hostname or ip like it would be returned
    in the urllib.parse netloc without the port
    * By default the list is empty

Related options:
    * allowed_schemes
    * disallowed_schemes
    * allowed_hosts
    * allowed_ports
    * disallowed_ports

""")),
    cfg.ListOpt('allowed_ports',
                item_type=cfg.types.Integer(min=1, max=65535),
                bounds=True,
                default=[80, 443],
                help=_("""
Specify the allowed ports for web-download.

This option provides whitelisting for uri ports that web-download import
method will be using. Whitelisting is always priority and ignores any
blacklisting of the ports but obeys host and scheme filtering.

For example: If scheme blacklisting contains '80' and whitelist contains
['80', '443'] the whitelist is obeyed on http://example.com:80 but any
other port like ftp://example.com:21 is blocked even it's not blacklisted.

Possible values:
    * List containing ports as they are returned from urllib.parse netloc
    field. For example ['80','443']

Related options:
    * allowed_schemes
    * disallowed_schemes
    * allowed_hosts
    * disallowed_hosts
    * disallowed_ports
""")),
    cfg.ListOpt('disallowed_ports',
                item_type=cfg.types.Integer(min=1, max=65535),
                bounds=True,
                default=[],
                help=_("""
Specify the disallowed ports for web-download.

This option provides blacklisting for uri ports that web-download import
method will be using. Whitelisting is always priority and ignores any
blacklisting of the ports but obeys host and scheme filtering.

For example: If scheme blacklisting contains '80' and whitelist contains
['80', '443'] the whitelist is obeyed on http://example.com:80 but any
other port like ftp://example.com:21 is blocked even it's not blacklisted.
If no whitelisting is defined any scheme and host combination is disallowed
for the blacklisted port.

Possible values:
    * List containing ports as they are returned from urllib.parse netloc
    field. For example ['80','443']
    * By default this list is empty.

Related options:
    * allowed_schemes
    * disallowed_schemes
    * allowed_hosts
    * disallowed_hosts
    * allowed_ports

""")),
]

CONF.register_opts(import_filtering_opts, group='import_filtering_opts')


class _WebDownload(task.Task):

    default_provides = 'file_uri'

    def __init__(self, task_id, task_type, image_repo, image_id, uri):
        self.task_id = task_id
        self.task_type = task_type
        self.image_repo = image_repo
        self.image_id = image_id
        self.uri = uri
        super(_WebDownload, self).__init__(
            name='%s-WebDownload-%s' % (task_type, task_id))

        if CONF.node_staging_uri is None:
            msg = (_("%(task_id)s of %(task_type)s not configured "
                     "properly. Missing node_staging_uri: %(work_dir)s") %
                   {'task_id': self.task_id,
                    'task_type': self.task_type,
                    'work_dir': CONF.node_staging_uri})
            raise exception.BadTaskConfiguration(msg)

        self.store = self._build_store()

    def _build_store(self):
        # NOTE(flaper87): Due to the nice glance_store api (#sarcasm), we're
        # forced to build our own config object, register the required options
        # (and by required I mean *ALL* of them, even the ones we don't want),
        # and create our own store instance by calling a private function.
        # This is certainly unfortunate but it's the best we can do until the
        # glance_store refactor is done. A good thing is that glance_store is
        # under our team's management and it gates on Glance so changes to
        # this API will (should?) break task's tests.
        conf = cfg.ConfigOpts()
        backend.register_opts(conf)
        conf.set_override('filesystem_store_datadir',
                          CONF.node_staging_uri[7:],
                          group='glance_store')

        # NOTE(flaper87): Do not even try to judge me for this... :(
        # With the glance_store refactor, this code will change, until
        # that happens, we don't have a better option and this is the
        # least worst one, IMHO.
        store = backend._load_store(conf, 'file')

        if store is None:
            msg = (_("%(task_id)s of %(task_type)s not configured "
                     "properly. Could not load the filesystem store") %
                   {'task_id': self.task_id, 'task_type': self.task_type})
            raise exception.BadTaskConfiguration(msg)

        store.configure()
        return store

    def execute(self):
        """Create temp file into store and return path to it

        :param image_id: Glance Image ID
        """
        # NOTE(jokke): We've decided to use staging area for this task as
        # a way to expect users to configure a local store for pre-import
        # works on the image to happen.
        #
        # While using any path should be "technically" fine, it's not what
        # we recommend as the best solution. For more details on this, please
        # refer to the comment in the `_ImportToStore.execute` method.
        data = script_utils.get_image_data_iter(self.uri)

        path = self.store.add(self.image_id, data, 0)[0]

        return path

    def revert(self, result, **kwargs):
        if isinstance(result, failure.Failure):
            LOG.exception(_LE('Task: %(task_id)s failed to import image '
                              '%(image_id)s to the filesystem.'),
                          {'task_id': self.task_id,
                           'image_id': self.image_id})


def get_flow(**kwargs):
    """Return task flow for web-download.

    :param task_id: Task ID.
    :param task_type: Type of the task.
    :param image_repo: Image repository used.
    :param uri: URI the image data is downloaded from.
    """
    task_id = kwargs.get('task_id')
    task_type = kwargs.get('task_type')
    image_repo = kwargs.get('image_repo')
    image_id = kwargs.get('image_id')
    uri = kwargs.get('import_req')['method'].get('uri')

    return lf.Flow(task_type).add(
        _WebDownload(task_id, task_type, image_repo, image_id, uri),
    )
