#!/usr/bin/python
"""
Upload an image into Glance

Usage:

Raw:

    glance_upload.py <filename> <name>

Kernel-outside:

    glance_upload.py --type=kernel <filename> <name>
    glance_upload.py --type=ramdisk <filename> <name>
    glance_upload.py --type=machine --kernel=KERNEL_ID --ramdisk=RAMDISK_ID \
                     <filename> <name>

"""
import argparse
import pprint
import sys

from glance.client import Client


def die(msg):
    print >>sys.stderr, msg
    sys.exit(1)


def parse_args():
    parser = argparse.ArgumentParser(description='Upload an image into Glance')
    parser.add_argument('filename', help='file to upload into Glance')
    parser.add_argument('name', help='name of image')
    parser.add_argument('--host', metavar='HOST', default='127.0.0.1',
                        help='Location of Glance Server (default: 127.0.0.1)')
    parser.add_argument('--type', metavar='TYPE', default='raw',
                        help='Type of Image [kernel, ramdisk, machine, raw] '
                             '(default: raw)')
    parser.add_argument('--kernel', metavar='KERNEL',
                        help='ID of kernel associated with this machine image')
    parser.add_argument('--ramdisk', metavar='RAMDISK',
                        help='ID of ramdisk associated with this machine image')
    args = parser.parse_args()
    return args


def main():
    args = parse_args()
    meta = {'name': args.name, 'type': args.type, 'is_public': True}

    if args.type == 'machine':
        if args.kernel and args.ramdisk:
            meta['properties'] = {'kernel_id': args.kernel,
                                  'ramdisk_id': args.ramdisk}
        else:
            die("kernel and ramdisk required for machine image")

    client = Client(args.host, 9292)
    with open(args.filename) as f:
        new_meta = client.add_image(meta, f)

    print 'Stored image. Got identifier: %s' % pprint.pformat(new_meta)


if __name__ == "__main__":
    main()
