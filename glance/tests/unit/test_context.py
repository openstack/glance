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

from glance import context
from glance.openstack.common import local
from glance.tests.unit import utils as unit_utils
from glance.tests import utils


def _fake_image(owner, is_public):
    return {
        'id': None,
        'owner': owner,
        'is_public': is_public,
    }


def _fake_membership(can_share=False):
    return {'can_share': can_share}


class TestContext(utils.BaseTestCase):
    def setUp(self):
        super(TestContext, self).setUp()
        self.db_api = unit_utils.FakeDB()

    def do_visible(self, exp_res, img_owner, img_public, **kwargs):
        """
        Perform a context visibility test.  Creates a (fake) image
        with the specified owner and is_public attributes, then
        creates a context with the given keyword arguments and expects
        exp_res as the result of an is_image_visible() call on the
        context.
        """

        img = _fake_image(img_owner, img_public)
        ctx = context.RequestContext(**kwargs)

        self.assertEqual(self.db_api.is_image_visible(ctx, img), exp_res)

    def do_sharable(self, exp_res, img_owner, membership=None, **kwargs):
        """
        Perform a context sharability test.  Creates a (fake) image
        with the specified owner and is_public attributes, then
        creates a context with the given keyword arguments and expects
        exp_res as the result of an is_image_sharable() call on the
        context.  If membership is not None, its value will be passed
        in as the 'membership' keyword argument of
        is_image_sharable().
        """

        img = _fake_image(img_owner, True)
        ctx = context.RequestContext(**kwargs)

        sharable_args = {}
        if membership is not None:
            sharable_args['membership'] = membership

        output = self.db_api.is_image_sharable(ctx, img, **sharable_args)
        self.assertEqual(exp_res, output)

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

    def test_empty_shared(self):
        """
        Tests that an empty context (with is_admin set to False) can
        not share an image, with or without membership.
        """
        self.do_sharable(False, 'pattieblack', None, is_admin=False)
        self.do_sharable(False, 'pattieblack', _fake_membership(True),
                         is_admin=False)

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

    def test_anon_shared(self):
        """
        Tests that an empty context (with is_admin set to True) can
        not share an image, with or without membership.
        """
        self.do_sharable(False, 'pattieblack', None)
        self.do_sharable(False, 'pattieblack', _fake_membership(True))

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

    def test_auth_sharable(self):
        """
        Tests that an authenticated context (with is_admin set to
        False) cannot share an image it neither owns nor is shared
        with it.
        """
        self.do_sharable(False, 'pattieblack', None, tenant='froggy')

    def test_auth_sharable_admin(self):
        """
        Tests that an authenticated context (with is_admin set to
        True) can share an image it neither owns nor is shared with
        it.
        """
        self.do_sharable(True, 'pattieblack', None, tenant='froggy',
                         is_admin=True)

    def test_auth_sharable_owned(self):
        """
        Tests that an authenticated context (with is_admin set to
        False) can share an image it owns, even if it is not shared
        with it.
        """
        self.do_sharable(True, 'pattieblack', None, tenant='pattieblack')

    def test_auth_sharable_cannot_share(self):
        """
        Tests that an authenticated context (with is_admin set to
        False) cannot share an image it does not own even if it is
        shared with it, but with can_share = False.
        """
        self.do_sharable(False, 'pattieblack', _fake_membership(False),
                         tenant='froggy')

    def test_auth_sharable_can_share(self):
        """
        Tests that an authenticated context (with is_admin set to
        False) can share an image it does not own if it is shared with
        it with can_share = True.
        """
        self.do_sharable(True, 'pattieblack', _fake_membership(True),
                         tenant='froggy')

    def test_request_id(self):
        contexts = [context.RequestContext().request_id for _ in range(5)]
        # Check for uniqueness -- set() will normalize its argument
        self.assertEqual(5, len(set(contexts)))

    def test_service_catalog(self):
        ctx = context.RequestContext(service_catalog=['foo'])
        self.assertEqual(['foo'], ctx.service_catalog)

    def test_context_local_store(self):
        if hasattr(local.store, 'context'):
            del local.store.context
        ctx = context.RequestContext()
        self.assertTrue(hasattr(local.store, 'context'))
        self.assertEqual(ctx, local.store.context)
