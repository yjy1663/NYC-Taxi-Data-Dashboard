#!/usr/bin/env python

# S3 Operation Examples

import argparse
import random
import sys
import string
import time
import uuid

import Queue
import threading

import boto3
import boto3.session
import botocore

from collections import defaultdict
from datetime import datetime
from cStringIO import StringIO

# Utilities
VERBOSE_INFO  = 0
VERBOSE_DEBUG = 1
VERBOSE_TRACE = 2
VERBOSE_LEVEL = VERBOSE_INFO

def fatal(message=''):
    if message:
        sys.stderr.write('fatal: %s\n' % message)
        sys.stderr.flush()
    sys.exit(1)

def warning(message):
    sys.stderr.write('warning: %s\n' % message)
    sys.stderr.flush()

def info(message):
    if VERBOSE_LEVEL >= VERBOSE_INFO:
        sys.stderr.write('info: %s\n' % message)
        sys.stderr.flush()

def debug(message):
    if VERBOSE_LEVEL >= VERBOSE_DEBUG:
        sys.stderr.write('debug: %s\n' % message)
        sys.stderr.flush()

def trace(message):
    if VERBOSE_LEVEL >= VERBOSE_TRACE:
        sys.stderr.write('trace: %s\n' % message)
        sys.stderr.flush()

def human2bytes(size):
    num = int(size.strip('KMGB'))
    if   size.upper().endswith('KB'): return num * 1024
    elif size.upper().endswith('MB'): return num * (1024 ** 2)
    elif size.upper().endswith('GB'): return num * (1024 ** 3)
    else:
        fatal('unknown value: %s' % size)

def bytes2human(num, round2int=False):
    format_str = '%.3f%s'
    if round2int: format_str = '%d%s'
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if abs(num) < 1024.0:
            return format_str % (num, unit)
        num /= 1024.0
    return format_str % (num, 'EB')

timer = time.clock if sys.platform == 'win32' else time.time

_elapased = 0.0
def timing_start():
    global _elapsed
    _elapsed = timer()

def timing_stop(message=''):
    global _elapsed
    _elapsed = timer() - _elapsed
    if message:
        info('%s: %.3f seconds' % (message, _elapsed))

# Parse argument
parser = argparse.ArgumentParser(
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)

parser.add_argument('-n', '--objects-number', type=int,
    dest='objects_nums', default=10, help='number of objects')

parser.add_argument('-s', '--objects-size', type=str,
    dest='object_size', default='1MB',
    help='objects size in bytes, KB, MB, or GB')

parser.add_argument('-t', '--threads-num', type=int,
    default=1, help='number of concurrent threads')

parser.add_argument('-o', '--optimal', action='store_true',
    default=False, help='optimal transfer using low-level control')

parser.add_argument('-x', '--max-concurrency', type=int,
    default=32, help='maximum concurrency')

parser.add_argument('-d', '--dryrun', help="dry run, nothing will be executed",
    action="store_true")

parser.add_argument('-v', "--verbose", metavar='INT', type=int,
    default=VERBOSE_LEVEL, help="output verbosity")

parser.add_argument("--clean", dest='clean', action='store_true',
    default=False, help="clean and remove buckets")

args = parser.parse_args()

VERBOSE_LEVEL = args.verbose
object_size = human2bytes(args.object_size)

# Get AWS account Information
session = boto3.session.Session()
iam_client = boto3.client('iam')
s3_client = boto3.client('s3')
aws_user_id = iam_client.list_users()['Users'][0]['UserId'] # HOWTO: get user id
aws_region = session.region_name                            # HOWTO: get profile region
debug('AWS user ID: %s' % aws_user_id)
debug('AWS region: %s' % aws_region)

# Prepare buckets
bucket_name_prefix = ("s3cp-%s-%s" % (\
    aws_user_id[0:8],
    datetime.now().strftime('%y%m%d'))).lower() # NOTE: bucket name must be lower case
s3 = boto3.resource('s3')

src_bucket = s3.Bucket(bucket_name_prefix + '-from')
dst_bucket = s3.Bucket(bucket_name_prefix + '-to')
debug('source bucket: %s' % src_bucket.name)
debug('destination bucket: %s' % dst_bucket.name)

# Empty and delete buckets
if args.clean:
    timing_start()
    deleted_objects = 0

    for bucket in [src_bucket, dst_bucket]:
        try:
            for key in bucket.objects.all(): # HOWTO: get all objects 
                trace('delete object: %s/%s' % (key.bucket_name, key.key))
                if not args.dryrun:
                    key.delete()
                    deleted_objects += 1
            trace('delete bucket: %s' % bucket.name)
            if not args.dryrun: bucket.delete()
        except botocore.exceptions.ClientError as e:
            # HOWTO: catch boto exceptions
            if e.response['Error']['Code'] == 'NoSuchBucket':
                warning('bucket s3://%s does not exist' % bucket.name)
            else:
                raise

    timing_stop('deleted %d objects' % deleted_objects)
    sys.exit(0)

