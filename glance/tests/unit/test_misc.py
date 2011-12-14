# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack, LLC
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

import os
import commands
import datetime
import re
import unittest

from glance.common import crypt
from glance.common import exception
from glance.common import utils


def parse_mailmap(mailmap='.mailmap'):
    mapping = {}
    if os.path.exists(mailmap):
        fp = open(mailmap, 'r')
        for l in fp:
            l = l.strip()
            if not l.startswith('#') and ' ' in l:
                canonical_email, alias = l.split(' ')
                mapping[alias] = canonical_email
    return mapping


def str_dict_replace(s, mapping):
    for s1, s2 in mapping.iteritems():
        s = s.replace(s1, s2)
    return s


class AuthorsTestCase(unittest.TestCase):
    def test_authors_up_to_date(self):

        topdir = os.path.normpath(os.path.dirname(__file__) + '/../../..')
        contributors = set()
        missing = set()
        authors_file = open(os.path.join(topdir, 'Authors'), 'r').read()

        if os.path.exists(os.path.join(topdir, '.git')):
            mailmap = parse_mailmap(os.path.join(topdir, '.mailmap'))
            for email in commands.getoutput('git log --format=%ae').split():
                if not email:
                    continue
                if "jenkins" in email and "openstack.org" in email:
                    continue
                email = '<' + email + '>'
                contributors.add(str_dict_replace(email, mailmap))

        for contributor in contributors:
            if contributor == 'glance-core':
                continue
            if not contributor in authors_file:
                missing.add(contributor)

        self.assertTrue(len(missing) == 0,
                        '%r not listed in Authors' % missing)


class UtilsTestCase(unittest.TestCase):

    def test_bool_from_string(self):
        true_values = ['True', True, 'true', 'TRUE', '1', 1, 'on', 'ON']

        i = 0
        for value in true_values:
            self.assertTrue(utils.bool_from_string(value),
                            "Got False for value: %r (%d)" % (value, i))
            i = i + 1

        false_values = ['False', False, 'false', 'T', 'F', 'FALSE',
                        '0', 0, 9, 'off', 'OFF']

        for value in false_values:
            self.assertFalse(utils.bool_from_string(value),
                             "Got True for value: %r" % value)

    def test_import_class_or_object(self):
        # Test that import_class raises a descriptive error when the
        # class to import could not be found.
        self.assertRaises(exception.ImportFailure, utils.import_class,
                          'nomodule')

        self.assertRaises(exception.ImportFailure, utils.import_class,
                          'mymodule.nonexistingclass')

        self.assertRaises(exception.ImportFailure, utils.import_class,
                          'sys.nonexistingclass')

        self.assertRaises(exception.ImportFailure, utils.import_object,
                          'os.path.NONEXISTINGOBJECT')

        store_class = utils.import_class('glance.store.s3.Store')

        self.assertTrue(store_class.__name__ == 'Store')

        # Try importing an object by supplying a class and
        # verify the object's class name is the same as that supplied
        ex_obj = utils.import_object('glance.common.exception.GlanceException')

        self.assertTrue(ex_obj.__class__.__name__ == 'GlanceException')

        # Try importing a module itself
        module_obj = utils.import_object('glance.registry')

        self.assertEqual('glance.registry', module_obj.__package__)

    def test_isotime(self):
        dt1 = datetime.datetime(2001, 11, 10, 1, 2, 3)
        self.assertEqual('2001-11-10T01:02:03Z', utils.isotime(dt1))

        iso_re = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z')
        now_iso = utils.isotime()
        self.assertTrue(iso_re.match(now_iso) is not None)

    def test_encryption(self):
        # Check that original plaintext and unencrypted ciphertext match
        # Check keys of the three allowed lengths
        key_list = ["1234567890abcdef",
                    "12345678901234567890abcd",
                    "1234567890abcdef1234567890ABCDEF"]
        plaintext_list = ['']
        blocksize = 64
        for i in range(3 * blocksize):
            plaintext_list.append(os.urandom(i))

        for key in key_list:
            for plaintext in plaintext_list:
                ciphertext = crypt.urlsafe_encrypt(key, plaintext, blocksize)
                self.assertTrue(ciphertext != plaintext)
                text = crypt.urlsafe_decrypt(key, ciphertext)
                self.assertTrue(plaintext == text)
