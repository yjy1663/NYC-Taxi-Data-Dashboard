#!/usr/bin/env python
# All rights reserved.

# Raw Taxi Trip to AWS Storage: S3, Athena

from __future__ import print_function

import argparse
import calendar
import copy
import datetime
import dateutil
import fileinput
import os.path
import re
import sys
import io
from urllib.request import urlopen
import multiprocessing

import bytebuffer
import botocore
import boto3


MIN_DATE = {
    'yellow': datetime.datetime(2009, 1, 1),
    'green' : datetime.datetime(2013, 8, 1)
}
MAX_DATE = {
    'yellow': datetime.datetime(2016, 6, 30),
    'green' : datetime.datetime(2016, 6, 30)
}

def fatal(msg=''):
    if msg:
        sys.stderr.write('error: %s\n' % msg)
        sys.stderr.flush()
    sys.exit(1)

def warning(msg):
    sys.stderr.write('warning: %s\n' % msg)
    sys.stderr.flush()

def info(msg):
    sys.stderr.write('info: %s\n' % msg)
    sys.stderr.flush()

def parse_argv():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Convert raw NYC taxi trip data and transfer it to AWS")

    parser.add_argument("--start", metavar='YYYY-MM',
        type=str, default='2016-01', help="start date")

    parser.add_argument("--end", metavar='YYYY-MM',
        type=str, default='2016-01', help="end date")

    parser.add_argument("--color", metavar='yellow|green',
        type=str, default='yellow', help="taxi color")

    parser.add_argument("--src", metavar='URI',
        type=str, default='http://s3.amazonaws.com/nyc-tlc/trip+data/',
        help="data source directory")

    parser.add_argument("--dst", metavar='URI',
        type=str, default='file://',
        help="data destination directory")

    parser.add_argument("--max-lines", metavar='NUM', type=int,
        dest='max_lines', default=sys.maxint, help="maximum lines")

    parser.add_argument("--buf-size", metavar='NUM', type=int,
        dest='read_buf_size', default=16 * 1024 * 1024,
        help="read buffer size in bytes")

    parser.add_argument("--tagging", metavar='true/false', type=str,
        dest='tagging', default='true',
        help="enable or disable objects tagging")

    parser.add_argument("--procs", metavar='NUM', type=int,
        dest='procs', default=1,
        help="number of parallel process")

    parser.add_argument("--cross-account", action='store_true',
        dest='cross_account', default=False,
        help="enable cross-account copy")

    args = parser.parse_args()

    # check arguments
    args.start = dateutil.parser.parse(args.start + '-01') # set day
    args.end = dateutil.parser.parse(args.end + '-01')
    if args.start > args.end:
        fatal('start date %s is after end date %s' % \
            (args.start.strftime('%Y-%m'), args.end.strftime('%Y-%m')))

    if not (args.start >= MIN_DATE[args.color] and \
            args.end <= MAX_DATE[args.color]):
        fatal('date range must be from %s to %s for %s data' % \
            (MIN_DATE[args.color].strftime('%Y-%m'),
             MAX_DATE[args.color].strftime('%Y-%m'),
             args.color))

    args.tagging = eval(args.tagging.capitalize())

    return args

def get_date_range(start, end):
    def add_months(date, months):
        month = date.month - 1 + months
        year = int(date.year + month / 12)
        month = month % 12 + 1
        day = min(date.day, calendar.monthrange(year, month)[1])
        return datetime.datetime(year, month, day)

    current = start
    while current <= end:
        yield current
        current = add_months(current, 1)

