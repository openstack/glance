import unittest
from webob import Request
from glance.teller import parallax
from glance.teller import server as image_server

class TestImageController(unittest.TestCase):
    def setUp(self):
        conf = {}
        fake_parallax = parallax.FakeParallaxAdapter

        self.image_controller = image_server.ImageController(conf)
        self.image_controller.image_lookup_fn = fake_parallax.lookup

    def test_GET_success(self):
        # uri must be specified
        request = Request.blank("/image")
        response = self.image_controller.GET(request)
        self.assertEqual(response.status_int, 400) # should be 422?

        # FIXME: need urllib.quote here?
        image_uri = "http://parallax-success/myacct/my-image"
        request = Request.blank("/image?uri=%s" % image_uri)
        response = self.image_controller.GET(request)
        self.assertEqual("//chunk0//chunk1", response.body)

    def test_GET_failure(self):
        image_uri = "http://parallax-failure/myacct/does-not-exist"
        request = Request.blank("/image?uri=%s" % image_uri)
        response = self.image_controller.GET(request)
        self.assertEqual(response.status_int, 404)

if __name__ == "__main__":
    unittest.main()
