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
import json
import logging
import subprocess
import sys

from oslo_utils.imageutils import format_inspector
from oslo_utils import units


def get_size_from_qemu_img(filename):
    output = subprocess.check_output(
        ['qemu-img', 'info', '--output=json', filename], text=True)
    return json.loads(output)['virtual-size']


def main():
    formats = sorted(format_inspector.ALL_FORMATS)

    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--debug', action='store_true')
    parser.add_argument('-f', '--format', default='raw',
                        help='Format (%s)' % ','.join(formats))
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

    if args.input:
        input_stream = open(args.input, 'rb')
    else:
        input_stream = sys.stdin.buffer

    stream = format_inspector.InspectWrapper(
        input_stream, tracing=args.debug)
    count = 0
    found_size = False
    try:
        while chunk := stream.read(args.block_size):
            count += len(chunk)
            if args.format == 'raw' or found_size:
                continue

            try:
                detected_format = stream.format
            except format_inspector.ImageFormatError:
                continue

            if (detected_format is not None
                    and str(detected_format) == args.format
                    and detected_format.virtual_size):
                # Print the point at which we've seen enough of the file to
                # know what the virtual size is. This is almost always less
                # than the raw_size
                print('Determined virtual size at byte %i' % count)
                found_size = True
    finally:
        stream.close()

    try:
        fmt = stream.format
    except format_inspector.ImageFormatError as error:
        print('*** Format inspector could not determine format: %s' % error)
        return 1

    if fmt is not None and str(fmt) == args.format:
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
        size = get_size_from_qemu_img(args.input)
        if size != fmt.virtual_size:
            print('*** QEMU disagrees with our size of %i: %i' % (
                fmt.virtual_size, size))
        else:
            print('Confirmed size with qemu-img')

    try:
        fmt.safety_check()
        safety_result = 'passed'
    except (
            format_inspector.ImageFormatError,
            format_inspector.SafetyCheckFailed) as error:
        safety_result = 'FAILED: %s' % error
    print('Image safety check: %s' % safety_result)
    if args.input:
        detected_fmt = format_inspector.detect_file_format(args.input)
        print('Detected inspector for image as: %s' % (
            detected_fmt.__class__.__name__))


if __name__ == '__main__':
    sys.exit(main())
