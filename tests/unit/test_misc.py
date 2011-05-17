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
import unittest


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
        topdir = os.path.normpath(os.path.dirname(__file__) + '/../../')
        if os.path.exists(os.path.join(topdir, '.bzr')):
            contributors = set()

            mailmap = parse_mailmap(os.path.join(topdir, '.mailmap'))

            import bzrlib.workingtree
            tree = bzrlib.workingtree.WorkingTree.open(topdir)
            tree.lock_read()
            try:
                parents = tree.get_parent_ids()
                g = tree.branch.repository.get_graph()
                for p in parents:
                    rev_ids = [r for r, _ in g.iter_ancestry(parents)
                               if r != "null:"]
                    revs = tree.branch.repository.get_revisions(rev_ids)
                    for r in revs:
                        for author in r.get_apparent_authors():
                            email = author.split(' ')[-1]
                            mailmapped = str_dict_replace(email, mailmap)
                            contributors.add(mailmapped)

                authors_file = open(os.path.join(topdir, 'Authors'),
                                    'r').read()

                missing = set()
                for contributor in contributors:
                    if contributor == 'glance-core':
                        continue
                    if not contributor in authors_file:
                        missing.add(contributor)

                self.assertTrue(len(missing) == 0,
                                '%r not listed in Authors' % missing)
            finally:
                tree.unlock()
