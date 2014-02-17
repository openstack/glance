# Copyright 2010 OpenStack Foundation
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

"""Storage backend for S3 or Storage Servers that follow the S3 Protocol"""

import hashlib
import httplib
import re
import tempfile

from oslo.config import cfg
import six.moves.urllib.parse as urlparse

from glance.common import exception
from glance.common import utils
import glance.openstack.common.log as logging
import glance.store
import glance.store.base
import glance.store.location

LOG = logging.getLogger(__name__)

s3_opts = [
    cfg.StrOpt('s3_store_host',
               help=_('The host where the S3 server is listening.')),
    cfg.StrOpt('s3_store_access_key', secret=True,
               help=_('The S3 query token access key.')),
    cfg.StrOpt('s3_store_secret_key', secret=True,
               help=_('The S3 query token secret key.')),
    cfg.StrOpt('s3_store_bucket',
               help=_('The S3 bucket to be used to store the Glance data.')),
    cfg.StrOpt('s3_store_object_buffer_dir',
               help=_('The local directory where uploads will be staged '
                      'before they are transferred into S3.')),
    cfg.BoolOpt('s3_store_create_bucket_on_put', default=False,
                help=_('A boolean to determine if the S3 bucket should be '
                       'created on upload if it does not exist or if '
                       'an error should be returned to the user.')),
    cfg.StrOpt('s3_store_bucket_url_format', default='subdomain',
               help=_('The S3 calling format used to determine the bucket. '
                      'Either subdomain or path can be used.')),
]

CONF = cfg.CONF
CONF.register_opts(s3_opts)


class StoreLocation(glance.store.location.StoreLocation):

    """
    Class describing an S3 URI. An S3 URI can look like any of
    the following:

        s3://accesskey:secretkey@s3.amazonaws.com/bucket/key-id
        s3+http://accesskey:secretkey@s3.amazonaws.com/bucket/key-id
        s3+https://accesskey:secretkey@s3.amazonaws.com/bucket/key-id

    The s3+https:// URIs indicate there is an HTTPS s3service URL
    """

    def process_specs(self):
        self.scheme = self.specs.get('scheme', 's3')
        self.accesskey = self.specs.get('accesskey')
        self.secretkey = self.specs.get('secretkey')
        s3_host = self.specs.get('s3serviceurl')
        self.bucket = self.specs.get('bucket')
        self.key = self.specs.get('key')

        if s3_host.startswith('https://'):
            self.scheme = 's3+https'
            s3_host = s3_host[8:].strip('/')
        elif s3_host.startswith('http://'):
            s3_host = s3_host[7:].strip('/')
        self.s3serviceurl = s3_host.strip('/')

    def _get_credstring(self):
        if self.accesskey:
            return '%s:%s@' % (self.accesskey, self.secretkey)
        return ''

    def get_uri(self):
        return "%s://%s%s/%s/%s" % (
            self.scheme,
            self._get_credstring(),
            self.s3serviceurl,
            self.bucket,
            self.key)

    def parse_uri(self, uri):
        """
        Parse URLs. This method fixes an issue where credentials specified
        in the URL are interpreted differently in Python 2.6.1+ than prior
        versions of Python.

        Note that an Amazon AWS secret key can contain the forward slash,
        which is entirely retarded, and breaks urlparse miserably.
        This function works around that issue.
        """
        # Make sure that URIs that contain multiple schemes, such as:
        # s3://accesskey:secretkey@https://s3.amazonaws.com/bucket/key-id
        # are immediately rejected.
        if uri.count('://') != 1:
            reason = _("URI cannot contain more than one occurrence "
                       "of a scheme. If you have specified a URI like "
                       "s3://accesskey:secretkey@"
                       "https://s3.amazonaws.com/bucket/key-id"
                       ", you need to change it to use the "
                       "s3+https:// scheme, like so: "
                       "s3+https://accesskey:secretkey@"
                       "s3.amazonaws.com/bucket/key-id")
            LOG.debug(_("Invalid store uri: %s") % reason)
            raise exception.BadStoreUri(message=reason)

        pieces = urlparse.urlparse(uri)
        assert pieces.scheme in ('s3', 's3+http', 's3+https')
        self.scheme = pieces.scheme
        path = pieces.path.strip('/')
        netloc = pieces.netloc.strip('/')
        entire_path = (netloc + '/' + path).strip('/')

        if '@' in uri:
            creds, path = entire_path.split('@')
            cred_parts = creds.split(':')

            try:
                access_key = cred_parts[0]
                secret_key = cred_parts[1]
                # NOTE(jaypipes): Need to encode to UTF-8 here because of a
                # bug in the HMAC library that boto uses.
                # See: http://bugs.python.org/issue5285
                # See: http://trac.edgewall.org/ticket/8083
                access_key = access_key.encode('utf-8')
                secret_key = secret_key.encode('utf-8')
                self.accesskey = access_key
                self.secretkey = secret_key
            except IndexError:
                reason = _("Badly formed S3 credentials %s") % creds
                LOG.debug(reason)
                raise exception.BadStoreUri()
        else:
            self.accesskey = None
            path = entire_path
        try:
            path_parts = path.split('/')
            self.key = path_parts.pop()
            self.bucket = path_parts.pop()
            if path_parts:
                self.s3serviceurl = '/'.join(path_parts).strip('/')
            else:
                reason = _("Badly formed S3 URI. Missing s3 service URL.")
                raise exception.BadStoreUri()
        except IndexError:
            reason = _("Badly formed S3 URI: %s") % uri
            LOG.debug(reason)
            raise exception.BadStoreUri()


