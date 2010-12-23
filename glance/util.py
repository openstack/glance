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


def image_meta_to_http_headers(image_meta):
    """
    Returns a set of image metadata into a dict
    of HTTP headers that can be fed to either a Webob
    Request object or an httplib.HTTP(S)Connection object

    :param image_meta: Mapping of image metadata
    """
    headers = {}
    for k, v in image_meta.iteritems():
        if k == 'properties':
            for pk, pv in v.iteritems():
                headers["x-image-meta-property-%s"
                        % pk.lower()] = pv

        headers["x-image-meta-%s" % k.lower()] = v
    return headers


def inject_image_meta_into_headers(response, image_meta):
    """
    Given a response and mapping of image metadata, injects
    the Response with a set of HTTP headers for the image
    metadata. Each main image metadata field is injected
    as a HTTP header with key 'x-image-meta-<FIELD>' except
    for the properties field, which is further broken out
    into a set of 'x-image-meta-property-<KEY>' headers

    :param response: The Webob Response object
    :param image_meta: Mapping of image metadata
    """
    headers = image_meta_to_http_headers(image_meta)

    for k, v in headers.iteritems():
        response.headers.add(k, v)


def get_image_meta_from_headers(response):
    """
    Processes HTTP headers from a supplied response that
    match the x-image-meta and x-image-meta-property and
    returns a mapping of image metadata and properties

    :param response: Response to process
    """
    result = {}
    properties = {}
    for key, value in response.headers.iteritems():
        key = str(key.lower())
        if key.startswith('x-image-meta-property-'):
            properties[key[len('x-image-meta-property-'):]] = value
        if key.startswith('x-image-meta-'):
            field_name = key[len('x-image-meta-'):].replace('-', '_')
            result[field_name] = value
    result['properties'] = properties
    return result
