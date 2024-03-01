#!/usr/bin/env python

# Copyright 2018 RedHat Inc.
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

import argparse
import collections
import datetime
import functools
import os
import sys
import time
import uuid

from oslo_utils import encodeutils
import prettytable

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


def validate_input(func):
    """Decorator to enforce validation on input"""
    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        if len(args[0].command) > 2:
            print("Please specify the ID of the image you wish for command "
                  "'%s' from the cache as the first and only "
                  "argument." % args[0].command[0])
            return FAILURE
        if len(args[0].command) == 2:
            image_id = args[0].command[1]
            try:
                image_id = uuid.UUID(image_id)
            except ValueError:
                print("Image ID '%s' is not a valid UUID." % image_id)
                return FAILURE

        return func(args[0], **kwargs)
    return wrapped


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
def list_cached(args):
    """%(prog)s list-cached [options]

    List all images currently cached.
    """
    client = get_client(args)
    images = client.get_cached_images()
    if not images:
        print("No cached images.")
        return SUCCESS

    print("Found %d cached images..." % len(images))

    pretty_table = prettytable.PrettyTable(("ID",
                                            "Last Accessed (UTC)",
                                            "Last Modified (UTC)",
                                            "Size",
                                            "Hits"))
    pretty_table.align['Size'] = "r"
    pretty_table.align['Hits'] = "r"

    for image in images:
        last_accessed = image['last_accessed']
        if last_accessed == 0:
            last_accessed = "N/A"
        else:
            last_accessed = datetime.datetime.utcfromtimestamp(
                last_accessed).isoformat()

        pretty_table.add_row((
            image['image_id'],
            last_accessed,
            datetime.datetime.utcfromtimestamp(
                image['last_modified']).isoformat(),
            image['size'],
            image['hits']))

    print(pretty_table.get_string())
    return SUCCESS


@catch_error('show queued images')
def list_queued(args):
    """%(prog)s list-queued [options]

    List all images currently queued for caching.
    """
    client = get_client(args)
    images = client.get_queued_images()
    if not images:
        print("No queued images.")
        return SUCCESS

    print("Found %d queued images..." % len(images))

    pretty_table = prettytable.PrettyTable(("ID",))

    for image in images:
        pretty_table.add_row((image,))

    print(pretty_table.get_string())


@catch_error('queue the specified image for caching')
@validate_input
def queue_image(args):
    """%(prog)s queue-image <IMAGE_ID> [options]

    Queues an image for caching.
    """
    image_id = args.command[1]
    if (not args.force and
        not user_confirm("Queue image %(image_id)s for caching?" %
                         {'image_id': image_id}, default=False)):
        return SUCCESS

    client = get_client(args)
    client.queue_image_for_caching(image_id)

    if args.verbose:
        print("Queued image %(image_id)s for caching" %
              {'image_id': image_id})

    return SUCCESS


@catch_error('delete the specified cached image')
@validate_input
def delete_cached_image(args):
    """%(prog)s delete-cached-image <IMAGE_ID> [options]

    Deletes an image from the cache.
    """
    image_id = args.command[1]
    if (not args.force and
        not user_confirm("Delete cached image %(image_id)s?" %
                         {'image_id': image_id}, default=False)):
        return SUCCESS

    client = get_client(args)
    client.delete_cached_image(image_id)

    if args.verbose:
        print("Deleted cached image %(image_id)s" % {'image_id': image_id})

    return SUCCESS


@catch_error('Delete all cached images')
def delete_all_cached_images(args):
    """%(prog)s delete-all-cached-images [options]

    Remove all images from the cache.
    """
    if (not args.force and
            not user_confirm("Delete all cached images?", default=False)):
        return SUCCESS

    client = get_client(args)
    num_deleted = client.delete_all_cached_images()

    if args.verbose:
        print("Deleted %(num_deleted)s cached images" %
              {'num_deleted': num_deleted})

    return SUCCESS


@catch_error('delete the specified queued image')
@validate_input
def delete_queued_image(args):
    """%(prog)s delete-queued-image <IMAGE_ID> [options]

    Deletes an image from the cache.
    """
    image_id = args.command[1]
    if (not args.force and
        not user_confirm("Delete queued image %(image_id)s?" %
                         {'image_id': image_id}, default=False)):
        return SUCCESS

    client = get_client(args)
    client.delete_queued_image(image_id)

    if args.verbose:
        print("Deleted queued image %(image_id)s" % {'image_id': image_id})

    return SUCCESS