class RawReader(io.IOBase):
    """A file-like raw HTTP data reader and pre-processor
    """

    START_DATE = datetime.datetime(2009,1,1)
    MAX_RECORD_LENGTH = 80
    DEFAULT_BUFFER_SIZE = 16 * 1024 * 1024 # 16MB

    def __init__(self):
        self.data = None
        self.color = 'yellow'
        self.year = 2016
        self.month = 1
        self.buf = None
        self.read_lines = 0
        self.max_lines = sys.maxint

    def alloc_buf(self, size=None):
        if size is None: size = self.DEFAULT_BUFFER_SIZE
        self.buf = bytebuffer.ByteBuffer.allocate(size)
        self.buf.clear()
        self.buf.flip()

    def reformat(self, line):
        def delta_seconds(time):
            delta = dateutil.parser.parse(time) - self.START_DATE
            return int(delta.total_seconds())

        line = line.strip()

        pickup_datetime = None
        dropoff_datetime = None
        pickup_longitude = None
        pickup_latitude = None
        dropoff_longitude = None
        dropoff_latitude = None
        trip_distance = None
        fare_amount = None

        try:
            if self.color == 'green':
                if self.year < 2015:
                    vendor_id, pickup_datetime, dropoff_datetime, \
                    store_and_fwd_flag, rate_code, pickup_longitude, \
                    pickup_latitude, dropoff_longitude, dropoff_latitude, \
                    passenger_count, trip_distance, fare_amount, extra, \
                    mta_tax, tip_amount, tolls_amount, ehail_fee, total_amount, \
                    payment_type, trip_type, _, _ = line.split(',')
                elif self.year == 2015 and self.month < 7:
                    vendor_id, pickup_datetime, dropoff_datetime, \
                    store_and_fwd_flag, rate_code, pickup_longitude, \
                    pickup_latitude, dropoff_longitude, dropoff_latitude, \
                    passenger_count, trip_distance, fare_amount, extra, \
                    mta_tax,tip_amount, tolls_amount, ehail_fee, surcharge, \
                    total_amount, payment_type, trip_type, _, _ = line.split(',')
                else:
                    vendor_id, pickup_datetime, dropoff_datetime, \
                    store_and_fwd_flag, rate_code, pickup_longitude, \
                    pickup_latitude, dropoff_longitude, dropoff_latitude, \
                    passenger_count, trip_distance, fare_amount, extra, \
                    mta_tax, tip_amount, tolls_amount, ehail_fee, surcharge, \
                    total_amount, payment_type, trip_type = line.split(',')
            elif self.color == 'yellow':
                if self.year < 2015:
                    vendor_id, pickup_datetime, dropoff_datetime, \
                    passenger_count, trip_distance, pickup_longitude, \
                    pickup_latitude, rate_code, store_and_fwd_flag, \
                    dropoff_longitude, dropoff_latitude, payment_type,\
                    fare_amount, extra, mta_tax, tip_amount, \
                    tolls_amount, total_amount = line.split(',')
                else:
                    vendor_id, pickup_datetime, dropoff_datetime, \
                    passenger_count, trip_distance, pickup_longitude, \
                    pickup_latitude, rate_code, store_and_fwd_flag, \
                    dropoff_longitude, dropoff_latitude, payment_type, \
                    fare_amount, extra, mta_tax, tip_amount, tolls_amount, \
                    surcharge, total_amount = line.split(',')

            # checking and compact data
            if pickup_longitude == '0' or pickup_latitude == '0' or \
               dropoff_longitude == '0' or dropoff_latitude == '0':
               return None

            pickup_datetime = "%d" % delta_seconds(pickup_datetime)
            dropoff_datetime = "%d" % delta_seconds(dropoff_datetime)
            pickup_longitude = "%.6f" % float(pickup_longitude)
            pickup_latitude = "%.6f" % float(pickup_latitude)
            dropoff_longitude = "%.6f" % float(dropoff_longitude)
            dropoff_latitude = "%.6f" % float(dropoff_latitude)
            trip_distance = "%.2f" % float(trip_distance)
            fare_amount = "%.2f" % float(fare_amount)

        except :
            warning("%s-%s-%02d: %s: d%s d%s f%s f%s f%s f%s f%s f%s" % \
                (self.color, self.year, self.month, e,
                 pickup_datetime, dropoff_datetime,
                 pickup_longitude, pickup_latitude,
                 dropoff_longitude, dropoff_latitude,
                 trip_distance, fare_amount))
            return None

        line = ','.join([pickup_datetime, dropoff_datetime, \
                         pickup_longitude, pickup_latitude, \
                         dropoff_longitude, dropoff_latitude, \
                         trip_distance, fare_amount, \
                         '']) # for right padding

        if len(line) > self.MAX_RECORD_LENGTH:
            warning("record length > %s, skip..." % self.MAX_RECORD_LENGTH)
            return None
        else:
            # make each record same length for offset seek
            return line.ljust(self.MAX_RECORD_LENGTH - 1, '*') + '\n'

    def open(self, color, year, month, source, max_lines, buf_size):
        self.color = color
        self.year = year
        self.month = month
        self.max_lines = max_lines
        self.alloc_buf(min(buf_size, self.MAX_RECORD_LENGTH * max_lines))

        if source.startswith('http://') or source.startswith('https://'):
            filename = '%s/%s_tripdata_%s-%02d.csv' % \
                (source.strip('/'), color, year, month)
            # HOWTO:
            # Unfortunately, boto3 does not provide read by lines
            # following code is not efficient
            # s3 = boto3.resource('s3')
            # obj = s3.Object('nyc-tlc','trip data/' + filename)
            # self.data = obj.get()["Body"].read()
            # for line in self.data.split('\n'):
            #    print(line)
            self.data = urlopen(filename)
        elif source.startswith('file://'):
            directory = os.path.realpath(source[7:])
            if not os.path.isdir(directory):
                fatal("%s is not a directory." % directory)

            path = '%s/%s_tripdata_%s-%02d.csv' % (directory, color, year, month)
            if not os.path.exists(path):
                fatal("%s does not exist." % path)
            if not os.path.isfile(path):
                fatal("%s is not a regular file." % path)

            info(" read: file://%s" % path)
            self.data = open(path, 'r')
        elif source == '-':
            self.data = fileinput.input('-')

        # skip header and empty line
        self.data.readline(); self.data.readline()

        return self

    def close(self):
        self.data.close()

    def read(self, size=None):
        if size < 0: size = None # in case size = -1
        if size > self.buf.get_capacity():
            #TODO: risk of data loss if 2nd request size > 1st request size
            self.alloc_buf(size * 2)

        # HOWTO: http://tutorials.jenkov.com/java-nio/buffers.html
        if self.buf.get_remaining() >= size:
            return self.buf.get_bytes(size)
        else: # not enough data, fill buffer
            self.buf.compact()
            while self.buf.get_remaining() >= self.MAX_RECORD_LENGTH:
                line = self.data.readline()
                self.read_lines += 1
                if self.read_lines > self.max_lines: line = None
                if not line: break # EOF
                line = self.reformat(line)
                if line: self.buf.put(bytearray(line))
            self.buf.flip()
            remaining = self.buf.get_remaining()
            if remaining == 0: return bytearray()
            if remaining < size: return self.buf.get_bytes()
            return self.buf.get_bytes(size)

    def readline(self):
        line = self.data.readline()
        if not line: return ''
        line = self.reformat(line)
        if line: return line

    def readlines(self):
        while True:
            line = self.data.readline()
            if not line: break
            line = self.reformat(line)
            if line: yield line

    def istty(self): return False

    def readable(self): return True

    def seekable(self): return False

    def seek(self): raise io.UnsupportOperation

    def writable(self): return False

    def writelines(self, lines): raise io.UnsupportOperation

    def truncate(size=None): raise io.UnsupportOperation

    def tell(self): raise io.UnsupportOperation # TODO

