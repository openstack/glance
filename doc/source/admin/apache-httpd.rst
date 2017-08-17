=======================
Running Glance in HTTPD
=======================

Since the Pike release Glance has packaged a wsgi script entrypoint that
enables you to run it with a real web server like Apache HTTPD or nginx. To
deploy this there are several patterns. This doc shows two common ways of
deploying Glance with Apache HTTPD.

.. NOTE::

    We are experiencing some problems in the gate when the Pike release of
    Glance is configured to run in devstack following the guidelines
    recommended in this documentation. You can follow `Bug #1703856
    <https://bugs.launchpad.net/glance/+bug/1703856>`__ to learn more.


uwsgi
-----

This is the current recommended way to deploy Glance with a real web server.
In this deployment method we use uwsgi as a web server bound to a random local
port. Then we configure apache using mod_proxy to forward all incoming requests
on the specified endpoint to that local webserver. This has the advantage of
letting apache manage all inbound http connections, but letting uwsgi manage
running the python code. It also means when we make changes to Glance code
or configuration we don't need to restart all of apache (which may be running
other services too) and just need to restart the local uwsgi daemon.

The httpd/ directory contains sample files for configuring HTTPD to run Glance
under uwsgi in this configuration. To use the sample configs simply copy
`httpd/uwsgi-glance-api.conf` to the appropriate location for your Apache
server. On Debian/Ubuntu systems it is::

    /etc/apache2/sites-available/uwsgi-glance-api.conf

On Red Hat based systems it is::

    /etc/httpd/conf.d/uwsgi-glance-api.conf

Enable mod_proxy by running ``sudo a2enmod proxy``

Then on Ubuntu/Debian systems enable the site by creating a symlink from the
file in ``sites-available`` to ``sites-enabled``. (This is not required on Red
Hat based systems)::

    ln -s /etc/apache2/sites-available/uwsgi-glance-api.conf /etc/apache2/sites-enabled

Start or restart HTTPD to pick up the new configuration.

Now we need to configure and start the uwsgi service. Copy the
`httpd/glance-api-uwsgi.ini` file to `/etc/glance`. Update the file to match
your system configuration (for example, you'll want to set the number of
processes and threads).

Install uwsgi and start the glance-api server using uwsgi::

    sudo pip install uwsgi
    uwsgi --ini /etc/glance/glance-api-uwsgi.ini

.. NOTE::

    In the sample configs port 60999 is used, but this doesn't matter and is
    just a randomly selected number. This is not a contract on the port used
    for the local uwsgi daemon.

.. NOTE::

    In the sample apache config proxy-sendcl is set. This is to workaround
    glance not leveraging uwsgi's chunked_read() api in the Pike release.
    Using this option means apache buffers the input chunked data in the
    configured TEMPDIR (which defaults to /tmp) before giving the data to
    glance. This can also be quite slow and might require increasing timeouts.


mod_proxy_uwsgi
'''''''''''''''

.. WARNING::

    Running Glance under HTTPD in this configuration will only work on Python 2
    if you use ``Transfer-Encoding: chunked``. Also if running with Python 2
    apache will be buffering the chunked encoding before passing the request
    on to uwsgi. See bug: https://github.com/unbit/uwsgi/issues/1540

Instead of running uwsgi as a webserver listening on a local port and then
having Apache HTTP proxy all the incoming requests with mod_proxy. The
normally recommended way of deploying uwsgi with Apache HTTPD is to use
mod_proxy_uwsgi and set up a local socket file for uwsgi to listen on. Apache
will send the requests using the uwsgi protocol over this local socket
file. However, there are issues with doing this and using chunked-encoding.

You can work around these issues by configuring your apache proxy to buffer the
chunked data and send the full content length to uwsgi. You do this by adding::

    SetEnv proxy-sendcl 1

to the apache config file using mod_proxy_uwsgi. For more details on using
mod_proxy_uwsgi see the official docs:
http://uwsgi-docs.readthedocs.io/en/latest/Apache.html?highlight=mod_uwsgi_proxy#mod-proxy-uwsgi

mod_wsgi
--------

This deployment method is not recommended for using Glance. The mod_wsgi
protocol does not support ``Transfer-Encoding: chunked`` and therefore makes it
unsuitable for use with Glance. However, you could theoretically deploy Glance
using mod_wsgi but it will fail on any requests that use a chunked transfer
encoding.
