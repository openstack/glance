import unittest
from StringIO import StringIO
from teller.backends import Backend, get_from_backend

class TellerTest(unittest.TestCase):
    pass

class TestBackends(TellerTest):
    def setUp(self):
        Backend.CHUNKSIZE = 2

    def test_filesystem_get_from_backend(self):
        class FakeFile(object):
            def __enter__(self, *args, **kwargs):
                return StringIO('fakedata')
            def __exit__(self, *args, **kwargs):
                pass

        fetcher = get_from_backend("file:///path/to/file.tar.gz",
                                   opener=lambda _: FakeFile())

        chunks = [c for c in fetcher]
        self.assertEqual(chunks, ["fa", "ke", "da", "ta"])

    def test_http_get_from_backend(self):
        class FakeHTTPConnection(object):
            def __init__(self, *args, **kwargs):
                pass
            def request(self, *args, **kwargs):
                pass
            def getresponse(self):
                return StringIO('fakedata')
            def close(self):
                pass

        fetcher = get_from_backend("http://netloc/path/to/file.tar.gz",
                                   conn_class=FakeHTTPConnection)

        chunks = [c for c in fetcher]
        self.assertEqual(chunks, ["fa", "ke", "da", "ta"])



if __name__ == "__main__":
    unittest.main()