class Raw2AWS:
    def __init__(self, opts):
        self.opts = opts
        # HOWTO: create S3 resource and client
        self.s3 = boto3.resource('s3')
        self.client = boto3.client('s3')
        self.reader = RawReader()

    def output(self, fin, date):
        if self.opts.dst.startswith('file://'):
            path = os.path.realpath(self.opts.dst[7:])

            if not os.path.exists(path):
                fatal("%s does not exist." % path)
            if not os.path.isdir(path):
                fatal("%s is not a directory." % path)

            filename = os.path.join(path, \
                '%s-%s-%02d.csv' % (self.opts.color, date.year, date.month))
            info('write: file://%s' % filename)
            with open(filename, 'w') as fout:
                for i, line in enumerate(fin.readlines()):
                    if i >= self.opts.max_lines: break
                    fout.write(line)

        elif self.opts.dst.startswith('s3://'):
            bucket = self.s3.Bucket(self.opts.dst[5:])

            # HOWTO: check if a bucket exists
            # If a client error is thrown, then check that it was a 404 error.
            # If it was a 404 error, then the bucket does not exist.
            try:
                self.s3.meta.client.head_bucket(Bucket=bucket.name)
            except botocore.exceptions.ClientError as e:
                error_code = int(e.response['Error']['Code'])
                if error_code == 404:
                    fatal("%s does not exists" % self.opts.dst)

            key = '%s-%s-%02d.csv' % (self.opts.color, date.year, date.month)
            obj = bucket.Object(key)
            args, config = None, None
            try:
                if self.opts.cross_account:
                    # HOWTO: cross-account copy
                    # need both acl and multipart upload threshold
                    # https://github.com/aws/aws-cli/issues/1674
                    config = boto3.s3.transfer.TransferConfig(
                        multipart_threshold=4 * (1024 ** 3))
                    args = {'ACL': 'bucket-owner-full-control'}
                obj.upload_fileobj(fin, ExtraArgs=args, Config=config)
            except botocore.exceptions.ClientError as e:
                error_code = int(e.response['Error']['Code'])
                fatal("%s" % error_code)

            if self.opts.tagging:
                # HOWTO: tagging object
                self.client.put_object_tagging(
                    Bucket=bucket.name,
                    Key=key,
                    Tagging = {'TagSet': [
                        {'Key': 'color', 'Value': self.opts.color },
                        {'Key': 'year',  'Value': str(date.year) },
                        {'Key': 'month', 'Value': str(date.month) }
                    ]})

        elif self.opts.dst == '-':
            for i, line in enumerate(fin.readlines()):
                if i >= self.opts.max_lines: break
                sys.stdout.write(line)
            sys.stdout.flush()

    def run(self):
        try:
            for date in get_date_range(self.opts.start, self.opts.end):
                self.run_date(date)
        except KeyboardInterrupt as e:
            return

    def run_date(self, date):
        with self.reader.open(self.opts.color, date.year, date.month,
                              self.opts.src, self.opts.max_lines,
                              self.opts.read_buf_size) as fin:
            self.output(fin, date)

def start_process(args):
    r = Raw2AWS(args)
    r.run()

def main():
    args = parse_argv()
    tasks = []

    for date in get_date_range(args.start, args.end):
        args_copy = copy.deepcopy(args)
        args_copy.start, args_copy.end = date, date
        tasks.append(args_copy)

    try:
        procs = multiprocessing.Pool(processes=args.procs)
        procs.map(start_process, tasks)
    except Exception as e:
        fatal(e)

if __name__ == '__main__':
    main()
