#!/usr/bin/env python

# Copyright 2011 OpenStack Foundation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
A simple cache management utility for Glance.
"""
from __future__ import print_function

import functools
import optparse
import os
import sys
import time

from oslo_utils import encodeutils
from oslo_utils import timeutils

from glance.common import utils
from six.moves import input

# If ../glance/__init__.py exists, add ../ to Python search path, so that
# it will override what happens to be installed in /usr/(local/)lib/python...
possible_topdir = os.path.normpath(os.path.join(os.path.abspath(sys.argv[0]),
                                   os.pardir,
                                   os.pardir))
if os.path.exists(os.path.join(possible_topdir, 'glance', '__init__.py')):
    sys.path.insert(0, possible_topdir)

from glance.common import exception
import glance.image_cache.client
from glance.version import version_info as version


SUCCESS = 0
FAILURE = 1


def catch_error(action):
    """Decorator to provide sensible default error handling for actions."""
    def wrap(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                ret = func(*args, **kwargs)
                return SUCCESS if ret is None else ret
            except exception.NotFound:
                options = args[0]
                print("Cache management middleware not enabled on host %s" %
                      options.host)
                return FAILURE
            except exception.Forbidden:
                print("Not authorized to make this request.")
                return FAILURE
            except Exception as e:
                options = args[0]
                if options.debug:
                    raise
                print("Failed to %s. Got error:" % action)
                pieces = encodeutils.exception_to_unicode(e).split('\n')
                for piece in pieces:
                    print(piece)
                return FAILURE

        return wrapper
    return wrap


@catch_error('show cached images')
def list_cached(options, args):
    """%(prog)s list-cached [options]

List all images currently cached.
    """
    client = get_client(options)
    images = client.get_cached_images()
    if not images:
        print("No cached images.")
        return SUCCESS

    print("Found %d cached images..." % len(images))

    pretty_table = utils.PrettyTable()
    pretty_table.add_column(36, label="ID")
    pretty_table.add_column(19, label="Last Accessed (UTC)")
    pretty_table.add_column(19, label="Last Modified (UTC)")
    # 1 TB takes 13 characters to display: len(str(2**40)) == 13
    pretty_table.add_column(14, label="Size", just="r")
    pretty_table.add_column(10, label="Hits", just="r")

    print(pretty_table.make_header())

    for image in images:
        last_modified = image['last_modified']
        last_modified = timeutils.iso8601_from_timestamp(last_modified)

        last_accessed = image['last_accessed']
        if last_accessed == 0:
            last_accessed = "N/A"
        else:
            last_accessed = timeutils.iso8601_from_timestamp(last_accessed)

        print(pretty_table.make_row(
            image['image_id'],
            last_accessed,
            last_modified,
            image['size'],
            image['hits']))


@catch_error('show queued images')
def list_queued(options, args):
    """%(prog)s list-queued [options]

List all images currently queued for caching.
    """
    client = get_client(options)
    images = client.get_queued_images()
    if not images:
        print("No queued images.")
        return SUCCESS

    print("Found %d queued images..." % len(images))

    pretty_table = utils.PrettyTable()
    pretty_table.add_column(36, label="ID")

    print(pretty_table.make_header())

    for image in images:
        print(pretty_table.make_row(image))


@catch_error('queue the specified image for caching')
def queue_image(options, args):
    """%(prog)s queue-image <IMAGE_ID> [options]

Queues an image for caching
"""
    if len(args) == 1:
        image_id = args.pop()
    else:
        print("Please specify one and only ID of the image you wish to ")
        print("queue from the cache as the first argument")
        return FAILURE

    if (not options.force and
        not user_confirm("Queue image %(image_id)s for caching?" %
                         {'image_id': image_id}, default=False)):
        return SUCCESS

    client = get_client(options)
    client.queue_image_for_caching(image_id)

    if options.verbose:
        print("Queued image %(image_id)s for caching" %
              {'image_id': image_id})

    return SUCCESS


@catch_error('delete the specified cached image')
def delete_cached_image(options, args):
    """
%(prog)s delete-cached-image <IMAGE_ID> [options]

Deletes an image from the cache
    """
    if len(args) == 1:
        image_id = args.pop()
    else:
        print("Please specify one and only ID of the image you wish to ")
        print("delete from the cache as the first argument")
        return FAILURE

    if (not options.force and
        not user_confirm("Delete cached image %(image_id)s?" %
                         {'image_id': image_id}, default=False)):
        return SUCCESS

    client = get_client(options)
    client.delete_cached_image(image_id)

    if options.verbose:
        print("Deleted cached image %(image_id)s" % {'image_id': image_id})

    return SUCCESS


@catch_error('Delete all cached images')
def delete_all_cached_images(options, args):
    """%(prog)s delete-all-cached-images [options]

