# Copyright (c) 2015 Mirantis, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import sys
import uuid

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import encodeutils

from glance.artifacts.domain import proxy
from glance.common.artifacts import definitions
from glance.common import utils
from glance import i18n

_ = i18n._
_LE = i18n._LE
_LW = i18n._LW

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class ArtifactFactoryProxy(proxy.ArtifactFactory):
    def __init__(self, factory, context, store_api, store_utils):
        self.context = context
        self.store_api = store_api
        self.store_utils = store_utils
        proxy_kwargs = {'store_api': store_api,
                        'store_utils': store_utils,
                        'context': self.context}
        super(ArtifactFactoryProxy, self).__init__(
            factory,
            artifact_proxy_class=ArtifactProxy,
            artifact_proxy_kwargs=proxy_kwargs)


class ArtifactProxy(proxy.Artifact):
    def __init__(self, artifact, context, store_api, store_utils):
        self.artifact = artifact
        self.context = context
        self.store_api = store_api
        self.store_utils = store_utils
        super(ArtifactProxy,
              self).__init__(artifact,
                             proxy_class=ArtifactBlobProxy,
                             proxy_kwargs={"context": self.context,
                                           "store_api": self.store_api})

    def set_type_specific_property(self, prop_name, value):
        if prop_name not in self.artifact.metadata.attributes.blobs:
            super(ArtifactProxy, self).set_type_specific_property(prop_name,
                                                                  value)
            return
        item_key = "%s.%s" % (self.artifact.id, prop_name)
        # XXX FIXME have to add support for BinaryObjectList properties
        blob = definitions.Blob(item_key=item_key)
        blob_proxy = self.helper.proxy(blob)

        if value is None:
            for location in blob_proxy.locations:
                blob_proxy.delete_from_store(location)
        else:
            data = value[0]
            size = value[1]
            blob_proxy.upload_to_store(data, size)
        setattr(self.artifact, prop_name, blob)

    def get_type_specific_property(self, prop_name):
        base = super(ArtifactProxy, self).get_type_specific_property(prop_name)
        if base is None:
            return None
        if prop_name in self.artifact.metadata.attributes.blobs:
            if isinstance(self.artifact.metadata.attributes.blobs[prop_name],
                          list):
                return ArtifactBlobProxyList(self.artifact.id,
                                             prop_name,
                                             base,
                                             self.context,
                                             self.store_api)
            else:
                return self.helper.proxy(base)
        else:
            return base


class ArtifactRepoProxy(proxy.ArtifactRepo):
    def __init__(self, artifact_repo, context, store_api, store_utils):
        self.context = context
        self.store_api = store_api
        proxy_kwargs = {'context': context, 'store_api': store_api,
                        'store_utils': store_utils}
        super(ArtifactRepoProxy, self).__init__(
            artifact_repo,
            proxy_helper=proxy.ArtifactHelper(ArtifactProxy, proxy_kwargs))

    def get(self, *args, **kwargs):
        return self.helper.proxy(self.base.get(*args, **kwargs))


class ArtifactBlobProxy(proxy.ArtifactBlob):
    def __init__(self, blob, context, store_api):
        self.context = context
        self.store_api = store_api
        self.blob = blob
        super(ArtifactBlobProxy, self).__init__(blob)

    def delete_from_store(self, location):
        try:
            ret = self.store_api.delete_from_backend(location['value'],
                                                     context=self.context)
            location['status'] = 'deleted'
            return ret
        except self.store_api.NotFound:
            msg = _LW('Failed to delete blob'
                      ' %s in store from URI') % self.blob.id
            LOG.warn(msg)
        except self.store_api.StoreDeleteNotSupported as e:
            LOG.warn(encodeutils.exception_to_unicode(e))
        except self.store_api.UnsupportedBackend:
            exc_type = sys.exc_info()[0].__name__
            msg = (_LE('Failed to delete blob'
                       ' %(blob_id)s from store: %(exc)s') %
                   dict(blob_id=self.blob.id, exc=exc_type))
            LOG.error(msg)

    def upload_to_store(self, data, size):
        if size is None:  # NOTE(ativelkov): None is "unknown size"
            size = 0
        location, ret_size, checksum, loc_meta = self.store_api.add_to_backend(
            CONF,
            self.blob.item_key,
            utils.LimitingReader(utils.CooperativeReader(data),
                                 CONF.image_size_cap),
            size,
            context=self.context)
        self.blob.size = ret_size
        self.blob.locations = [{'status': 'active', 'value': location}]
        self.blob.checksum = checksum

    @property
    def data_stream(self):
        if len(self.locations) > 0:
            err = None
            try:
                for location in self.locations:
                    data, size = self.store_api.get_from_backend(
                        location['value'],
                        context=self.context)
                    return data
            except Exception as e:
                LOG.warn(_('Get blob %(name)s data failed: '
                           '%(err)s.')
                         % {'name': self.blob.item_key,
                            'err': encodeutils.exception_to_unicode(e)})
                err = e

            # tried all locations
            LOG.error(_LE('Glance tried all active locations to get data '
                          'for blob %s '
                          'but all have failed.') % self.blob.item_key)
            raise err


class ArtifactBlobProxyList(proxy.List):
    def __init__(self, artifact_id, prop_name, bloblist, context, store_api):
        self.artifact_id = artifact_id
        self.prop_name = prop_name
        self.context = context
        self.store_api = store_api
        super(ArtifactBlobProxyList,
              self).__init__(bloblist,
                             item_proxy_class=ArtifactBlobProxy,
                             item_proxy_kwargs={'context': context,
                                                'store_api': store_api})

    def insert(self, index, value):
        data = value[0]
        size = value[1]
        item_key = "%s.%s.%s" % (self.artifact_id, self.prop_name,
                                 uuid.uuid4())
        blob = definitions.Blob(item_key=item_key)
        blob_proxy = self.helper.proxy(blob)
        blob_proxy.upload_to_store(data, size)
        super(ArtifactBlobProxyList, self).insert(index, blob_proxy)

    def __setitem__(self, index, value):
        blob = self[index]
        data = value[0]
        size = value[1]
        blob.upload_to_store(data, size)
