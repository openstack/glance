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

import unittest

from glance.common import context


class FakeImage(object):
    """
    Fake image for providing the image attributes needed for
    TestContext.
    """

    def __init__(self, owner, is_public):
        self.owner = owner
        self.is_public = is_public


class TestContext(unittest.TestCase):
    def do_visible(self, exp_res, img_owner, img_public, **kwargs):
        """
        Perform a context test.  Creates a (fake) image with the
        specified owner and is_public attributes, then creates a
        context with the given keyword arguments and expects exp_res
        as the result of an is_image_visible() call on the context.
        """

        img = FakeImage(img_owner, img_public)
        ctx = context.RequestContext(**kwargs)

        self.assertEqual(ctx.is_image_visible(img), exp_res)

    def test_empty_public(self):
        """
        Tests that an empty context (with is_admin set to True) can
        access an image with is_public set to True.
        """
        self.do_visible(True, None, True, is_admin=True)

    def test_empty_public_owned(self):
        """
        Tests that an empty context (with is_admin set to True) can
        access an owned image with is_public set to True.
        """
        self.do_visible(True, 'pattieblack', True, is_admin=True)

    def test_empty_private(self):
        """
        Tests that an empty context (with is_admin set to True) can
        access an image with is_public set to False.
        """
        self.do_visible(True, None, False, is_admin=True)

    def test_empty_private_owned(self):
        """
        Tests that an empty context (with is_admin set to True) can
        access an owned image with is_public set to False.
        """
        self.do_visible(True, 'pattieblack', False, is_admin=True)

    def test_anon_public(self):
        """
        Tests that an anonymous context (with is_admin set to False)
        can access an image with is_public set to True.
        """
        self.do_visible(True, None, True)

    def test_anon_public_owned(self):
        """
        Tests that an anonymous context (with is_admin set to False)
        can access an owned image with is_public set to True.
        """
        self.do_visible(True, 'pattieblack', True)

    def test_anon_private(self):
        """
        Tests that an anonymous context (with is_admin set to False)
        can access an unowned image with is_public set to False.
        """
        self.do_visible(True, None, False)

    def test_anon_private_owned(self):
        """
        Tests that an anonymous context (with is_admin set to False)
        cannot access an owned image with is_public set to False.
        """
        self.do_visible(False, 'pattieblack', False)

    def test_auth_public(self):
        """
        Tests that an authenticated context (with is_admin set to
        False) can access an image with is_public set to True.
        """
        self.do_visible(True, None, True, tenant='froggy')

    def test_auth_public_unowned(self):
        """
        Tests that an authenticated context (with is_admin set to
        False) can access an image (which it does not own) with
        is_public set to True.
        """
        self.do_visible(True, 'pattieblack', True, tenant='froggy')

    def test_auth_public_owned(self):
        """
        Tests that an authenticated context (with is_admin set to
        False) can access an image (which it does own) with is_public
        set to True.
        """
        self.do_visible(True, 'pattieblack', True, tenant='pattieblack')

    def test_auth_private(self):
        """
        Tests that an authenticated context (with is_admin set to
        False) can access an image with is_public set to False.
        """
        self.do_visible(True, None, False, tenant='froggy')

    def test_auth_private_unowned(self):
        """
        Tests that an authenticated context (with is_admin set to
        False) cannot access an image (which it does not own) with
        is_public set to False.
        """
        self.do_visible(False, 'pattieblack', False, tenant='froggy')

    def test_auth_private_owned(self):
        """
        Tests that an authenticated context (with is_admin set to
        False) can access an image (which it does own) with is_public
        set to False.
        """
        self.do_visible(True, 'pattieblack', False, tenant='pattieblack')
