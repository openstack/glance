=======================
Running Glance in HTTPD
=======================

In short Glance will not operate properly if tried to be ran without eventlet
and introducing another web server into the mix does not make it any better.
This exercise failed without ever having proper interest or resources to fix
the underlying issues.

None of the models deploying Glance as bare wsgi app under some httpd are
currently adviced.

Since the Pike release Glance has packaged a wsgi script entrypoint that
enables you to run it with a real web server like Apache HTTPD or nginx. To
deploy this there are several patterns, which all fail different ways. This doc
mentions three common ways of trying to deploy Glance with Apache HTTPD.

.. warning::
   As pointed out in the Pike and Queens release notes (see the "Known Issues"
   section of each), the Glance project team recommends that Glance be run in
   its normal standalone configuration, particularly in production
   environments.  The full functionality of Glance is not available when Glance
   is deployed in the manner described in this document.  In particular, the
   interoperable image import functionality does not work under such
   configuration.  See the release notes for details.

uWSGI Server HTTP Mode
----------------------

This has never worked properly nor it has been of any development focus.

The clearest we can say is just don't do it.

.. _mod_proxy_uwsgi:

mod_proxy_uwsgi
'''''''''''''''

.. WARNING::

    Running Glance under HTTPD in this configuration will only work on Python 2
    if you use ``Transfer-Encoding: chunked``. Also if running with Python 2
    Apache will be buffering the chunked encoding before passing the request
    on to uWSGI. See bug: https://github.com/unbit/uwsgi/issues/1540
    The async tasks, namely (by default) admin only tasks API and Interoperable
    Image Import will not work under uWSGI even with proxying. There might be
    problems with reload and graceful shutdowns of the service that are not
    documented elsewhere. Treat this as any uWSGI deployment, not supported.

Instead of running uWSGI as a webserver listening on a local port and then
having Apache HTTP proxy all the incoming requests with mod_proxy. The
normally recommended way of deploying the uWSGI server with Apache HTTPD is to
use mod_proxy_uwsgi and set up a local socket file for uWSGI to listen on.
Apache will send the requests using the uwsgi protocol over this local socket
file. However, there are issues with doing this and using chunked-encoding, so
this is not recommended for use with Glance.

You can work around these issues by configuring your Apache proxy to buffer the
chunked data and send the full content length to the uWSGI server. You do this
by adding::

    SetEnv proxy-sendcl 1

to the apache config file using mod_proxy_uwsgi. For more details on using
mod_proxy_uwsgi see the official docs:
http://uwsgi-docs.readthedocs.io/en/latest/Apache.html?highlight=mod_uwsgi_proxy#mod-proxy-uwsgi

There are some additional considerations when doing this though. Having Apache
locally buffer the chunked data to disk before passing it to uWSGI means you'll
need to have sufficient disk space in /tmp (or whatever you set TMPDIR to) to
store all the disk files. The other aspect to consider is that this buffering
can take some time to write the images to disk. To prevent random failures
you'll likely have to increase timeout values in the uWSGI configuration file
to ensure uWSGI will wait long enough for this to happen. (Depending on the
uploaded image file sizes it may be necessary to set the timeouts to multiple
minutes.)

mod_wsgi
--------

This deployment method is not recommended for using Glance. The mod_wsgi
protocol does not support ``Transfer-Encoding: chunked`` and therefore makes it
unsuitable for use with Glance. However, you could theoretically deploy Glance
using mod_wsgi but it will fail on any requests that use a chunked transfer
encoding.

.. _uwsgi_glossary:

Glossary
--------

.. glossary::

  uwsgi
    The native protocol used by the uWSGI server. (The acronym is written in
    all lowercase on purpose.)

    https://uwsgi-docs.readthedocs.io/en/latest/Protocol.html

  uWSGI
    A project that aims at developing a full stack for building hosting
    services.  It produces software, the uWSGI server, that is exposed in
    Python code as a module named ``uwsgi``.

    https://uwsgi-docs.readthedocs.io/en/latest/index.html

    https://pypi.org/project/uWSGI/

    https://github.com/unbit/uwsgi

  mod_wsgi
    An Apache 2 HTTP server module that supports the Python WSGI
    specification.

    https://modwsgi.readthedocs.io/en/develop/

  mod_proxy_uwsgi
    An Apache 2 HTTP Server module that provides a uwsgi gateway for
    mod_proxy. It communicates to the uWSGI server using the uwsgi protocol.

    http://httpd.apache.org/docs/trunk/mod/mod_proxy_uwsgi.html

  WSGI
    Web Server Gateway Interface, a Python standard published as `PEP 3333`_.

    https://wsgi.readthedocs.io/en/latest/index.html

    .. _PEP 3333: https://www.python.org/dev/peps/pep-3333
