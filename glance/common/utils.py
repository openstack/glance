# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
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
System-level utilities and helper functions.
"""

import datetime
import errno
import inspect
import logging
import os
import random
import subprocess
import socket
import sys
import uuid

from glance.common import exception


logger = logging.getLogger(__name__)

TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def chunkiter(fp, chunk_size=65536):
    """
    Return an iterator to a file-like obj which yields fixed size chunks

    :param fp: a file-like object
    :param chunk_size: maximum size of chunk
    """
    while True:
        chunk = fp.read(chunk_size)
        if chunk:
            yield chunk
        else:
            break


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
    if 'size' in result:
        result['size'] = int(result['size'])
    for key in ('is_public', 'deleted', 'protected'):
        if key in result:
            result[key] = bool_from_header_value(result[key])
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


def bool_from_string(subject):
    """
    Interpret a string as a boolean.

    Any string value in:
        ('True', 'true', 'On', 'on', '1')
    is interpreted as a boolean True.

    Useful for JSON-decoded stuff and config file parsing
    """
    if isinstance(subject, bool):
        return subject
    elif isinstance(subject, int):
        return subject == 1
    if hasattr(subject, 'startswith'):  # str or unicode...
        if subject.strip().lower() in ('true', 'on', '1'):
            return True
    return False


def import_class(import_str):
    """Returns a class from a string including module and class"""
    mod_str, _sep, class_str = import_str.rpartition('.')
    try:
        __import__(mod_str)
        return getattr(sys.modules[mod_str], class_str)
    except (ImportError, ValueError, AttributeError), e:
        raise exception.ImportFailure(import_str=import_str,
                                      reason=e)


def import_object(import_str):
    """Returns an object including a module or module and class"""
    try:
        __import__(import_str)
        return sys.modules[import_str]
    except ImportError:
        cls = import_class(import_str)
        return cls()


def generate_uuid():
    return str(uuid.uuid4())


def is_uuid_like(value):
    try:
        uuid.UUID(value)
        return True
    except Exception:
        return False


def isotime(at=None):
    if not at:
        at = datetime.datetime.utcnow()
    return at.strftime(TIME_FORMAT)


def parse_isotime(timestr):
    return datetime.datetime.strptime(timestr, TIME_FORMAT)


def safe_mkdirs(path):
    try:
        os.makedirs(path)
    except OSError, e:
        if e.errno != errno.EEXIST:
            raise


def safe_remove(path):
    try:
        os.remove(path)
    except OSError, e:
        if e.errno != errno.ENOENT:
            raise


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
