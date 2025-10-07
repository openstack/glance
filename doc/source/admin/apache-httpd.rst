=======================
Running Glance in HTTPD
=======================

Glance provides full support for running as a WSGI application under
various web servers including Apache HTTPD and nginx. This deployment
method is now fully supported and recommended for production
environments. This document describes the recommended deployment
patterns for running Glance with Apache HTTPD with uWSGI.

.. versionchanged:: 15.0.0

   Added the ``glance-wsgi-api`` WSGI script, which can be used with
   uWSGI using the ``[uwsgi] wsgi-file`` configuration option. This
   can be used for the basic API service, though not all functionality
   is currently supported and standalone (eventlet) mode is still
   recommended for production environments.

.. versionchanged:: 21.0.0 (Victoria)

   Glance now fully supports WSGI deployment including all functionality
   such as interoperable image import, chunked transfer encoding, and
   graceful shutdown. This deployment method is recommended for
   production environments.

.. versionchanged:: 30.0.0 (2025.1, Epoxy)

   Added the ``glance.wsgi.api`` module as a replacement for the
   ``glance-wsgi-api`` WSGI script. This can be used with uWSGI using
   the ``[uwsgi] module`` configuration option. The ``glance-wsgi-api``
   WSGI script is now deprecated for removal.

.. versionchanged:: 32.0.0 (2026.1, Gazpacho)

   The ``glance-wsgi-api`` WSGI script has been removed.

uWSGI Server HTTP Mode
----------------------

This is the most common deployment method for running Glance under
Apache HTTPD and is what is currently tested by the Glance project.

uWSGI provides excellent performance and full compatibility with
Glance's features including:

* Full support for chunked transfer encoding
* Interoperable image import functionality
* Graceful shutdown and reload capabilities
* Native threading support
* Production-ready stability

Configuration Example
~~~~~~~~~~~~~~~~~~~~~

Here's a sample uWSGI configuration for Glance API:

.. code-block:: ini

   [uwsgi]
   socket-timeout = 10
   http-auto-chunked = true
   http-chunked-input = true
   http-raw-body = true
   chmod-socket = 666
   lazy-apps = true
   add-header = Connection: close
   buffer-size = 65535
   thunder-lock = true
   plugins = python
   enable-threads = true
   exit-on-reload = true
   die-on-term = true
   master = true
   processes = 4
   http-socket = 127.0.0.1:60999
   module = glance.wsgi.api:application

Key Configuration Options
~~~~~~~~~~~~~~~~~~~~~~~~~

* ``http-auto-chunked = true`` - Enables automatic chunked transfer
  encoding support
* ``http-chunked-input = true`` - Supports chunked input for image
  uploads
* ``enable-threads = true`` - Enables native threading for better
  performance
* ``die-on-term = true`` - Enables graceful shutdown on SIGTERM
* ``exit-on-reload = true`` - Enables graceful reload on SIGHUP

Graceful Shutdown
~~~~~~~~~~~~~~~~~

Glance running under uWSGI supports graceful shutdown through:

* SIGTERM signal for graceful shutdown
* SIGHUP signal for configuration reload
* Automatic worker pool draining
* Proper cleanup of background tasks

.. _mod_proxy_uwsgi:

mod_proxy_uwsgi
'''''''''''''''

This deployment method uses Apache's mod_proxy_uwsgi module to proxy
requests to a uWSGI server.

Configuration Example
~~~~~~~~~~~~~~~~~~~~~

Apache VirtualHost configuration:

.. code-block:: apache

   <VirtualHost *:80>
       ServerName glance-api.example.com

       ProxyPreserveHost On
       ProxyPass / uwsgi://127.0.0.1:60999/
       ProxyPassReverse / uwsgi://127.0.0.1:60999/

       # Optional: Add headers for better logging
       ProxyAddHeaders On
   </VirtualHost>

Benefits
~~~~~~~~

* Apache handles SSL termination and load balancing
* uWSGI handles the Python application
* Full compatibility with all Glance features
* Production-ready and scalable

mod_wsgi
--------

This deployment method uses Apache's mod_wsgi module directly.

.. note::
   While mod_wsgi is supported, uWSGI is recommended for better
   performance and feature compatibility.

Configuration Example
~~~~~~~~~~~~~~~~~~~~~

Apache VirtualHost configuration:

.. code-block:: apache

   <VirtualHost *:80>
       ServerName glance-api.example.com

       WSGIDaemonProcess glance-api processes=4 threads=15
       WSGIProcessGroup glance-api
       WSGIScriptAlias / /usr/local/bin/glance-wsgi-api

       <Directory /usr/local/bin>
           WSGIApplicationGroup %{GLOBAL}
           Require all granted
       </Directory>
   </VirtualHost>

Performance Considerations
--------------------------

For production deployments, consider:

* **Process Management**: Use uWSGI's master process for better
  stability
* **Threading**: Enable native threading for I/O-bound operations
* **Memory**: Configure appropriate buffer sizes for large image
  transfers
* **Timeouts**: Set appropriate socket timeouts for long-running
  operations
* **Logging**: Configure proper logging for monitoring and debugging

Monitoring and Troubleshooting
------------------------------

* Monitor uWSGI worker processes and memory usage
* Check logs for any chunked transfer encoding issues
* Verify graceful shutdown behavior during deployments
* Test interoperable image import functionality
* Monitor response times for large image operations

.. _uwsgi_glossary:

Glossary
--------

.. glossary::

  uwsgi protocol
    The native protocol used by the uWSGI server. (The acronym is
    written in all lowercase on purpose.)

    https://uwsgi-docs.readthedocs.io/en/latest/Protocol.html

  uWSGI project
    A project that aims at developing a full stack for building
    hosting services.  It produces software, the uWSGI server, that is
    exposed in Python code as a module named ``uwsgi``.

    https://uwsgi-docs.readthedocs.io/en/latest/index.html

    https://pypi.org/project/uWSGI/

    https://github.com/unbit/uwsgi

  mod_wsgi
    An Apache 2 HTTP server module that supports the Python WSGI
    specification.

    https://modwsgi.readthedocs.io/en/develop/

  mod_proxy_uwsgi
    An Apache 2 HTTP Server module that provides a uwsgi gateway for
    mod_proxy. It communicates to the uWSGI server using the uwsgi
    protocol.

    http://httpd.apache.org/docs/trunk/mod/mod_proxy_uwsgi.html

  WSGI
    Web Server Gateway Interface, a Python standard published as
    :pep:`3333`.

    https://wsgi.readthedocs.io/en/latest/index.html
