import urlparse

class BackendException(Exception):
    pass
class UnsupportedBackend(BackendException):
    pass

class Backend(object):
    CHUNKSIZE = 4096

class FilesystemBackend(Backend):
    @classmethod
    def get(cls, parsed_uri, opener=lambda p: open(p, "b")):
        """
        file:///path/to/file.tar.gz.0
        """
        def sanitize_path(p):
            #FIXME: must prevent attacks using ".." and "." paths
            return p

        with opener(sanitize_path(parsed_uri.path)) as f:
            chunk = f.read(cls.CHUNKSIZE)
            while chunk:
                yield chunk
                chunk = f.read(cls.CHUNKSIZE)
         
class HTTPBackend(Backend):
    @classmethod
    def get(cls, parsed_uri, conn_class=None):
        """
        http://netloc/path/to/file.tar.gz.0
        https://netloc/path/to/file.tar.gz.0
        """
        import httplib
        if conn_class:
            pass # use the conn_class passed in
        elif parsed_uri.scheme == "http":
            conn_class = httplib.HTTPConnection
        elif parsed_uri.scheme == "https":
            conn_class = httplib.HTTPSConnection
        else:
            raise BackendException("scheme '%s' not support for HTTPBackend")
        conn = conn_class(parsed_uri.netloc)
        conn.request("GET", parsed_uri.path, "", {})
        try:
            response = conn.getresponse()
            chunk = response.read(cls.CHUNKSIZE)
            while chunk:
                yield chunk
                chunk = response.read(cls.CHUNKSIZE)
        finally:
            conn.close()

def _scheme2backend(scheme):
    return {
        "file": FilesystemBackend,
        "http": HTTPBackend,
        "https": HTTPBackend
    }[scheme]

def get_from_backend(uri, **kwargs):
    """
    Yields chunks of data from backend specified by uri
    """
    parsed_uri = urlparse.urlparse(uri)
    try:
        return _scheme2backend(parsed_uri.scheme).get(parsed_uri, **kwargs)
    except KeyError:
        raise UnsupportedBackend("No backend found for '%s'" % parsed_uri.scheme)


