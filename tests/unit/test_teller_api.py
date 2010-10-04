import unittest
from webob import Request, exc
from glance.teller import controllers

class TestImageController(unittest.TestCase):
    def setUp(self):
        self.image_controller = controllers.ImageController()

    def test_index_image_with_no_uri_should_raise_http_bad_request(self):
        # uri must be specified
        request = Request.blank("/image")
        response = self.image_controller.index(request)
        self.assertEqual(response.status_int, 400) # should be 422?

    def test_index_image_unrecognized_registry_adapter(self):
        # FIXME: need urllib.quote here?
        image_uri = "http://parallax-success/myacct/my-image"
        request = self._make_request(image_uri, "unknownregistry")
        response = self.image_controller.index(request)
        self.assertEqual(response.status_int, 400) # should be 422?

    def test_index_image_where_image_exists_should_return_the_data(self):
        # FIXME: need urllib.quote here?
        image_uri = "http://parallax-success/myacct/my-image"
        request = self._make_request(image_uri)
        response = self.image_controller.index(request)
        self.assertEqual("//chunk0//chunk1", response.body)

    def test_index_image_where_image_doesnt_exist_should_raise_not_found(self):
        image_uri = "http://parallax-failure/myacct/does-not-exist"
        request = self._make_request(image_uri)
        self.assertRaises(exc.HTTPNotFound, self.image_controller.index,
                          request)

    def _make_request(self, image_uri, registry="fake_parallax"):
        return Request.blank(
            "/image?uri=%s&registry=%s" % (image_uri, registry))


if __name__ == "__main__":
    unittest.main()
