# Copyright 2014 Hewlett-Packard Development Company, L.P.
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

import elasticsearch
from elasticsearch import helpers
from oslo_config import cfg

from glance.common import utils


search_opts = [
    cfg.ListOpt('hosts', default=['127.0.0.1:9200'],
                help='List of nodes where Elasticsearch instances are '
                     'running. A single node should be defined as an IP '
                     'address and port number.'),
]

CONF = cfg.CONF
CONF.register_opts(search_opts, group='elasticsearch')


def get_api():
    es_hosts = CONF.elasticsearch.hosts
    es_api = elasticsearch.Elasticsearch(hosts=es_hosts)
    return es_api


class CatalogSearchRepo(object):

    def __init__(self, context, es_api):
        self.context = context
        self.es_api = es_api
        self.plugins = utils.get_search_plugins() or []
        self.plugins_info_dict = self._get_plugin_info()

    def search(self, index, doc_type, query, fields, offset, limit,
               ignore_unavailable=True):
        return self.es_api.search(
            index=index,
            doc_type=doc_type,
            body=query,
            _source_include=fields,
            from_=offset,
            size=limit,
            ignore_unavailable=ignore_unavailable)

    def index(self, default_index, default_type, actions):
        return helpers.bulk(
            client=self.es_api,
            index=default_index,
            doc_type=default_type,
            actions=actions)

    def plugins_info(self):
        return self.plugins_info_dict

    def _get_plugin_info(self):
        plugin_info = dict()
        plugin_info['plugins'] = []
        for plugin in self.plugins:
            info = dict()
            info['type'] = plugin.obj.get_document_type()
            info['index'] = plugin.obj.get_index_name()
            plugin_info['plugins'].append(info)
        return plugin_info