class ChunkedFile(object):

    """
    We send this back to the Glance API server as
    something that can iterate over a ``boto.s3.key.Key``
    """

    CHUNKSIZE = 65536

    def __init__(self, fp):
        self.fp = fp

    def __iter__(self):
        """Return an iterator over the image file"""
        try:
            if self.fp:
                while True:
                    chunk = self.fp.read(ChunkedFile.CHUNKSIZE)
                    if chunk:
                        yield chunk
                    else:
                        break
        finally:
            self.close()

    def getvalue(self):
        """Return entire string value... used in testing."""
        data = ""
        self.len = 0
        for chunk in self:
            read_bytes = len(chunk)
            data = data + chunk
            self.len = self.len + read_bytes
        return data

    def close(self):
        """Close the internal file pointer."""
        if self.fp:
            self.fp.close()
            self.fp = None


class Store(glance.store.base.Store):
    """An implementation of the s3 adapter."""

    EXAMPLE_URL = "s3://<ACCESS_KEY>:<SECRET_KEY>@<S3_URL>/<BUCKET>/<OBJ>"

    def get_schemes(self):
        return ('s3', 's3+http', 's3+https')

    def configure_add(self):
        """
        Configure the Store to use the stored configuration options
        Any store that needs special configuration should implement
        this method. If the store was not able to successfully configure
        itself, it should raise `exception.BadStoreConfiguration`
        """
        self.s3_host = self._option_get('s3_store_host')
        access_key = self._option_get('s3_store_access_key')
        secret_key = self._option_get('s3_store_secret_key')
        # NOTE(jaypipes): Need to encode to UTF-8 here because of a
        # bug in the HMAC library that boto uses.
        # See: http://bugs.python.org/issue5285
        # See: http://trac.edgewall.org/ticket/8083
        self.access_key = access_key.encode('utf-8')
        self.secret_key = secret_key.encode('utf-8')
        self.bucket = self._option_get('s3_store_bucket')

        self.scheme = 's3'
        if self.s3_host.startswith('https://'):
            self.scheme = 's3+https'
            self.full_s3_host = self.s3_host
        elif self.s3_host.startswith('http://'):
            self.full_s3_host = self.s3_host
        else:  # Defaults http
            self.full_s3_host = 'http://' + self.s3_host

        self.s3_store_object_buffer_dir = CONF.s3_store_object_buffer_dir

    def _option_get(self, param):
        result = getattr(CONF, param)
        if not result:
            reason = (_("Could not find %(param)s in configuration "
                        "options.") % {'param': param})
            LOG.debug(reason)
            raise exception.BadStoreConfiguration(store_name="s3",
                                                  reason=reason)
        return result

    def get(self, location):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file, and returns a tuple of generator
        (for reading the image file) and image_size

        :param location `glance.store.location.Location` object, supplied
                        from glance.store.location.get_location_from_uri()
        :raises `glance.exception.NotFound` if image does not exist
        """
        key = self._retrieve_key(location)

        key.BufferSize = self.CHUNKSIZE

        class ChunkedIndexable(glance.store.Indexable):
            def another(self):
                return (self.wrapped.fp.read(ChunkedFile.CHUNKSIZE)
                        if self.wrapped.fp else None)

        return (ChunkedIndexable(ChunkedFile(key), key.size), key.size)

    def get_size(self, location):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file, and returns the image_size (or 0
        if unavailable)

        :param location `glance.store.location.Location` object, supplied
                        from glance.store.location.get_location_from_uri()
        """
        try:
            key = self._retrieve_key(location)
            return key.size
        except Exception:
            return 0

    def _retrieve_key(self, location):
        loc = location.store_location
        from boto.s3.connection import S3Connection

        s3_conn = S3Connection(loc.accesskey, loc.secretkey,
                               host=loc.s3serviceurl,
                               is_secure=(loc.scheme == 's3+https'),
                               calling_format=get_calling_format())
        bucket_obj = get_bucket(s3_conn, loc.bucket)

        key = get_key(bucket_obj, loc.key)

        msg = _("Retrieved image object from S3 using (s3_host=%(s3_host)s, "
                "access_key=%(accesskey)s, bucket=%(bucket)s, "
                "key=%(obj_name)s)") % ({'s3_host': loc.s3serviceurl,
                                         'accesskey': loc.accesskey,
                                         'bucket': loc.bucket,
                                         'obj_name': loc.key})
        LOG.debug(msg)

        return key

    def add(self, image_id, image_file, image_size):
        """
        Stores an image file with supplied identifier to the backend
        storage system and returns a tuple containing information
        about the stored image.

        :param image_id: The opaque image identifier
        :param image_file: The image data to write, as a file-like object
        :param image_size: The size of the image data to write, in bytes

        :retval tuple of URL in backing store, bytes written, checksum
                and a dictionary with storage system specific information
        :raises `glance.common.exception.Duplicate` if the image already
                existed

        S3 writes the image data using the scheme:
            s3://<ACCESS_KEY>:<SECRET_KEY>@<S3_URL>/<BUCKET>/<OBJ>
        where:
            <USER> = ``s3_store_user``
            <KEY> = ``s3_store_key``
            <S3_HOST> = ``s3_store_host``
            <BUCKET> = ``s3_store_bucket``
            <ID> = The id of the image being added
        """
        from boto.s3.connection import S3Connection

        loc = StoreLocation({'scheme': self.scheme,
                             'bucket': self.bucket,
                             'key': image_id,
                             's3serviceurl': self.full_s3_host,
                             'accesskey': self.access_key,
                             'secretkey': self.secret_key})

        s3_conn = S3Connection(loc.accesskey, loc.secretkey,
                               host=loc.s3serviceurl,
                               is_secure=(loc.scheme == 's3+https'),
                               calling_format=get_calling_format())

        create_bucket_if_missing(self.bucket, s3_conn)

        bucket_obj = get_bucket(s3_conn, self.bucket)
        obj_name = str(image_id)

        def _sanitize(uri):
            return re.sub('//.*:.*@',
                          '//s3_store_secret_key:s3_store_access_key@',
                          uri)

        key = bucket_obj.get_key(obj_name)
        if key and key.exists():
            raise exception.Duplicate(_("S3 already has an image at "
                                      "location %s") %
                                      _sanitize(loc.get_uri()))

        msg = _("Adding image object to S3 using (s3_host=%(s3_host)s, "
                "access_key=%(access_key)s, bucket=%(bucket)s, "
                "key=%(obj_name)s)") % ({'s3_host': self.s3_host,
                                         'access_key': self.access_key,
                                         'bucket': self.bucket,
                                         'obj_name': obj_name})
        LOG.debug(msg)

        key = bucket_obj.new_key(obj_name)

        # We need to wrap image_file, which is a reference to the
        # webob.Request.body_file, with a seekable file-like object,
        # otherwise the call to set_contents_from_file() will die
        # with an error about Input object has no method 'seek'. We
        # might want to call webob.Request.make_body_seekable(), but
        # unfortunately, that method copies the entire image into
        # memory and results in LP Bug #818292 occurring. So, here
        # we write temporary file in as memory-efficient manner as
        # possible and then supply the temporary file to S3. We also
        # take this opportunity to calculate the image checksum while
        # writing the tempfile, so we don't need to call key.compute_md5()

        msg = _("Writing request body file to temporary file "
                "for %s") % _sanitize(loc.get_uri())
        LOG.debug(msg)

        tmpdir = self.s3_store_object_buffer_dir
        temp_file = tempfile.NamedTemporaryFile(dir=tmpdir)
        checksum = hashlib.md5()
        for chunk in utils.chunkreadable(image_file, self.CHUNKSIZE):
            checksum.update(chunk)
            temp_file.write(chunk)
        temp_file.flush()

        msg = (_("Uploading temporary file to S3 for %s") %
               _sanitize(loc.get_uri()))
        LOG.debug(msg)

        # OK, now upload the data into the key
        key.set_contents_from_file(open(temp_file.name, 'r+b'), replace=False)
        size = key.size
        checksum_hex = checksum.hexdigest()

        LOG.debug(_("Wrote %(size)d bytes to S3 key named %(obj_name)s "
                    "with checksum %(checksum_hex)s"),
                  {'size': size, 'obj_name': obj_name,
                   'checksum_hex': checksum_hex})

        return (loc.get_uri(), size, checksum_hex, {})

    def delete(self, location):
        """
        Takes a `glance.store.location.Location` object that indicates
        where to find the image file to delete

        :location `glance.store.location.Location` object, supplied
                  from glance.store.location.get_location_from_uri()

        :raises NotFound if image does not exist
        """
        loc = location.store_location
        from boto.s3.connection import S3Connection
        s3_conn = S3Connection(loc.accesskey, loc.secretkey,
                               host=loc.s3serviceurl,
                               is_secure=(loc.scheme == 's3+https'),
                               calling_format=get_calling_format())
        bucket_obj = get_bucket(s3_conn, loc.bucket)

        # Close the key when we're through.
        key = get_key(bucket_obj, loc.key)

        msg = _("Deleting image object from S3 using (s3_host=%(s3_host)s, "
                "access_key=%(accesskey)s, bucket=%(bucket)s, "
                "key=%(obj_name)s)") % ({'s3_host': loc.s3serviceurl,
                                         'accesskey': loc.accesskey,
                                         'bucket': loc.bucket,
                                         'obj_name': loc.key})
        LOG.debug(msg)

        return key.delete()


