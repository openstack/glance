#!/usr/bin/env python3
# Copyright 2020 Red Hat, Inc
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

"""This is a helper tool to test Glance's stream-based format inspection."""

# Example usage:
#
# test_format_inspector.py -f qcow2 -v -i ~/cirros-0.5.1-x86_64-disk.img

import argparse
import logging
import sys

from oslo_utils import units

from glance.common import format_inspector
from glance.tests.unit.common import test_format_inspector


def main():
    formats = ['raw', 'qcow2', 'vhd', 'vhdx', 'vmdk', 'vdi']

    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--debug', action='store_true')
    parser.add_argument('-f', '--format', default='raw',
                        help='Format (%s)' % ','.join(sorted(formats)))
    parser.add_argument('-b', '--block-size', default=65536, type=int,
                        help='Block read size')
    parser.add_argument('--context-limit', default=(1 * 1024), type=int,
                        help='Maximum memory footprint (KiB)')
    parser.add_argument('-i', '--input', default=None,
                        help='Input file. Defaults to stdin')
    parser.add_argument('-v', '--verify', action='store_true',
                        help=('Verify our number with qemu-img '
                              '(requires --input)'))
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    fmt = format_inspector.get_inspector(args.format)(tracing=args.debug)

    if args.input:
        input_stream = open(args.input, 'rb')
    else:
        input_stream = sys.stdin.buffer

    stream = format_inspector.InfoWrapper(input_stream, fmt)
    count = 0
    found_size = False
    while True:
        chunk = stream.read(int(args.block_size))
        # This could stream to an output destination or stdin for testing
        # sys.stdout.write(chunk)
        if not chunk:
            break
        count += len(chunk)
        if args.format != 'raw' and not found_size and fmt.virtual_size != 0:
            # Print the point at which we've seen enough of the file to
            # know what the virtual size is. This is almost always less
            # than the raw_size
            print('Determined virtual size at byte %i' % count)
            found_size = True

    if fmt.format_match:
        print('Source was %s file, virtual size %i MiB (%i bytes)' % (
            fmt, fmt.virtual_size / units.Mi, fmt.virtual_size))
    else:
        print('*** Format inspector did not detect file as %s' % args.format)

    print('Raw size %i MiB (%i bytes)' % (fmt.actual_size / units.Mi,
                                          fmt.actual_size))
    print('Required contexts: %s' % str(fmt.context_info))
    mem_total = sum(fmt.context_info.values())
    print('Total memory footprint: %i bytes' % mem_total)

    # To make sure we're not storing the whole image, complain if the
    # format inspector stored more than context_limit data
    if mem_total > args.context_limit * 1024:
        print('*** ERROR: Memory footprint exceeded!')

    if args.verify and args.input:
        size = test_format_inspector.get_size_from_qemu_img(args.input)
        if size != fmt.virtual_size:
            print('*** QEMU disagrees with our size of %i: %i' % (
                fmt.virtual_size, size))
        else:
            print('Confirmed size with qemu-img')

    print('Image safety check: %s' % (
        fmt.safety_check() and 'passed' or 'FAILED'))
    if args.input:
        detected_fmt = format_inspector.detect_file_format(args.input)
        print('Detected inspector for image as: %s' % (
            detected_fmt.__class__.__name__))


if __name__ == '__main__':
    sys.exit(main())
