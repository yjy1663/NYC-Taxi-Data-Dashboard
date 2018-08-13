#!/usr/bin/env python
# All rights reserved.

# Tasks Management and Queuing

import logging
import sys

import boto3
import botocore

from common import *

logging.basicConfig()

def parse_argv():
    o = Options()
    o.add('--create-tasks', type=int, dest='create_tasks', metavar='NUM',
        default=-1, help='create tasks')
    o.add('--receive-tasks', type=int, dest='receive_tasks', metavar='NUM',
        default=0, help='receive tasks')
    o.add('--delete-after-receive', dest='delete_received', action='store_true',
        default=False, help='delete task after successful receive')
    o.add('--count-tasks', dest='count_tasks', action='store_true',
        default=False, help='count tasks')
    o.add('--purge-queue', dest='purge_queue', action='store_true',
        default=False, help='purge queue')

    return o.load()

class Task:
    def __init__(self, color, year, month, start, end,
            timeout=3600, sqs_id=None, sqs_handle=None):
        self.color = color
        self.year = year
        self.month = month
        self.start = start
        self.end = end
        self.timeout = timeout  # If not succeeded in 3600 seconds, expires
        self.status  = None

        # for task retry
        self.sqs_id = sqs_id          # SQS message ID
        self.sqs_handle = sqs_handle  # SQS message handle

    def encode(self):
        return self.__str__()

    @classmethod
    def decode(cls, message):
        color, year, month, start, end, timeout = message.body.split(',')

        return Task(color, int(year), int(month), int(start), int(end),
            int(timeout), message.message_id, message.receipt_handle)

    def __repr__(self):
        return "%(color)s:%(year)s:%(month)s:[%(start)d,%(end)d):%(timeout)d" % \
            (self.__dict__)

    def __str__(self):
        return "%(color)s,%(year)d,%(month)d,%(start)d,%(end)d,%(timeout)d" % \
            (self.__dict__)

class TaskManager:
    def __init__(self, opts):
        self.opts = opts

        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(self.opts.verbose)

        self.sqs = boto3.resource('sqs', region_name=opts.region)
        self.logger.debug('queue:%s' % self.opts.sqs_queue)
        self.queue = self.sqs.Queue(self.opts.sqs_queue)

        self.s3 = boto3.resource('s3')
        self.logger.debug('bucket:%s' % self.opts.bucket)
        self.bucket = self.s3.Bucket(self.opts.bucket)

    @classmethod
    def cut(cls, start, end, N, nth=None):
        """Cut a range [start, end] into N parts [nth, nth+1)"""
        parts = range(start, end + 1, (end - start) / N)
        parts[-1] = end + 1
        if nth is None: return [[parts[i], parts[i+1]] for i in range(N)]
        return [parts[nth], parts[nth+1]]

    def create_tasks(self, color, year, month, n_tasks=0):
        if n_tasks < 0: return

        try:
            self.s3.meta.client.head_bucket(Bucket=self.bucket.name)
        except botocore.exceptions.ClientError as e:
            error_code = int(e.response['Error']['Code'])
            if error_code == 404:
                self.logger.critical('s3://%s does not exists' % self.bucket.name)
                sys.exit(1)

        key = '%s-%s-%02d.csv' % (color, year, month)
        obj = self.bucket.Object(key)
        n_records = obj.content_length / RECORD_LENGTH
        if n_tasks == 0:
            n_tasks = (n_records / int(self.opts.records_per_task)) + 1

        self.logger.debug('create tasks for s3://%s/%s (%d)' % \
            (self.bucket.name, key, n_records))

        for record_range in self.cut(0, n_records, n_tasks):
            task = Task(color, year, month, record_range[0], record_range[1],
                int(self.opts.task_timeout))
            self.logger.debug('%r => create' % task)
            if not self.opts.dryrun:
                self.queue.send_message(MessageBody=task.encode())

    def retrieve_task(self, delete=False, **kwargs):
        try:
            message = self.queue.receive_messages(
                MaxNumberOfMessages=1, WaitTimeSeconds=1)[0]
        except IndexError as e:
            self.logger.debug("no more task")
            return None

        task = Task.decode(message)
        self.logger.debug('%r => retreive' % task)

        # change task visiblity in case of failure and retry
        if delete:
            self.logger.debug('%r (%s) => delete' % (task, task.sqs_id))
            message.delete()
        else:
            self.logger.debug('%r (%s) => hold' % (task, task.sqs_id))
            message.change_visibility(VisibilityTimeout=task.timeout)

        return task

    def delete_task(self, task):
        self.logger.debug('%r (%s) => delete' % (task, task.sqs_id))
        self.queue.delete_messages(
            Entries = [{'Id': task.sqs_id, 'ReceiptHandle': task.sqs_handle}])

    def count_tasks(self):
        self.queue.reload()
        attr = self.queue.attributes
        remain = int(attr['ApproximateNumberOfMessages'])
        retry  = int(attr['ApproximateNumberOfMessagesNotVisible'])
        return remain, retry

    def purge_queue(self):
        self.logger.warning('%s => purge' % self.opts.sqs_queue)
        self.queue.purge()

    def run(self):
        if self.opts.purge_queue: self.purge_queue()

        self.create_tasks(self.opts.color, self.opts.year, self.opts.month,
            self.opts.create_tasks)

        if self.opts.count_tasks:
            print('Tasks remain: %d, retry: %d' % self.count_tasks())

        for i in range(self.opts.receive_tasks):
            print('received %r' % self.retrieve_task(self.opts.delete_received))

if __name__ == '__main__':
    tm = TaskManager(parse_argv())
    tm.run()
