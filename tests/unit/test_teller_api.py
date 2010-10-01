import unittest
from webob import Request, exc
from glance.teller import parallax
from glance.teller.api import images as image_server

class TestImageController(unittest.TestCase):
    def setUp(self):
        fake_parallax = parallax.FakeParallaxAdapter

        self.image_controller = image_server.Controller()
        self.image_controller.image_lookup_fn = fake_parallax.lookup

    def test_show_image_with_no_uri_should_raise_http_bad_request(self):
        # uri must be specified
        request = Request.blank("/image")
        response = self.image_controller.show(request, None)
        self.assertEqual(response.status_int, 400) # should be 422?

    def test_show_image_where_image_exists_should_return_the_data(self):
        # FIXME: need urllib.quote here?
        image_uri = "http://parallax-success/myacct/my-image"
        request = Request.blank("/image?uri=%s" % image_uri)
        response = self.image_controller.show(request, image_uri)
        self.assertEqual("//chunk0//chunk1", response.body)

    def test_show_image_where_image_doesnt_exist_should_raise_not_found(self):
        image_uri = "http://parallax-failure/myacct/does-not-exist"
        request = Request.blank("/image?uri=%s" % image_uri)
        self.assertRaises(exc.HTTPNotFound, self.image_controller.show, request,
                          image_uri)

if __name__ == "__main__":
    unittest.main()
