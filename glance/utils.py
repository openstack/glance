# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 OpenStack LLC.
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

"""
A few utility routines used throughout Glance
"""
import errno
import logging

import xattr

logger = logging.getLogger('glance.utils')


def image_meta_to_http_headers(image_meta):
    """
    Returns a set of image metadata into a dict
    of HTTP headers that can be fed to either a Webob
    Request object or an httplib.HTTP(S)Connection object

    :param image_meta: Mapping of image metadata
    """
    headers = {}
    for k, v in image_meta.items():
        if v is None:
            v = ''
        if k == 'properties':
            for pk, pv in v.items():
                if pv is None:
                    pv = ''
                headers["x-image-meta-property-%s"
                        % pk.lower()] = unicode(pv)
        else:
            headers["x-image-meta-%s" % k.lower()] = unicode(v)
    return headers


def get_image_meta_from_headers(response):
    """
    Processes HTTP headers from a supplied response that
    match the x-image-meta and x-image-meta-property and
    returns a mapping of image metadata and properties

    :param response: Response to process
    """
    result = {}
    properties = {}

    if hasattr(response, 'getheaders'):  # httplib.HTTPResponse
        headers = response.getheaders()
    else:  # webob.Response
        headers = response.headers.items()

    for key, value in headers:
        key = str(key.lower())
        if key.startswith('x-image-meta-property-'):
            field_name = key[len('x-image-meta-property-'):].replace('-', '_')
            properties[field_name] = value or None
        elif key.startswith('x-image-meta-'):
            field_name = key[len('x-image-meta-'):].replace('-', '_')
            result[field_name] = value or None
    result['properties'] = properties
    if 'id' in result:
        result['id'] = int(result['id'])
    if 'size' in result:
        result['size'] = int(result['size'])
    if 'is_public' in result:
        result['is_public'] = bool_from_header_value(result['is_public'])
    if 'deleted' in result:
        result['deleted'] = bool_from_header_value(result['deleted'])
    return result


def bool_from_header_value(value):
    """
    Returns True if value is a boolean True or the
    string 'true', case-insensitive, False otherwise
    """
    if isinstance(value, bool):
        return value
    elif isinstance(value, (basestring, unicode)):
        if str(value).lower() == 'true':
            return True
    return False


def has_body(req):
    """
    Returns whether a Webob.Request object will possess an entity body.

    :param req:  Webob.Request object
    """
    return req.content_length or 'transfer-encoding' in req.headers


def chunkiter(fp, chunk_size=65536):
    """Return an iterator to a file-like obj which yields fixed size chunks

    :param fp: a file-like object
    :param chunk_size: maximum size of chunk
    """
    while True:
        chunk = fp.read(chunk_size)
        if chunk:
            yield chunk
        else:
            break


class PrettyTable(object):
    """Creates an ASCII art table for use in bin/glance

    Example:

        ID  Name              Size         Hits
        --- ----------------- ------------ -----
        122 image                       22     0
    """
    def __init__(self):
        self.columns = []

    def add_column(self, width, label="", just='l'):
        """Add a column to the table

        :param width: number of characters wide the column should be
        :param label: column heading
        :param just: justification for the column, 'l' for left,
                     'r' for right
        """
        self.columns.append((width, label, just))

    def make_header(self):
        label_parts = []
        break_parts = []
        for width, label, _ in self.columns:
            # NOTE(sirp): headers are always left justified
            label_part = self._clip_and_justify(label, width, 'l')
            label_parts.append(label_part)

            break_part = '-' * width
            break_parts.append(break_part)

        label_line = ' '.join(label_parts)
        break_line = ' '.join(break_parts)
        return '\n'.join([label_line, break_line])

    def make_row(self, *args):
        row = args
        row_parts = []
        for data, (width, _, just) in zip(row, self.columns):
            row_part = self._clip_and_justify(data, width, just)
            row_parts.append(row_part)

        row_line = ' '.join(row_parts)
        return row_line

    @staticmethod
    def _clip_and_justify(data, width, just):
        # clip field to column width
        clipped_data = str(data)[:width]

        if just == 'r':
            # right justify
            justified = clipped_data.rjust(width)
        else:
            # left justify
            justified = clipped_data.ljust(width)

        return justified


def _make_namespaced_xattr_key(key, namespace='user'):
    """Create a fully-qualified xattr-key by including the intended namespace.

    Namespacing differs among OSes[1]:

        FreeBSD: user, system
        Linux: user, system, trusted, security
        MacOS X: not needed

    Mac OS X won't break if we include a namespace qualifier, so, for
    simplicity, we always include it.

    --
    [1] http://en.wikipedia.org/wiki/Extended_file_attributes
    """
    namespaced_key = ".".join([namespace, key])
    return namespaced_key


def get_xattr(path, key, **kwargs):
    """Return the value for a particular xattr

    If the key doesn't not exist, or xattrs aren't supported by the file
    system then a KeyError will be raised, that is, unless you specify a
    default using kwargs.
    """
    namespaced_key = _make_namespaced_xattr_key(key)
    entry_xattr = xattr.xattr(path)
    try:
        return entry_xattr[namespaced_key]
    except KeyError:
        if 'default' in kwargs:
            return kwargs['default']
        else:
            raise


def set_xattr(path, key, value):
    """Set the value of a specified xattr.

    If xattrs aren't supported by the file-system, we skip setting the value.
    """
    namespaced_key = _make_namespaced_xattr_key(key)
    entry_xattr = xattr.xattr(path)
    try:
        entry_xattr.set(namespaced_key, str(value))
    except IOError as e:
        if e.errno == errno.EOPNOTSUPP:
            logger.warn(_("xattrs not supported, skipping..."))
        else:
            raise


def inc_xattr(path, key, n=1):
    """Increment the value of an xattr (assuming it is an integer).

    BEWARE, this code *does* have a RACE CONDITION, since the
    read/update/write sequence is not atomic.

    Since the use-case for this function is collecting stats--not critical--
    the benefits of simple, lock-free code out-weighs the possibility of an
    occasional hit not being counted.
    """
    try:
        count = int(get_xattr(path, key))
    except KeyError:
        # NOTE(sirp): a KeyError is generated in two cases:
        # 1) xattrs is not supported by the filesystem
        # 2) the key is not present on the file
        #
        # In either case, just ignore it...
        pass
    else:
        # NOTE(sirp): only try to bump the count if xattrs is supported
        # and the key is present
        count += n
        set_xattr(path, key, str(count))