def get_bucket(conn, bucket_id):
    """
    Get a bucket from an s3 connection

    :param conn: The ``boto.s3.connection.S3Connection``
    :param bucket_id: ID of the bucket to fetch
    :raises ``glance.exception.NotFound`` if bucket is not found.
    """

    bucket = conn.get_bucket(bucket_id)
    if not bucket:
        msg = _("Could not find bucket with ID %s") % bucket_id
        LOG.debug(msg)
        raise exception.NotFound(msg)

    return bucket


def get_s3_location(s3_host):
    from boto.s3.connection import Location
    locations = {
        's3.amazonaws.com': Location.DEFAULT,
        's3-eu-west-1.amazonaws.com': Location.EU,
        's3-us-west-1.amazonaws.com': Location.USWest,
        's3-ap-southeast-1.amazonaws.com': Location.APSoutheast,
        's3-ap-northeast-1.amazonaws.com': Location.APNortheast,
    }
    # strip off scheme and port if present
    key = re.sub('^(https?://)?(?P<host>[^:]+)(:[0-9]+)?$',
                 '\g<host>',
                 s3_host)
    return locations.get(key, Location.DEFAULT)


def create_bucket_if_missing(bucket, s3_conn):
    """
    Creates a missing bucket in S3 if the
    ``s3_store_create_bucket_on_put`` option is set.

    :param bucket: Name of bucket to create
    :param s3_conn: Connection to S3
    """
    from boto.exception import S3ResponseError
    try:
        s3_conn.get_bucket(bucket)
    except S3ResponseError as e:
        if e.status == httplib.NOT_FOUND:
            if CONF.s3_store_create_bucket_on_put:
                location = get_s3_location(CONF.s3_store_host)
                try:
                    s3_conn.create_bucket(bucket, location=location)
                except S3ResponseError as e:
                    msg = (_("Failed to add bucket to S3.\n"
                             "Got error from S3: %(e)s") % {'e': e})
                    raise glance.store.BackendException(msg)
            else:
                msg = (_("The bucket %(bucket)s does not exist in "
                         "S3. Please set the "
                         "s3_store_create_bucket_on_put option "
                         "to add bucket to S3 automatically.")
                       % {'bucket': bucket})
                raise glance.store.BackendException(msg)


def get_key(bucket, obj):
    """
    Get a key from a bucket

    :param bucket: The ``boto.s3.Bucket``
    :param obj: Object to get the key for
    :raises ``glance.exception.NotFound`` if key is not found.
    """

    key = bucket.get_key(obj)
    if not key or not key.exists():
        msg = (_("Could not find key %(obj)s in bucket %(bucket)s") %
               {'obj': obj, 'bucket': bucket})
        LOG.debug(msg)
        raise exception.NotFound(msg)
    return key


def get_calling_format(bucket_format=None):
    import boto.s3.connection
    if bucket_format is None:
        bucket_format = CONF.s3_store_bucket_url_format
    if bucket_format.lower() == 'path':
        return boto.s3.connection.OrdinaryCallingFormat()
    else:
        return boto.s3.connection.SubdomainCallingFormat()
