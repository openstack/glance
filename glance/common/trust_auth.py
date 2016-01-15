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

from keystoneauth1.identity import v3
from keystoneauth1.loading import conf
from keystoneauth1.loading import session
from keystoneclient import exceptions as ks_exceptions
from keystoneclient.v3 import client as ks_client
from oslo_config import cfg
from oslo_log import log as logging

CONF = cfg.CONF

LOG = logging.getLogger(__name__)


class TokenRefresher(object):
    """Class that responsible for token refreshing with trusts"""

    def __init__(self, user_plugin, user_project, user_roles):
        """Prepare all parameters and clients required to refresh token"""

        # step 1: Prepare parameters required to connect to keystone
        self.auth_url = CONF.keystone_authtoken.auth_uri
        if not self.auth_url.endswith('/v3'):
            self.auth_url += '/v3'

        self.ssl_settings = {
            'cacert': CONF.keystone_authtoken.cafile,
            'insecure': CONF.keystone_authtoken.insecure,
            'cert': CONF.keystone_authtoken.certfile,
            'key': CONF.keystone_authtoken.keyfile,
        }

        # step 2: create trust to ensure that we can always update token

        # trustor = user who made the request
        trustor_client = self._load_client(user_plugin, self.ssl_settings)
        trustor_id = trustor_client.session.get_user_id()

        # get trustee user client that impersonates main user
        trustee_user_auth = conf.load_from_conf_options(CONF,
                                                        'keystone_authtoken')
        # save service user client because we need new service token
        # to refresh trust-scoped client later
        self.trustee_user_client = self._load_client(trustee_user_auth,
                                                     self.ssl_settings)
        trustee_id = self.trustee_user_client.session.get_user_id()

        self.trust_id = trustor_client.trusts.create(trustor_user=trustor_id,
                                                     trustee_user=trustee_id,
                                                     impersonation=True,
                                                     role_names=user_roles,
                                                     project=user_project).id
        LOG.debug("Trust %s has been created.", self.trust_id)

        # step 3: postpone trust-scoped client initialization
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
        except ks_exceptions.Unauthorized:
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
        except ks_exceptions.Unauthorized:
            # service user token may expire when we are trying to delete token
            # so need to update client to ensure that this is not the reason
            # of failure
            self.trustee_client = self._refresh_trustee_client()
            self.trustee_client.trusts.delete(self.trust_id)

    def _refresh_trustee_client(self):
        trustee_token = self.trustee_user_client.session.get_token()
        trustee_auth = v3.Token(
            trust_id=self.trust_id,
            token=trustee_token,
            auth_url=self.auth_url
        )
        return self._load_client(trustee_auth, self.ssl_settings)

    @staticmethod
    def _load_client(plugin, ssl_settings):
        # load client from auth settings and user plugin
        sess = session.Session().load_from_options(
            auth=plugin, **ssl_settings)
        return ks_client.Client(session=sess)
