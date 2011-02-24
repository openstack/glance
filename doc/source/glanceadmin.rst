..
      Copyright 2011 OpenStack, LLC
      All Rights Reserved.

      Licensed under the Apache License, Version 2.0 (the "License"); you may
      not use this file except in compliance with the License. You may obtain
      a copy of the License at

          http://www.apache.org/licenses/LICENSE-2.0

      Unless required by applicable law or agreed to in writing, software
      distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
      WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
      License for the specific language governing permissions and limitations
      under the License.

Using the Glance Admin Tool
===========================

Glance ships with a command-line tool for administering Glance called
``glance-admin``. It has a fairly simple but powerful interface of the
form::

  Usage: glance-admin <command> [options] [args]

Where ``<command>`` is one of the following:

* help

  Show detailed help information about a specific command

* add

  Adds an image to Glance

* update

  Updates an image's stored metadata in Glance

* delete

  Deletes an image and its metadata from Glance

* index

  Lists brief information about *public* images that Glance knows about

* details

  Lists detailed information about *public* images that Glance knows about

* show

  Lists detailed information about a specific image

* clear

  Destroys *all* images and their associated metadata

This document describes how to use the ``glance-admin`` tool for each of
the above commands.

The ``help`` command
--------------------

Issuing the ``help`` command with a ``<COMMAND>`` argument shows detailed help
about a specific command. Running ``glance-admin`` without any arguments shows
a brief help message, like so::

  $> glance-admin
  Usage: glance-admin <command> [options] [args]

  Commands:

      help <command>  Output help for one of the commands below

      add             Adds a new image to Glance

      update          Updates an image's metadata in Glance

      delete          Deletes an image from Glance

      index           Return brief information about images in Glance

      details         Return detailed information about images in
                      Glance

      show            Show detailed information about an image in
                      Glance

      clear           Removes all images and metadata from Glance

  Options:
    --version             show program's version number and exit
    -h, --help            show this help message and exit
    -v, --verbose         Print more verbose output
    -H ADDRESS, --host=ADDRESS
                          Address of Glance API host. Default: 0.0.0.0
    -p PORT, --port=PORT  Port the Glance API host listens on. Default: 9292
    --dry-run             Don't actually execute the command, just print output
                          showing what WOULD happen.

With a ``<COMMAND>`` argument, more information on the command is shown,
like so::

  $> glance-admin help update

  glance-admin update [options] <ID> <field1=value1 field2=value2 ...>

  Updates an image's metadata in Glance. Specify metadata fields as arguments.

  All field/value pairs are converted into a mapping that is passed
  to Glance that represents the metadata for an image.

  Field names that can be specified:

  name                A name for the image.
  is_public           If specified, interpreted as a boolean value
                      and sets or unsets the image's availability to the public.
  disk_format         Format of the disk image
  container_format    Format of the container

  All other field names are considered to be custom properties so be careful
  to spell field names correctly. :)

The ``add`` command
-------------------

The ``add`` command is used to do both of the following:

* Store virtual machine image data and metadata about that image in Glance

* Let Glance know about an existing virtual machine image that may be stored
  somewhere else

We cover both use cases below.

Store virtual machine image data and metadata
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When adding an actual virtual machine image to Glance, you use the ``add``
command. You will pass metadata about the VM image on the command line, and
you will use a standard shell redirect to stream the image data file to
``glance-admin``.

Let's walk through a simple example. Suppose we have an image stored on our
local filesystem that we wish to "upload" to Glance. This image is stored
on our local filesystem in ``/tmp/images/myimage.tar.gz``.

We'd also like to tell Glance that this image should be called "My Image", and
that the image should be public -- anyone should be able to fetch it.

Here is how we'd upload this image to Glance::

  $> glance-admin add name="My Image" is_public=true < /tmp/images/myimage.tar.gz

If Glance was able to successfully upload and store your VM image data and
metadata attributes, you would see something like this::

  $> glance-admin add name="My Image" is_public=true < /tmp/images/myimage.tar.gz
  Added new image with ID: 2

You can use the ``--verbose`` (or ``-v``) command-line option to print some more
information about the metadata that was saved with the image::

  $> glance-admin --verbose add name="My Image" is_public=true < /tmp/images/myimage.tar.gz
  Added new image with ID: 4
  Returned the following metadata for the new image:
                 container_format => ovf
                       created_at => 2011-02-22T19:20:53.298556
                          deleted => False
                       deleted_at => None
                      disk_format => raw
                               id => 4
                        is_public => True
                         location => file:///tmp/images/4
                             name => My Image
                       properties => {}
                             size => 58520278
                           status => active
                       updated_at => None
  Completed in 0.6141 sec.

If you are unsure about what will be added, you can use the ``--dry-run``
command-line option, which will simply show you what *would* have happened::

  $> glance-admin --dry-run add name="Foo" distro="Ubuntu" is_publi=True < /tmp/images/myimage.tar.gz
  Dry run. We would have done the following:
  Add new image with metadata:
                 container_format => ovf
                      disk_format => raw
                        is_public => False
                             name => Foo
                       properties => {'is_publi': 'True', 'distro': 'Ubuntu'}

This is useful for detecting problems and for seeing what the default field
values supplied by ``glance-admin`` are.  For instance, there was a typo in
the command above (the ``is_public`` field was incorrectly spelled ``is_publi``
which resulted in the image having an ``is_publi`` custom property added to
the image and the *real* ``is_public`` field value being `False` (the default)
and not `True`...

Register a virtual machine image in another location
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Sometimes, you already have stored the virtual machine image in some non-Glance
location -- perhaps even a location you have no write access to -- and you want
to tell Glance where this virtual machine image is located and some metadata
about it. The ``add`` command can do this for you.

When registering an image in this way, the only difference is that you do not
use a shell redirect to stream a virtual machine image file into Glance, but
instead, you tell Glance where to find the existing virtual machine image by
setting the ``location`` field. Below is an example of doing this.

Let's assume that there is a virtual machine image located at the URL
``http://example.com/images/myimage.tar.gz``. We can register this image with
Glance using the following::

  $> glance-admin --verbose add name="Some web image" location="http://example.com/images/myimage.tar.gz"
  Added new image with ID: 1
  Returned the following metadata for the new image:
                 container_format => ovf
                       created_at => 2011-02-23T00:42:04.688890
                          deleted => False
                       deleted_at => None
                      disk_format => vhd
                               id => 1
                        is_public => True
                         location => http://example.com/images/myimage.tar.gz
                             name => Some web image
                       properties => {}
                             size => 0
                           status => active
                       updated_at => None
  Completed in 0.0356 sec.


The ``update`` command
----------------------

After uploading/adding a virtual machine image to Glance, it is not possible to
modify the actual virtual machine image -- images are read-only after all --
however, it *is* possible to update any metadata about the image after you add
it to Glance.

The ``update`` command allows you to update the metadata fields of a stored
image. You use this command like so::

  glance-admin update <ID> [field1=value1 field2=value2 ...]

Let's say we have an image with identifier 4 that we wish to change the is_public
attribute of the image from True to False. The following would accomplish this::



The ``delete`` command
----------------------

The ``index`` command
---------------------

The ``details`` command
-----------------------

The ``show`` command
--------------------

The ``clear`` command
---------------------

The ``clear`` command is an administrative command that deletes **ALL** images
and all image metadata. Passing the ``--verbose`` command will print brief
information about all the images that were deleted, as shown below::

  $> glance-admin --verbose clear
  Deleting image 1 "Some web image" ... done
  Deleting image 2 "Some other web image" ... done
  Completed in 0.0328 sec.
