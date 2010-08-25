import unittest
from webob import Request
#TODO: should this be teller.image ?
from teller import server as image_server

class TestImageController(unittest.TestCase):
    def setUp(self):
        conf = {}
        self.image_controller = image_server.ImageController(conf)

    def test_GET(self):
        # uri must be specified
        request = Request.blank("/image")
        response = self.image_controller.GET(request)
        self.assertEqual(response.status_int, 400) # should be 422?

        # FIXME: need urllib.quote here?
        image_uri = "http://parallax/myacct/my-image"
        request = Request.blank("/image?uri=%s" % image_uri)
        def mock_parallax_lookup(uri):
            return {"objects": [{"uri": "teststr://chunk0"},
                                {"uri": "teststr://chunk1"}]}

        self.image_controller.image_lookup_fn = mock_parallax_lookup
        response = self.image_controller.GET(request)
        self.assertEqual("chunk0chunk1", response.body)

        image_uri = "http://parallax/myacct/does-not-exist"
        request = Request.blank("/image?uri=%s" % image_uri)
        def mock_parallax_lookup(uri):
            return None
        self.image_controller.image_lookup_fn = mock_parallax_lookup
        response = self.image_controller.GET(request)
        self.assertEqual(response.status_int, 404)

if __name__ == "__main__":
    unittest.main()
