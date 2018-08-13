#!/usr/bin/env python
# All rights reserved.

from __future__ import print_function

import argparse
import datetime
import logging
import os.path
import sys
import ConfigParser

import boto3

__all__ = ['RECORD_LENGTH', 'MIN_DATE', 'MAX_DATE', 'BASE_DATE', \
           'fatal', 'error', \
           'get_file_name', 'get_file_size', 'get_file_length', \
           'Options']

RECORD_LENGTH = 80
MIN_DATE = {
    'yellow': datetime.datetime(2009, 1, 1),
    'green' : datetime.datetime(2013, 8, 1)
}
MAX_DATE = {
    'yellow': datetime.datetime(2016, 6, 30),
    'green' : datetime.datetime(2016, 6, 30)
}
BASE_DATE = datetime.datetime(2009,1,1)

def fatal(message):
    sys.stderr.write('fatal: %s\n' % message)
    sys.stderr.flush()
    sys.exit(1)

def error(message):
    sys.stderr.write('error: %s\n' % message)
    sys.stderr.flush()

def get_file_name(color, year, month):
    return '%s-%s-%02d.csv' % (color, year, int(month))

def get_file_size(source, color, year, month):
    name = get_file_name(color, year, month)

    if source.startswith('file://'):
        directory = os.path.realpath(source[7:])
        if not os.path.isdir(directory):
            fatal("%s is not a directory." % directory)

        path = os.path.join(directory, name)
        if not os.path.exists(path):
            fatal("%s does not exist." % path)
        if not os.path.isfile(path):
            fatal("%s is not a regular file." % path)

        return os.path.getsize(path)

    elif source.startswith('s3://'):
        s3 = boto3.resource('s3')
        bucket = s3.Bucket(source[5:])

        try:
            s3.meta.client.head_bucket(Bucket=bucket.name)
        except botocore.exceptions.ClientError as e:
            error_code = int(e.response['Error']['Code'])
            if error_code == 404:
                fatal("%s does not exists" % self.opts.dst)

        return bucket.Object(name).content_length

def get_file_length(source, color, year, month):
    return get_file_size(source, color, year, month) / RECORD_LENGTH

class Options:
    def __init__(self):
        self.parser = argparse.ArgumentParser(
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)

        self.parser.add_argument('-c', '--color', metavar='yellow|green',
            type=str, default='green', help="color of record")

        self.parser.add_argument('-y', '--year', metavar='YEAR',
            type=int, default=2016, help="year of record")

        self.parser.add_argument('-m', '--month', metavar='MONTH',
            type=int, default=1, help="month of record")

        self.parser.add_argument('-d', '--debug', action='store_true',
            default=False, help="debug mode")

        self.parser.add_argument('--config', type=str,
            default='config.ini', help="configuration file")

        class VAction(argparse.Action):
            def __call__(self, parser, args, values, option_string=None):
                if values is None: values = logging.INFO
                try:
                    values = int(values)
                except ValueError:
                    values = logging.INFO - values.count('v') * 10
                setattr(args, self.dest, values)

        self.parser.add_argument('-v', nargs='?', action=VAction,
            metavar='vv..|NUM',
            dest='verbose', default=logging.WARNING, help='verbose level')

        self.parser.add_argument('--dryrun', action='store_true',
            default=False, help="dryrun")

    def add(self, *args, **kwargs):
        self.parser.add_argument(*args, **kwargs)

    def load(self):
        self.opts = self.parser.parse_args()
        self. _validate()

        # load configurations
        p = ConfigParser.SafeConfigParser()
        cwd = os.path.dirname(__file__)
        p.read(os.path.join(cwd, self.opts.config))
        profile = 'debug' if self.opts.debug else 'default'
        for name, value in p.items(profile):
            setattr(self.opts, name, value)

        return self.opts

    def _validate(self):
        if self.opts.color not in ['yellow', 'green']:
            fatal('unknown color: %s' % self.opts.color)

        date = datetime.datetime(self.opts.year, self.opts.month, 1)
        if not (date >= MIN_DATE[self.opts.color] and \
                date <= MAX_DATE[self.opts.color]):
            fatal('date range must be from %s to %s for %s data' % \
                (MIN_DATE[self.opts.color].strftime('%Y-%m'),
                 MAX_DATE[self.opts.color].strftime('%Y-%m'),
                 self.opts.color))

    def __str__(self):
        return '\n'.join(['%16s: %s' % (attr, value) for attr, value in
                self.opts.__dict__.iteritems()])

    @classmethod
    def parse_argv(cls):
        return Options().load()

if __name__ == '__main__':
    o = Options()
    o.load()
    print(o)