@catch_error('Delete all queued images')
def delete_all_queued_images(args):
    """%(prog)s delete-all-queued-images [options]

    Remove all images from the cache queue.
    """
    if (not args.force and
            not user_confirm("Delete all queued images?", default=False)):
        return SUCCESS

    client = get_client(args)
    num_deleted = client.delete_all_queued_images()

    if args.verbose:
        print("Deleted %(num_deleted)s queued images" %
              {'num_deleted': num_deleted})

    return SUCCESS


def get_client(options):
    """Return a new client object to a Glance server.

    specified by the --host and --port options
    supplied to the CLI
    """
    # Generate auth_url based on identity_api_version
    identity_version = env('OS_IDENTITY_API_VERSION', default='3')
    auth_url = options.os_auth_url
    if identity_version == '3' and "/v3" not in auth_url:
        auth_url = auth_url + "/v3"
    elif identity_version == '2' and "/v2" not in auth_url:
        auth_url = auth_url + "/v2.0"

    user_domain_id = options.os_user_domain_id
    if not user_domain_id:
        user_domain_id = options.os_domain_id
    project_domain_id = options.os_project_domain_id
    if not user_domain_id:
        project_domain_id = options.os_domain_id

    return glance.image_cache.client.get_client(
        host=options.host,
        port=options.port,
        username=options.os_username,
        password=options.os_password,
        project=options.os_project_name,
        user_domain_id=user_domain_id,
        project_domain_id=project_domain_id,
        auth_url=auth_url,
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
        value = os.environ.get(v)
        if value:
            return value
    return kwargs.get('default', '')


def print_help(args):
    """
    Print help specific to a command
    """
    command = lookup_command(args.command[1])
    print(command.__doc__ % {'prog': os.path.basename(sys.argv[0])})


def parse_args(parser):
    """Set up the CLI and config-file options that may be
    parsed and program commands.

    :param parser: The option parser
    """
    parser.add_argument('command', default='help', nargs='+',
                        help='The command to execute')
    parser.add_argument('-v', '--verbose', default=False, action="store_true",
                        help="Print more verbose output.")
    parser.add_argument('-d', '--debug', default=False, action="store_true",
                        help="Print debugging output.")
    parser.add_argument('-H', '--host', metavar="ADDRESS", default="0.0.0.0",
                        help="Address of Glance API host.")
    parser.add_argument('-p', '--port', dest="port", metavar="PORT",
                        type=int, default=9292,
                        help="Port the Glance API host listens on.")
    parser.add_argument('-k', '--insecure', dest="insecure",
                        default=False, action="store_true",
                        help='Explicitly allow glance to perform "insecure" '
                             "SSL (https) requests. The server's certificate "
                             "will not be verified against any certificate "
                             "authorities. This option should be used with "
                             "caution.")
    parser.add_argument('-f', '--force', dest="force",
                        default=False, action="store_true",
                        help="Prevent select actions from requesting "
                             "user confirmation.")

    parser.add_argument('--os-auth-token',
                        dest='os_auth_token',
                        default=env('OS_AUTH_TOKEN'),
                        help='Defaults to env[OS_AUTH_TOKEN].')
    parser.add_argument('-A', '--os_auth_token', '--auth_token',
                        dest='os_auth_token',
                        help=argparse.SUPPRESS)

    parser.add_argument('--os-username',
                        dest='os_username',
                        default=env('OS_USERNAME'),
                        help='Defaults to env[OS_USERNAME].')
    parser.add_argument('-I', '--os_username',
                        dest='os_username',
                        help=argparse.SUPPRESS)

    parser.add_argument('--os-password',
                        dest='os_password',
                        default=env('OS_PASSWORD'),
                        help='Defaults to env[OS_PASSWORD].')
    parser.add_argument('-K', '--os_password',
                        dest='os_password',
                        help=argparse.SUPPRESS)

    parser.add_argument('--os-region-name',
                        dest='os_region_name',
                        default=env('OS_REGION_NAME'),
                        help='Defaults to env[OS_REGION_NAME].')
    parser.add_argument('-R', '--os_region_name',
                        dest='os_region_name',
                        help=argparse.SUPPRESS)

    parser.add_argument('--os-project-id',
                        dest='os_project_id',
                        default=env('OS_PROJECT_ID'),
                        help='Defaults to env[OS_PROJECT_ID].')
    parser.add_argument('--os_project_id',
                        dest='os_project_id',
                        help=argparse.SUPPRESS)

    parser.add_argument('--os-project-name',
                        dest='os_project_name',
                        default=env('OS_PROJECT_NAME'),
                        help='Defaults to env[OS_PROJECT_NAME].')
    parser.add_argument('-T', '--os_project_name',
                        dest='os_project_name',
                        help=argparse.SUPPRESS)

    # arguments related user, project domain
    parser.add_argument('--os-user-domain-id',
                        dest='os_user_domain_id',
                        default=env('OS_USER_DOMAIN_ID'),
                        help='Defaults to env[OS_USER_DOMAIN_ID].')
    parser.add_argument('--os-project-domain-id',
                        dest='os_project_domain_id',
                        default=env('OS_PROJECT_DOMAIN_ID'),
                        help='Defaults to env[OS_PROJECT_DOMAIN_ID].')
    parser.add_argument('--os-domain-id',
                        dest='os_domain_id',
                        default=env('OS_DOMAIN_ID', default='default'),
                        help='Defaults to env[OS_DOMAIN_ID].')

    parser.add_argument('--os-auth-url',
                        default=env('OS_AUTH_URL'),
                        help='Defaults to env[OS_AUTH_URL].')
    parser.add_argument('-N', '--os_auth_url',
                        dest='os_auth_url',
                        help=argparse.SUPPRESS)

    parser.add_argument('-S', '--os_auth_strategy', dest="os_auth_strategy",
                        metavar="STRATEGY",
                        help="Authentication strategy (keystone or noauth).")

    version_string = version.cached_version_string()
    parser.add_argument('--version', action='version',
                        version=version_string)

    return parser.parse_args()


CACHE_COMMANDS = collections.OrderedDict()
CACHE_COMMANDS['help'] = (
    print_help, 'Output help for one of the commands below')
CACHE_COMMANDS['list-cached'] = (
    list_cached, 'List all images currently cached')
CACHE_COMMANDS['list-queued'] = (
    list_queued, 'List all images currently queued for caching')
CACHE_COMMANDS['queue-image'] = (
    queue_image, 'Queue an image for caching')
CACHE_COMMANDS['delete-cached-image'] = (
    delete_cached_image, 'Purges an image from the cache')
CACHE_COMMANDS['delete-all-cached-images'] = (
    delete_all_cached_images, 'Removes all images from the cache')
CACHE_COMMANDS['delete-queued-image'] = (
    delete_queued_image, 'Deletes an image from the cache queue')
CACHE_COMMANDS['delete-all-queued-images'] = (
    delete_all_queued_images, 'Deletes all images from the cache queue')


def _format_command_help():
    """Formats the help string for subcommands."""
    help_msg = "Commands:\n\n"

    for command, info in CACHE_COMMANDS.items():
        if command == 'help':
            command = 'help <command>'
        help_msg += "    %-28s%s\n\n" % (command, info[1])

    return help_msg


def lookup_command(command_name):
    try:
        command = CACHE_COMMANDS[command_name]
        return command[0]
    except KeyError:
        print('\nError: "%s" is not a valid command.\n' % command_name)
        print(_format_command_help())
        sys.exit("Unknown command: %(cmd_name)s" % {'cmd_name': command_name})


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
    print('In the Caracal development cycle, the glance-cache-manage command '
          'has been deprecated in favor of the new Cache API. It is scheduled '
          'to be removed in the Dalmatian development cycle.', file=sys.stderr)
    parser = argparse.ArgumentParser(
        description=_format_command_help(),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    args = parse_args(parser)

    if args.command[0] == 'help' and len(args.command) == 1:
        parser.print_help()
        return

    # Look up the command to run
    command = lookup_command(args.command[0])

    try:
        start_time = time.time()
        result = command(args)
        end_time = time.time()
        if args.verbose:
            print("Completed in %-0.4f sec." % (end_time - start_time))
        sys.exit(result)
    except (RuntimeError, NotImplementedError) as e:
        sys.exit("ERROR: %s" % e)


if __name__ == '__main__':
    main()
