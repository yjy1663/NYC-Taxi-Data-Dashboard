#!/usr/bin/env python

# JSON to INI

import argparse
import sys
import json

addrs = {}

def find_key(data, keywords):
    if isinstance(data, dict):
        for key, value in data.items():
            if key in keywords: addrs[key] = value
            if isinstance(value, dict):
                find_key(value, keywords)
            elif isinstance(value, list) and value:
                find_key(value[0], keywords)

parser = argparse.ArgumentParser(
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)

parser.add_argument("-i", "--input", dest='input', type=str,
    default='-', help="input file")

parser.add_argument("-o", "--output", dest='output', type=str,
    default='-', help="output file")

parser.add_argument("-k", "--keywords", dest='keywords', type=str,
    default='', help="comma separated keywords for section")

args = parser.parse_args()

keywords = args.keywords.split(',')

data = None
if args.input == '-':
    data = json.load(sys.stdin)
else:
    with open(args.input, 'r') as f:
        data = json.load(f)

find_key(data, keywords)

out = sys.stdout if args.output == '-' else open(args.output, 'w')

newline = ''
for key, value in addrs.items():
    out.write("%s[%s]\n" % (newline, key))
    newline = '\n'
    if isinstance(value, dict):
        if 'value' in value:
            if isinstance(value['value'], list):
                for v in value['value']:
                    out.write('%s\n' % v)
            elif isinstance(value['value'], str):
                    out.write('%s\n' % value['value'])

out.flush()
out.close()
