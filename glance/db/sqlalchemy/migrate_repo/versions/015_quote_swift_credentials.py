# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 OpenStack LLC.
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

import types
import urlparse

import sqlalchemy

from glance.common import exception
import glance.openstack.common.log as logging
import glance.store.swift

LOG = logging.getLogger(__name__)


def upgrade(migrate_engine):
    migrate_location_credentials(migrate_engine, to_quoted=True)


def downgrade(migrate_engine):
    migrate_location_credentials(migrate_engine, to_quoted=False)


def migrate_location_credentials(migrate_engine, to_quoted):
    """
    Migrate location credentials for swift uri's between the quoted
    and unquoted forms.

    :param migrate_engine: The configured db engine
    :param to_quoted: If True, migrate location credentials from
                      unquoted to quoted form.  If False, do the
                      reverse.
    """
    meta = sqlalchemy.schema.MetaData()
    meta.bind = migrate_engine

    images_table = sqlalchemy.Table('images', meta, autoload=True)

    images = images_table.select(images_table.c.location.startswith('swift')).\
             execute()

    for image in images:
        fixed_uri = fix_uri_credentials(image['location'], to_quoted)
        images_table.update().\
            where(images_table.c.id == image['id']).\
            values(location=fixed_uri).execute()


def fix_uri_credentials(uri, to_quoted):
    """
    Fix the given uri's embedded credentials by round-tripping with
    StoreLocation.

    If to_quoted is True, the uri is assumed to have credentials that
    have not been quoted, and the resulting uri will contain quoted
    credentials.

    If to_quoted is False, the uri is assumed to have credentials that
    have been quoted, and the resulting uri will contain credentials
    that have not been quoted.
    """
    location = glance.store.swift.StoreLocation({})
    if to_quoted:
        # The legacy parse_uri doesn't unquote credentials
        location.parse_uri = types.MethodType(legacy_parse_uri, location)
    else:
        # The legacy _get_credstring doesn't quote credentials
        location._get_credstring = types.MethodType(legacy__get_credstring,
                                                    location)
    location.parse_uri(uri)
    return location.get_uri()


def legacy__get_credstring(self):
    if self.user:
        return '%s:%s@' % (self.user, self.key)
    return ''


def legacy_parse_uri(self, uri):
    """
    Parse URLs. This method fixes an issue where credentials specified
    in the URL are interpreted differently in Python 2.6.1+ than prior
    versions of Python. It also deals with the peculiarity that new-style
    Swift URIs have where a username can contain a ':', like so:

        swift://account:user:pass@authurl.com/container/obj
    """
    # Make sure that URIs that contain multiple schemes, such as:
    # swift://user:pass@http://authurl.com/v1/container/obj
    # are immediately rejected.
    if uri.count('://') != 1:
        reason = _(
                "URI cannot contain more than one occurrence of a scheme."
                "If you have specified a URI like "
                "swift://user:pass@http://authurl.com/v1/container/obj"
                ", you need to change it to use the swift+http:// scheme, "
                "like so: "
                "swift+http://user:pass@authurl.com/v1/container/obj"
                )

        LOG.error(_("Invalid store uri %(uri)s: %(reason)s") % locals())
        raise exception.BadStoreUri(message=reason)

    pieces = urlparse.urlparse(uri)
    assert pieces.scheme in ('swift', 'swift+http', 'swift+https')
    self.scheme = pieces.scheme
    netloc = pieces.netloc
    path = pieces.path.lstrip('/')
    if netloc != '':
        # > Python 2.6.1
        if '@' in netloc:
            creds, netloc = netloc.split('@')
        else:
            creds = None
    else:
        # Python 2.6.1 compat
        # see lp659445 and Python issue7904
        if '@' in path:
            creds, path = path.split('@')
        else:
            creds = None
        netloc = path[0:path.find('/')].strip('/')
        path = path[path.find('/'):].strip('/')
    if creds:
        cred_parts = creds.split(':')

        # User can be account:user, in which case cred_parts[0:2] will be
        # the account and user. Combine them into a single username of
        # account:user
        if len(cred_parts) == 1:
            reason = (_("Badly formed credentials '%(creds)s' in Swift "
                        "URI") % locals())
            LOG.error(reason)
            raise exception.BadStoreUri()
        elif len(cred_parts) == 3:
            user = ':'.join(cred_parts[0:2])
        else:
            user = cred_parts[0]
        key = cred_parts[-1]
        self.user = user
        self.key = key
    else:
        self.user = None
    path_parts = path.split('/')
    try:
        self.obj = path_parts.pop()
        self.container = path_parts.pop()
        if not netloc.startswith('http'):
            # push hostname back into the remaining to build full authurl
            path_parts.insert(0, netloc)
            self.auth_or_store_url = '/'.join(path_parts)
    except IndexError:
        reason = _("Badly formed S3 URI: %s") % uri
        LOG.error(message=reason)
        raise exception.BadStoreUri()
