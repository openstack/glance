#!/usr/bin/env python
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

import sys

import keystoneclient.v2_0.client
from oslo_config import cfg
from oslo_log import log as logging

import glance.context
import glance.db.sqlalchemy.api as db_api
from glance import i18n
import glance.registry.context

_ = i18n._
_LC = i18n._LC
_LE = i18n._LE
_LI = i18n._LI

LOG = logging.getLogger(__name__)
LOG.addHandler(logging.StreamHandler())
LOG.setLevel(logging.DEBUG)


def get_owner_map(ksclient, owner_is_tenant=True):
    if owner_is_tenant:
        entities = ksclient.tenants.list()
    else:
        entities = ksclient.users.list()
    # build mapping of (user or tenant) name to id
    return {entity.name: entity.id for entity in entities}


def build_image_owner_map(owner_map, db, context):
    image_owner_map = {}
    for image in db.image_get_all(context):
        image_id = image['id']
        owner_name = image['owner']

        if not owner_name:
            LOG.info(_LI('Image %s has no owner. Skipping.') % image_id)
            continue

        try:
            owner_id = owner_map[owner_name]
        except KeyError:
            msg = (_LE('Image "%(image)s" owner "%(owner)s" was not found. '
                       'Skipping.'),
                   {'image': image_id, 'owner': owner_name})
            LOG.error(msg)
            continue

        image_owner_map[image_id] = owner_id

        msg = (_LI('Image "%(image)s" owner "%(owner)s" -> "%(owner_id)s"'),
               {'image': image_id, 'owner': owner_name, 'owner_id': owner_id})
        LOG.info(msg)

    return image_owner_map


def update_image_owners(image_owner_map, db, context):
    for (image_id, image_owner) in image_owner_map.items():
        db.image_update(context, image_id, {'owner': image_owner})
        LOG.info(_LI('Image %s successfully updated.') % image_id)


if __name__ == "__main__":
    config = cfg.CONF
    extra_cli_opts = [
        cfg.BoolOpt('dry-run',
                    help='Print output but do not make db changes.'),
        cfg.StrOpt('keystone-auth-uri',
                   help='Authentication endpoint'),
        cfg.StrOpt('keystone-admin-tenant-name',
                   help='Administrative user\'s tenant name'),
        cfg.StrOpt('keystone-admin-user',
                   help='Administrative user\'s id'),
        cfg.StrOpt('keystone-admin-password',
                   help='Administrative user\'s password',
                   secret=True),
    ]
    config.register_cli_opts(extra_cli_opts)
    config(project='glance', prog='glance-registry')

    db_api.configure_db()

    context = glance.common.context.RequestContext(is_admin=True)

    auth_uri = config.keystone_auth_uri
    admin_tenant_name = config.keystone_admin_tenant_name
    admin_user = config.keystone_admin_user
    admin_password = config.keystone_admin_password

    if not (auth_uri and admin_tenant_name and admin_user and admin_password):
        LOG.critical(_LC('Missing authentication arguments'))
        sys.exit(1)

    ks = keystoneclient.v2_0.client.Client(username=admin_user,
                                           password=admin_password,
                                           tenant_name=admin_tenant_name,
                                           auth_url=auth_uri)

    owner_map = get_owner_map(ks, config.owner_is_tenant)
    image_updates = build_image_owner_map(owner_map, db_api, context)
    if not config.dry_run:
        update_image_owners(image_updates, db_api, context)