Remove all images from the cache.
    """
    if (not options.force and
            not user_confirm("Delete all cached images?", default=False)):
        return SUCCESS

    client = get_client(options)
    num_deleted = client.delete_all_cached_images()

    if options.verbose:
        print("Deleted %(num_deleted)s cached images" %
              {'num_deleted': num_deleted})

    return SUCCESS


@catch_error('delete the specified queued image')
def delete_queued_image(options, args):
    """
%(prog)s delete-queued-image <IMAGE_ID> [options]

Deletes an image from the cache
    """
    if len(args) == 1:
        image_id = args.pop()
    else:
        print("Please specify one and only ID of the image you wish to ")
        print("delete from the cache as the first argument")
        return FAILURE

    if (not options.force and
        not user_confirm("Delete queued image %(image_id)s?" %
                         {'image_id': image_id}, default=False)):
        return SUCCESS

    client = get_client(options)
    client.delete_queued_image(image_id)

    if options.verbose:
        print("Deleted queued image %(image_id)s" % {'image_id': image_id})

    return SUCCESS


@catch_error('Delete all queued images')
def delete_all_queued_images(options, args):
    """%(prog)s delete-all-queued-images [options]

Remove all images from the cache queue.
    """
    if (not options.force and
            not user_confirm("Delete all queued images?", default=False)):
        return SUCCESS

    client = get_client(options)
    num_deleted = client.delete_all_queued_images()

    if options.verbose:
        print("Deleted %(num_deleted)s queued images" %
              {'num_deleted': num_deleted})

    return SUCCESS


def get_client(options):
    """Return a new client object to a Glance server.

    specified by the --host and --port options
    supplied to the CLI
    """
    return glance.image_cache.client.get_client(
        host=options.host,
        port=options.port,
        username=options.os_username,
        password=options.os_password,
        tenant=options.os_tenant_name,
        auth_url=options.os_auth_url,
        auth_strategy=options.os_auth_strategy,
        auth_token=options.os_auth_token,
        region=options.os_region_name,
        insecure=options.insecure)


def env(*vars, **kwargs):
    """Search for the first defined of possibly many env vars.

    Returns the first environment variable defined in vars, or
    returns the default defined in kwargs.
    """
    for v in vars:
        value = os.environ.get(v, None)
        if value:
            return value
    return kwargs.get('default', '')


def create_options(parser):
    """Set up the CLI and config-file options that may be
    parsed and program commands.

    :param parser: The option parser
    """
    parser.add_option('-v', '--verbose', default=False, action="store_true",
                      help="Print more verbose output.")
    parser.add_option('-d', '--debug', default=False, action="store_true",
                      help="Print debugging output.")
    parser.add_option('-H', '--host', metavar="ADDRESS", default="0.0.0.0",
                      help="Address of Glance API host. "
                           "Default: %default.")
    parser.add_option('-p', '--port', dest="port", metavar="PORT",
                      type=int, default=9292,
                      help="Port the Glance API host listens on. "
                           "Default: %default.")
    parser.add_option('-k', '--insecure', dest="insecure",
                      default=False, action="store_true",
                      help="Explicitly allow glance to perform \"insecure\" "
                      "SSL (https) requests. The server's certificate will "
                      "not be verified against any certificate authorities. "
                      "This option should be used with caution.")
    parser.add_option('-f', '--force', dest="force", metavar="FORCE",
                      default=False, action="store_true",
                      help="Prevent select actions from requesting "
                           "user confirmation.")

    parser.add_option('--os-auth-token',
                      dest='os_auth_token',
                      default=env('OS_AUTH_TOKEN'),
                      help='Defaults to env[OS_AUTH_TOKEN].')
    parser.add_option('-A', '--os_auth_token', '--auth_token',
                      dest='os_auth_token',
                      help=optparse.SUPPRESS_HELP)

    parser.add_option('--os-username',
                      dest='os_username',
                      default=env('OS_USERNAME'),
                      help='Defaults to env[OS_USERNAME].')
    parser.add_option('-I', '--os_username',
                      dest='os_username',
                      help=optparse.SUPPRESS_HELP)

    parser.add_option('--os-password',
                      dest='os_password',
                      default=env('OS_PASSWORD'),
                      help='Defaults to env[OS_PASSWORD].')
    parser.add_option('-K', '--os_password',
                      dest='os_password',
                      help=optparse.SUPPRESS_HELP)

    parser.add_option('--os-region-name',
                      dest='os_region_name',
                      default=env('OS_REGION_NAME'),
                      help='Defaults to env[OS_REGION_NAME].')
    parser.add_option('-R', '--os_region_name',
                      dest='os_region_name',
                      help=optparse.SUPPRESS_HELP)

    parser.add_option('--os-tenant-id',
                      dest='os_tenant_id',
                      default=env('OS_TENANT_ID'),
                      help='Defaults to env[OS_TENANT_ID].')
    parser.add_option('--os_tenant_id',
                      dest='os_tenant_id',
                      help=optparse.SUPPRESS_HELP)

    parser.add_option('--os-tenant-name',
                      dest='os_tenant_name',
                      default=env('OS_TENANT_NAME'),
                      help='Defaults to env[OS_TENANT_NAME].')
    parser.add_option('-T', '--os_tenant_name',
                      dest='os_tenant_name',
                      help=optparse.SUPPRESS_HELP)

    parser.add_option('--os-auth-url',
                      default=env('OS_AUTH_URL'),
                      help='Defaults to env[OS_AUTH_URL].')
    parser.add_option('-N', '--os_auth_url',
                      dest='os_auth_url',
                      help=optparse.SUPPRESS_HELP)

    parser.add_option('-S', '--os_auth_strategy', dest="os_auth_strategy",
                      metavar="STRATEGY",
                      help="Authentication strategy (keystone or noauth).")


def parse_options(parser, cli_args):
    """
    Returns the parsed CLI options, command to run and its arguments, merged
    with any same-named options found in a configuration file

    :param parser: The option parser
    """
    if not cli_args:
        cli_args.append('-h')  # Show options in usage output...

    (options, args) = parser.parse_args(cli_args)

    # HACK(sirp): Make the parser available to the print_help method
    # print_help is a command, so it only accepts (options, args); we could
    # one-off have it take (parser, options, args), however, for now, I think
    # this little hack will suffice
    options.__parser = parser

    if not args:
        parser.print_usage()
        sys.exit(0)

    command_name = args.pop(0)
    command = lookup_command(parser, command_name)

    return (options, command, args)


def print_help(options, args):
    """
    Print help specific to a command
    """
    if len(args) != 1:
        sys.exit("Please specify a command")

    parser = options.__parser
    command_name = args.pop()
    command = lookup_command(parser, command_name)

    print(command.__doc__ % {'prog': os.path.basename(sys.argv[0])})


def lookup_command(parser, command_name):
    BASE_COMMANDS = {'help': print_help}

    CACHE_COMMANDS = {
        'list-cached': list_cached,
        'list-queued': list_queued,
        'queue-image': queue_image,
        'delete-cached-image': delete_cached_image,
        'delete-all-cached-images': delete_all_cached_images,
        'delete-queued-image': delete_queued_image,
        'delete-all-queued-images': delete_all_queued_images,
    }

    commands = {}
    for command_set in (BASE_COMMANDS, CACHE_COMMANDS):
        commands.update(command_set)

    try:
        command = commands[command_name]
    except KeyError:
        parser.print_usage()
        sys.exit("Unknown command: %(cmd_name)s" % {'cmd_name': command_name})

    return command


def user_confirm(prompt, default=False):
    """Yes/No question dialog with user.

    :param prompt: question/statement to present to user (string)
    :param default: boolean value to return if empty string
                    is received as response to prompt

    """
    if default:
        prompt_default = "[Y/n]"
    else:
        prompt_default = "[y/N]"

    answer = input("%s %s " % (prompt, prompt_default))

    if answer == "":
        return default
    else:
        return answer.lower() in ("yes", "y")


def main():
    usage = """
%prog <command> [options] [args]

Commands:

    help <command> Output help for one of the commands below

    list-cached                 List all images currently cached

    list-queued                 List all images currently queued for caching

    queue-image                 Queue an image for caching

    delete-cached-image         Purges an image from the cache

    delete-all-cached-images    Removes all images from the cache

    delete-queued-image         Deletes an image from the cache queue

    delete-all-queued-images    Deletes all images from the cache queue
"""

    version_string = version.cached_version_string()
    oparser = optparse.OptionParser(version=version_string,
                                    usage=usage.strip())
    create_options(oparser)
    (options, command, args) = parse_options(oparser, sys.argv[1:])

    try:
        start_time = time.time()
        result = command(options, args)
        end_time = time.time()
        if options.verbose:
            print("Completed in %-0.4f sec." % (end_time - start_time))
        sys.exit(result)
    except (RuntimeError, NotImplementedError) as e:
        print("ERROR: ", e)

if __name__ == '__main__':
    main()