# Create buckets
if not args.dryrun:
    timing_start()
    for bucket in [src_bucket, dst_bucket]:
        try:
            bucket.create( # HOWTO: create bucket
                CreateBucketConfiguration = {'LocationConstraint': 'us-west-2'},
            )
        except botocore.exceptions.ClientError as e:
            # HOWTO: catch boto exceptions
            if e.response['Error']['Code'] == 'BucketAlreadyOwnedByYou':
                warning('bucket s3://%s has been created' % bucket.name)
            else:
                raise

    timing_stop('create buckets')

# Create objects
tasks = Queue.Queue(args.threads_num * 2)

def create_objects_by_thread(thread_id):
    # HOWTO: each thread should have its own session
    # http://boto3.readthedocs.io/en/latest/guide/resources.html#multithreading
    session = boto3.session.Session()

    if args.optimal:
        # HOWTO: low-level control
        # http://boto3.readthedocs.io/en/latest/_modules/boto3/s3/transfer.html
        client_config = botocore.config.Config(
            max_pool_connections=args.max_concurrency)
        transfer_config = boto3.s3.transfer.TransferConfig(
            multipart_threshold=8 * 1024 * 1024,
            multipart_chunksize=8 * 1024 * 1024,
            max_concurrency=args.max_concurrency,
            num_download_attempts=5,
            max_io_queue=100,
            io_chunksize=256 * 1024)
        client = session.client('s3', config=client_config)
    else:
        s3 = session.resource('s3')

    while True:
        key = tasks.get()
        content = StringIO('*' * object_size)
        trace('thread %d create object: s3://%s/%s' % \
            (thread_id, src_bucket.name, key))
        if not args.dryrun:
            if args.optimal:
                client.upload_fileobj(content, src_bucket.name, key,
                    Config=transfer_config)
            else:
                obj = s3.Object(src_bucket.name, key)
                obj.upload_fileobj(content)
        tasks.task_done()

timing_start()

for i in xrange(args.threads_num):
    t = threading.Thread(target=create_objects_by_thread, args=(i,))
    t.daemon = True
    t.start()

for i in xrange(args.objects_nums):
    # HOWTO: construct a well distributed key
    key = '%s-%s-%d.s3cp' % (
        uuid.uuid3(uuid.NAMESPACE_DNS,
                   (str(99999999 - i) + args.object_size).encode()).hex,
        args.object_size, i)
    tasks.put(key)

tasks.join()
timing_stop('created %d objects by %d threads' % (args.objects_nums, args.threads_num))

# Copy objects

#with tasks.mutex: tasks.queue.clear()
tasks = Queue.Queue(args.threads_num * 2)
copied_objects = [0] * args.threads_num

def copy_objects_by_thread(thread_id, copied_objects):
    # HOWTO: each thread should have its own session
    # http://boto3.readthedocs.io/en/latest/guide/resources.html#multithreading
    session = boto3.session.Session()

    if args.optimal:
        # HOWTO: low-level control
        # http://boto3.readthedocs.io/en/latest/_modules/boto3/s3/transfer.html
        client_config = botocore.config.Config(
            max_pool_connections=args.max_concurrency)
        transfer_config = boto3.s3.transfer.TransferConfig(
            multipart_threshold=8 * 1024 * 1024,
            multipart_chunksize=8 * 1024 * 1024,
            max_concurrency=args.max_concurrency,
            num_download_attempts=5,
            max_io_queue=100,
            io_chunksize=256 * 1024)
        client = session.client('s3', config=client_config)
    else:
        s3 = session.resource('s3')
        client = session.client('s3')

    count = 0
    while True:
        prefix = tasks.get()
        # HOWTO: list objects
        response = s3_client.list_objects_v2(
            Bucket=src_bucket.name,
            Prefix=prefix) # Important: using prefix to limit listing
        for content in response['Contents']:
            key = content['Key']
            trace('thread %d copy object: s3://%s/%s' % \
                (thread_id, src_bucket.name, key))
            if not args.dryrun:
                if args.optimal:
                    client.copy(
                        CopySource={'Bucket': src_bucket.name, 'Key': key},
                        Bucket=dst_bucket.name, Key=key,
                        Config=transfer_config)
                else:
                    obj = s3.Object(dst_bucket.name, key)
                    obj.copy_from(
                        CopySource={'Bucket': src_bucket.name, 'Key': key},
                    )
                count += 1
        copied_objects[thread_id] = count
        tasks.task_done()

timing_start()

existing_prefixes = []
for prefix in string.ascii_lowercase + string.digits:
    # HOWTO: use prefix to restrict listing objects
    response = s3_client.list_objects_v2(
        Bucket=src_bucket.name,
        Prefix=prefix,
        MaxKeys=1) # NOTE: MaxKeys=1 since we only test object existence
    if response['KeyCount'] > 0:
        existing_prefixes.append(prefix)

debug('existing prefixes: %s' % existing_prefixes)
for i in xrange(args.threads_num):
    t = threading.Thread(target=copy_objects_by_thread, args=(i, copied_objects))
    t.daemon = True
    t.start()

for prefix in existing_prefixes:
    tasks.put(prefix)

tasks.join()

for i in xrange(args.threads_num):
    info('thread %d copied %d objects' % (i, copied_objects[i]))
timing_stop('copied %d objects by %d threads' % (sum(copied_objects), args.threads_num))
