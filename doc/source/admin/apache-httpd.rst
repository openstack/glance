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

This has not been doable since Ussuri as we only support Python 3.

In theory the same applies as mod_wsgi but even without chunked encoding the
code is still broken under uwsgi.

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

  uwsgi protocol
    The native protocol used by the uWSGI server. (The acronym is written in
    all lowercase on purpose.)

    https://uwsgi-docs.readthedocs.io/en/latest/Protocol.html

  uWSGI project
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
