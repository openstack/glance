# Copyright (c) 2015 Mirantis, Inc.
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

from keystoneauth1 import exceptions as ka_exceptions
from keystoneauth1 import loading as ka_loading
from keystoneclient.v3 import client as ks_client
from oslo_config import cfg
from oslo_log import log as logging

CONF = cfg.CONF
CONF.register_opt(cfg.IntOpt('timeout'), group='keystone_authtoken')

LOG = logging.getLogger(__name__)


class TokenRefresher(object):
    """Class that responsible for token refreshing with trusts"""

    def __init__(self, user_plugin, user_project, user_roles):
        """Prepare all parameters and clients required to refresh token"""
        # step 1: create trust to ensure that we can always update token

        # trustor = user who made the request
        trustor_client = self._load_client(user_plugin)
        trustor_id = trustor_client.session.get_user_id()

        # get trustee user client that impersonates main user
        trustee_user_auth = ka_loading.load_auth_from_conf_options(
            CONF, 'keystone_authtoken')
        # save service user client because we need new service token
        # to refresh trust-scoped client later
        self.trustee_user_client = self._load_client(trustee_user_auth)

        trustee_id = self.trustee_user_client.session.get_user_id()

        self.trust_id = trustor_client.trusts.create(trustor_user=trustor_id,
                                                     trustee_user=trustee_id,
                                                     impersonation=True,
                                                     role_names=user_roles,
                                                     project=user_project).id
        LOG.debug("Trust %s has been created.", self.trust_id)

        # step 2: postpone trust-scoped client initialization
        # until we need to refresh the token
        self.trustee_client = None

    def refresh_token(self):
        """Receive new token if user need to update old token

        :return: new token that can be used for authentication
        """
        LOG.debug("Requesting the new token with trust %s", self.trust_id)
        if self.trustee_client is None:
            self.trustee_client = self._refresh_trustee_client()
        try:
            return self.trustee_client.session.get_token()
        except ka_exceptions.Unauthorized:
            # in case of Unauthorized exceptions try to refresh client because
            # service user token may expired
            self.trustee_client = self._refresh_trustee_client()
            return self.trustee_client.session.get_token()

    def release_resources(self):
        """Release keystone resources required for refreshing"""

        try:
            if self.trustee_client is None:
                self._refresh_trustee_client().trusts.delete(self.trust_id)
            else:
                self.trustee_client.trusts.delete(self.trust_id)
        except ka_exceptions.Unauthorized:
            # service user token may expire when we are trying to delete token
            # so need to update client to ensure that this is not the reason
            # of failure
            self.trustee_client = self._refresh_trustee_client()
            self.trustee_client.trusts.delete(self.trust_id)

    def _refresh_trustee_client(self):
        # Remove project_name and project_id, since we need a trust scoped
        # auth object
        kwargs = {
            'project_name': None,
            'project_domain_name': None,
            'project_id': None,
            'trust_id': self.trust_id
        }

        trustee_auth = ka_loading.load_auth_from_conf_options(
            CONF, 'keystone_authtoken', **kwargs)

        return self._load_client(trustee_auth)

    @staticmethod
    def _load_client(plugin):
        # load client from auth settings and user plugin
        sess = ka_loading.load_session_from_conf_options(
            CONF, 'keystone_authtoken', auth=plugin)
        return ks_client.Client(session=sess)
