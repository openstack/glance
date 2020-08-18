# Copyright 2018 Verizon Wireless
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

import six
import time

from oslo_serialization import jsonutils
from oslo_utils import timeutils
import requests
from six.moves import http_client as http


def verify_image_hashes_and_status(
        test_obj, image_id, checksum=None, os_hash_value=None, status=None,
        os_hash_algo='sha512'):
    """Makes image-detail request and checks response.

    :param test_obj: The test object; expected to have _url() and
                     _headers() defined on it
    :param image_id: Image id to use in the request
    :param checksum: Expected checksum (default: None)
    :param os_hash_value: Expected multihash value (default: None)
    :param status: Expected status (default: None)
    :param os_hash_algo: Expected value of os_hash_algo; only checked when
                         os_hash_value is not None (default: 'sha512')
    """
    path = test_obj._url('/v2/images/%s' % image_id)
    response = requests.get(path, headers=test_obj._headers())
    test_obj.assertEqual(http.OK, response.status_code)
    image = jsonutils.loads(response.text)
    test_obj.assertEqual(checksum, image['checksum'])
    if os_hash_value:
        # make sure we're using the hashing_algorithm we expect
        test_obj.assertEqual(six.text_type(os_hash_algo),
                             image['os_hash_algo'])
    test_obj.assertEqual(os_hash_value, image['os_hash_value'])
    test_obj.assertEqual(status, image['status'])


def wait_for_status(request_path, request_headers, status='active',
                    max_sec=10, delay_sec=0.2, start_delay_sec=None):
    """
    Performs a time-bounded wait for the entity at the request_path to
    reach the requested status.

    :param request_path: path to use to make the request
    :param request_headers: headers to use when making the request
    :param status: the status to wait for (default: 'active')
    :param max_sec: the maximum number of seconds to wait (default: 10)
    :param delay_sec: seconds to sleep before the next request is
                      made (default: 0.2)
    :param start_delay_sec: seconds to wait before making the first
                            request (default: None)
    :raises Exception: if the entity fails to reach the status within
                       the requested time or if the server returns something
                       other than a 200 response
    """
    start_time = time.time()
    done_time = start_time + max_sec
    if start_delay_sec:
        time.sleep(start_delay_sec)
    while time.time() <= done_time:
        resp = requests.get(request_path, headers=request_headers)
        if resp.status_code != http.OK:
            raise Exception("Received {} response from server".format(
                resp.status_code))
        entity = jsonutils.loads(resp.text)
        if entity['status'] == status:
            return
        time.sleep(delay_sec)
    entity_id = request_path.rsplit('/', 1)[1]
    msg = "Entity {0} failed to reach status '{1}' within {2} sec"
    raise Exception(msg.format(entity_id, status, max_sec))


def wait_for_copying(request_path, request_headers, stores=[],
                     max_sec=10, delay_sec=0.2, start_delay_sec=None,
                     failure_scenario=False):
    """
    Performs a time-bounded wait for the entity at the request_path to
    wait until image is copied to specified stores.

    :param request_path: path to use to make the request
    :param request_headers: headers to use when making the request
    :param stores: list of stores to copy
    :param max_sec: the maximum number of seconds to wait (default: 10)
    :param delay_sec: seconds to sleep before the next request is
                      made (default: 0.2)
    :param start_delay_sec: seconds to wait before making the first
                            request (default: None)
    :raises Exception: if the entity fails to reach the status within
                       the requested time or if the server returns something
                       other than a 200 response
    """
    start_time = time.time()
    done_time = start_time + max_sec
    if start_delay_sec:
        time.sleep(start_delay_sec)
    while time.time() <= done_time:
        resp = requests.get(request_path, headers=request_headers)
        if resp.status_code != http.OK:
            raise Exception("Received {} response from server".format(
                resp.status_code))
        entity = jsonutils.loads(resp.text)
        all_copied = False
        for store in stores:
            if store in entity['stores']:
                all_copied = True
            else:
                all_copied = False

        if all_copied:
            return

        time.sleep(delay_sec)

    if not failure_scenario:
        entity_id = request_path.rsplit('/', 1)[1]
        msg = "Entity {0} failed to copy image to stores '{1}' within {2} sec"
        raise Exception(msg.format(entity_id, ",".join(stores), max_sec))


def poll_entity(url, headers, callback, max_sec=10, delay_sec=0.2,
                require_success=True):
    """Poll a given URL passing the parsed entity to a callback.

    This is a utility method that repeatedly GETs a URL, and calls
    a callback with the result. The callback determines if we should
    keep polling by returning True (up to the timeout).

    :param url: The url to fetch
    :param headers: The request headers to use for the fetch
    :param callback: A function that takes the parsed entity and is expected
                     to return True if we should keep polling
    :param max_sec: The overall timeout before we fail
    :param delay_sec: The time between fetches
    :param require_success: Assert resp_code is http.OK each time before
                            calling the callback
    """

    timer = timeutils.StopWatch(max_sec)
    timer.start()

    while not timer.expired():
        resp = requests.get(url, headers=headers)
        if require_success and resp.status_code != http.OK:
            raise Exception(
                'Received %i response from server' % resp.status_code)
        entity = resp.json()
        keep_polling = callback(entity)
        if keep_polling is not True:
            return keep_polling
        time.sleep(delay_sec)

    raise Exception('Poll timeout if %i seconds exceeded!' % max_sec)
