# Copyright 2012 OpenStack Foundation.
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

from oslo_log import log as logging
from oslo_utils import encodeutils
import six.moves.urllib.parse as urlparse
import sqlalchemy

from glance.common import exception
from glance.i18n import _, _LE

LOG = logging.getLogger(__name__)


def upgrade(migrate_engine):
    migrate_location_credentials(migrate_engine, to_quoted=True)


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

    images = list(images_table.select(images_table.c.location.startswith(
                                      'swift')).execute())

    for image in images:
        try:
            fixed_uri = legacy_parse_uri(image['location'], to_quoted)
            images_table.update().where(
                images_table.c.id == image['id']).values(
                    location=fixed_uri).execute()
        except exception.BadStoreUri as e:
            reason = encodeutils.exception_to_unicode(e)
            msg = _LE("Invalid store uri for image: %(image_id)s. "
                      "Details: %(reason)s") % {'image_id': image.id,
                                                'reason': reason}
            LOG.exception(msg)
            raise


def legacy_parse_uri(uri, to_quote):
    """
    Parse URLs. This method fixes an issue where credentials specified
    in the URL are interpreted differently in Python 2.6.1+ than prior
    versions of Python. It also deals with the peculiarity that new-style
    Swift URIs have where a username can contain a ':', like so:

        swift://account:user:pass@authurl.com/container/obj

    If to_quoted is True, the uri is assumed to have credentials that
    have not been quoted, and the resulting uri will contain quoted
    credentials.

    If to_quoted is False, the uri is assumed to have credentials that
    have been quoted, and the resulting uri will contain credentials
    that have not been quoted.
    """
    # Make sure that URIs that contain multiple schemes, such as:
    # swift://user:pass@http://authurl.com/v1/container/obj
    # are immediately rejected.
    if uri.count('://') != 1:
        reason = _("URI cannot contain more than one occurrence of a scheme."
                   "If you have specified a URI like "
                   "swift://user:pass@http://authurl.com/v1/container/obj"
                   ", you need to change it to use the swift+http:// scheme, "
                   "like so: "
                   "swift+http://user:pass@authurl.com/v1/container/obj")

        raise exception.BadStoreUri(message=reason)

    pieces = urlparse.urlparse(uri)
    if pieces.scheme not in ('swift', 'swift+http', 'swift+https'):
        raise exception.BadStoreUri(message="Unacceptable scheme: '%s'" %
                                    pieces.scheme)
    scheme = pieces.scheme
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
        if to_quote:
            if len(cred_parts) == 1:
                reason = (_("Badly formed credentials '%(creds)s' in Swift "
                            "URI") % {'creds': creds})
                raise exception.BadStoreUri(message=reason)
            elif len(cred_parts) == 3:
                user = ':'.join(cred_parts[0:2])
            else:
                user = cred_parts[0]
            key = cred_parts[-1]
            user = user
            key = key
        else:
            if len(cred_parts) != 2:
                reason = (_("Badly formed credentials in Swift URI."))
                raise exception.BadStoreUri(message=reason)
            user, key = cred_parts
            user = urlparse.unquote(user)
            key = urlparse.unquote(key)
    else:
        user = None
        key = None
    path_parts = path.split('/')
    try:
        obj = path_parts.pop()
        container = path_parts.pop()
        if not netloc.startswith('http'):
            # push hostname back into the remaining to build full authurl
            path_parts.insert(0, netloc)
            auth_or_store_url = '/'.join(path_parts)
    except IndexError:
        reason = _("Badly formed S3 URI: %(uri)s") % {'uri': uri}
        raise exception.BadStoreUri(message=reason)

    if auth_or_store_url.startswith('http://'):
        auth_or_store_url = auth_or_store_url[len('http://'):]
    elif auth_or_store_url.startswith('https://'):
        auth_or_store_url = auth_or_store_url[len('https://'):]

    credstring = ''
    if user and key:
        if to_quote:
            quote_user = urlparse.quote(user)
            quote_key = urlparse.quote(key)
        else:
            quote_user = user
            quote_key = key
        credstring = '%s:%s@' % (quote_user, quote_key)

    auth_or_store_url = auth_or_store_url.strip('/')
    container = container.strip('/')
    obj = obj.strip('/')

    return '%s://%s%s/%s/%s' % (scheme, credstring, auth_or_store_url,
                                container, obj)
