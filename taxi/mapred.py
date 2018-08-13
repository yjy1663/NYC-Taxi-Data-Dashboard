#!/usr/bin/env python

# All rights reserved.

from __future__ import print_function

import argparse
import copy
import datetime
import decimal
import io
import json
import logging
import multiprocessing
import os.path
import sys
import time

import boto3
import botocore

from collections import Counter
from boto3.dynamodb.conditions import Key, Attr

from common import *
from geo import NYCBorough, NYCGeoPolygon
from tasks import TaskManager

logging.basicConfig()
logger = logging.getLogger(os.path.basename(__file__))

def parse_argv():
    o = Options()
    o.add('--src', metavar='URI', type=str,
        default='s3://aws-nyc-taxi-data', help="data source directory")
    o.add('-s', '--start',  metavar='NUM', type=int,
        default=0, help="start record index")
    o.add('-e', '--end',  metavar='NUM', type=int,
        default=4 * 1024 ** 3, help="end record index")
    o.add('-r', '--report', action='store_true',
        default=False, help="report results")
    o.add('-p', '--procs', type=int, dest='nprocs',
        default=1, help="number of concurrent processes")
    o.add('-w', '--worker', action='store_true',
        default=False, help="worker mode")
    o.add('--sleep', type=int,
        default=10, help="worker sleep time if no task")

    opts = o.load()

    if opts.start < 0 or opts.start > opts.end:
        fatal("invalid range [%d, %d]" % (opts.start, opts.end))

    opts.end = min(get_file_length(
        opts.src, opts.color, opts.year, opts.month), opts.end)

    logger.setLevel(opts.verbose)
    return opts

class RecordReader(io.IOBase):
    DATA_STDIN = 1
    DATA_FILE = 2
    DATA_S3 = 3

    def __init__(self):
        self.data = None
        self.start = 0
        self.end = 0
        self.data_type = -1

        self.s3 = boto3.resource('s3')
        self.client = boto3.client('s3')

        self.path = ''
        self.proc = multiprocessing.current_process().name

    def open(self, color, year, month, source, start, end):
        self.start = start
        self.end = end
        self.skip = None
        filename = get_file_name(color, year, month)

        if source.startswith('file://'):
            self.data_type = self.DATA_FILE
            directory = os.path.realpath(source[7:])
            path = '%s/%s' % (directory, filename)
            self.path = 'file://' + path

            self.data = open(path, 'r')
            self.data.seek(RECORD_LENGTH * self.start)

        elif source.startswith('s3://'):
            self.data_type = self.DATA_S3
            bucket = self.s3.Bucket(source[5:])

            # HOWTO: read object by range
            obj = bucket.Object(filename)
            self.path = 's3://%s/%s' %(bucket.name, filename)

            bytes_range = 'bytes=%d-%d' % \
                (self.start * RECORD_LENGTH, \
                 self.end * RECORD_LENGTH - 1)
            self.data = obj.get(Range=bytes_range)['Body']

        logger.info("%s [%d, %d) => %s" % \
            (self.path, self.start, self.end, self.proc))
        return self

    def readline(self):
        if self.data_type == self.DATA_S3:
            # HOWTO: fixed length makes read very easy
            return self.data.read(RECORD_LENGTH)
        return self.data.readline()

    def readlines(self):
        start = self.start
        skip = 0
        while start < self.end:
            line = self.readline()
            if skip < self.skip: skip += 1; continue # for stdin read
            start += 1
            if not line: break
            yield line

    def close(self):
        self.data.close()

class StatDB:
    def __init__(self, opts):
        self.ddb = boto3.resource('dynamodb',
            region_name=opts.region, endpoint_url=opts.ddb_endpoint)
        self.table = self.ddb.Table(opts.ddb_table_name)
        try:
            assert self.table.table_status == 'ACTIVE'
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                logger.warning("table %s does not exist" % self.table.table_name)
            logger.debug("create table %s/%s" % \
                (opts.ddb_endpoint, self.table.table_name))
            self.create_table()

    def create_table(self):
        self.table = self.ddb.create_table(
            TableName='taxi',
            KeySchema=[
                {
                    'AttributeName': 'color',
                    'KeyType': 'HASH'   # partition key
                },
                {
                    'AttributeName': 'date',
                    'KeyType': 'RANGE'  # sort key
                }
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'color',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'date',
                    'AttributeType': 'N'
                },

            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 2,
                'WriteCapacityUnits': 10
            }
        )

    def append(self, stat):
        def add_values(counter, prefix):
            for key, count in counter.items():
                values[':%s%s' % (prefix, key)] = count

        values = {}

        # use one letter to save bytes, thus write/read units
        # must not overlap with 'color' and 'date'
        values[':l'] = stat.total
        values[':i'] = stat.invalid
        add_values(stat.pickups,   'p')
        add_values(stat.dropoffs,  'r')
        add_values(stat.hour,      'h')
        add_values(stat.trip_time, 't')
        add_values(stat.distance,  's')
        add_values(stat.fare,      'f')
        add_values(stat.borough_pickups,  'k')
        add_values(stat.borough_dropoffs, 'o')

        # HOWTO: contrurct update expression
        expr = ','.join([k[1:] + k for k in values.keys()])

        self.table.update_item(
            Key={'color': stat.color, 'date': stat.year * 100 + stat.month},
            UpdateExpression='add ' + expr,
            ExpressionAttributeValues=values
        )

    def get(self, color, year, month):
        def add_stat(counter, prefix):
            for key, val in values.items():
                if key.startswith(prefix):
                    counter[int(key[1:])] = int(val)

        stat = TaxiStat(color, year, month)
        try:
            response = self.table.get_item(
                Key={
                    'color': color,
                    'date': year * 100 + month
                }
            )

            values = response['Item']

            stat.total = values['l']
            stat.invalid = values['i']
            add_stat(stat.pickups,   'p')
            add_stat(stat.dropoffs,  'r')
            add_stat(stat.hour,      'h')
            add_stat(stat.trip_time, 't')
            add_stat(stat.distance,  's')
            add_stat(stat.fare,      'f')
            add_stat(stat.borough_pickups,  'k')
            add_stat(stat.borough_dropoffs, 'o')
        except botocore.exceptions.ClientError as e:
            logger.warning(e.response['Error']['Message'])
        except KeyError:
            logger.warning('item () => not found')
        finally:
            return stat

    def purge(self):
        logger.warning('%s => purge' % self.table.table_arn)
        for color in ['yellow', 'green']:
            response = self.table.query(
                KeyConditionExpression=Key('color').eq(color))
            for item in response['Items']:
                self.table.delete_item(Key={
                    'color': item['color'],
                    'date':  item['date']
                })

class TaxiStat(object):
    def __init__(self, color=None, year=0, month=0):
        self.color = color
        self.year = year
        self.month = month
        self.total = 0                      # number of total records
        self.invalid = 0                    # number of invalid records
        self.pickups = Counter()            # district -> # of pickups
        self.dropoffs = Counter()           # district -> # of dropoffs
        self.hour = Counter()               # pickup hour distriibution
        self.trip_time = Counter()          # trip time distribution
        self.distance = Counter()           # distance distribution
        self.fare = Counter()               # fare distribution
        self.borough_pickups  = Counter()   # borough -> # of pickups
        self.borough_dropoffs = Counter()   # borough -> # of dropoffs

    def get_hour(self):
        return [self.hour[i] for i in range(24)]

    def get_trip_time(self):
        return [self.trip_time[i] \
            for i in [0, 300, 600, 900, 1800, 2700, 3600]]

    def get_distance(self):
        return [self.distance[i] for i in [0, 1, 2, 5, 10, 20]]

    def get_fare(self):
        return [self.fare[i] for i in [0, 5, 10, 25, 50, 100]]

class NYCTaxiStat(TaxiStat):
    def __init__(self, opts):
        super(NYCTaxiStat, self).__init__(opts.color, opts.year, opts.month)
        self.opts = opts
        self.reader = RecordReader()
        self.elapsed = 0
        self.districts = NYCGeoPolygon.load_districts()
        self.path = ''

    def __add__(self, x):
        if self is x: return self
        self.total += x.total
        self.invalid += x.invalid
        self.pickups += x.pickups
        self.dropoffs += x.dropoffs
        self.hour += x.hour
        self.trip_time += x.trip_time
        self.distance += x.distance
        self.fare += x.fare
        self.elapsed = max(self.elapsed, x.elapsed)
        return self

    def __repr__(self):
        return '%s [%d, %d)' % \
            (self.path, self.opts.start, self.opts.end)

    def search(self, line):
        def delta_time(seconds):
            return BASE_DATE + datetime.timedelta(seconds=seconds)

        pickup_datetime, dropoff_datetime, \
        pickup_longitude, pickup_latitude, \
        dropoff_longitude, dropoff_latitude, \
        trip_distance, fare_amount, _ = line.strip().split(',')

        pickup_datetime = int(pickup_datetime)
        dropoff_datetime = int(dropoff_datetime)
        trip_time = dropoff_datetime - pickup_datetime
        pickup_hour = delta_time(pickup_datetime).hour
        # We don't need dropoff time
        # dropoff_datetime = delta_time(dropoff_datetime)

        pickup_longitude = float(pickup_longitude)
        pickup_latitude = float(pickup_latitude)
        dropoff_longitude = float(dropoff_longitude)
        dropoff_latitude = float(dropoff_latitude)
        trip_distance = float(trip_distance)
        fare_amount = float(fare_amount)

        pickup_district, dropoff_district = None, None

        # Note: district in particular order, see geo.py
        for district in self.districts:
            if pickup_district is None and \
               (pickup_longitude, pickup_latitude) in district:
                pickup_district = district.index
            if dropoff_district is None and \
               (dropoff_longitude, dropoff_latitude) in district:
                dropoff_district = district.index
            if pickup_district and dropoff_district: break

        self.total += 1
        if pickup_district is None and dropoff_district is None:
            logger.debug("(%f, %f) >> (%f, %f) => unable to locate" % \
                (pickup_longitude, pickup_latitude, \
                 dropoff_longitude, dropoff_latitude))
            self.invalid += 1
            return None

        if pickup_district:  self.pickups[pickup_district] += 1
        if dropoff_district: self.dropoffs[dropoff_district] += 1
        self.hour[pickup_hour] += 1

        if   trip_distance >= 20: self.distance[20] += 1
        elif trip_distance >= 10: self.distance[10] += 1
        elif trip_distance >= 5:  self.distance[5]  += 1
        elif trip_distance >= 2:  self.distance[2]  += 1
        elif trip_distance >= 1:  self.distance[1]  += 1
        else:                     self.distance[0]  += 1

        if   trip_time >= 3600:   self.trip_time[3600] += 1
        elif trip_time >= 2700:   self.trip_time[2700] += 1
        elif trip_time >= 1800:   self.trip_time[1800] += 1
        elif trip_time >= 900:    self.trip_time[900]  += 1
        elif trip_time >= 600:    self.trip_time[600]  += 1
        elif trip_time >= 300:    self.trip_time[300]  += 1
        else:                     self.trip_time[0]    += 1

        if   fare_amount >= 100:  self.fare[100] += 1
        elif fare_amount >= 50:   self.fare[50]  += 1
        elif fare_amount >= 25:   self.fare[25]  += 1
        elif fare_amount >= 10:   self.fare[10]  += 1
        elif fare_amount >= 5:    self.fare[5]   += 1
        else:                     self.fare[0]   += 1

    def report(self):
        width = 50
        report_date = datetime.datetime(self.opts.year, self.opts.month, 1)
        title = " NYC %s Cab, %s " %\
            (self.opts.color.capitalize(), report_date.strftime('%B %Y'))
        print(title.center(width, '='))

        format_str = "%14s: %16s %16s"
        print(format_str % ('Borough', 'Pickups', 'Dropoffs'))
        for index, name in NYCBorough.BOROUGHS.items():
            print(format_str % (name,
                                self.borough_pickups[index],
                                self.borough_dropoffs[index]))

        print(" Pickup Time ".center(width, '-'))
        format_str = "%14s: %33s"
        for hour in range(24):
            if hour in self.hour:
                hour_str = '%d:00 ~ %d:59' % (hour, hour)
                print(format_str % (hour_str, self.hour[hour]))

        print(" Trip Distance (miles) ".center(width, '-'))
        format_str = "%14s: %33s"
        print(format_str % ('0 ~ 1',   self.distance[0]))
        print(format_str % ('1 ~ 2',   self.distance[1]))
        print(format_str % ('2 ~ 5',   self.distance[2]))
        print(format_str % ('5 ~ 10',  self.distance[5]))
        print(format_str % ('10 ~ 20', self.distance[10]))
        print(format_str % ('> 20',    self.distance[20]))

        print(" Trip Time (minutes) ".center(width, '-'))
        format_str = "%14s: %33s"
        print(format_str % ('0 ~ 5',   self.trip_time[0]))
        print(format_str % ('5 ~ 10',  self.trip_time[300]))
        print(format_str % ('10 ~ 15', self.trip_time[600]))
        print(format_str % ('15 ~ 30', self.trip_time[900]))
        print(format_str % ('30 ~ 45', self.trip_time[1800]))
        print(format_str % ('45 ~ 60', self.trip_time[2700]))
        print(format_str % ('> 60',    self.trip_time[3600]))

        print(" Fare (dollars) ".center(width, '-'))
        format_str = "%14s: %33s"
        print(format_str % ('0 ~ 5',    self.fare[0]))
        print(format_str % ('5 ~ 10',   self.fare[5]))
        print(format_str % ('10 ~ 25',  self.fare[10]))
        print(format_str % ('25 ~ 50',  self.fare[25]))
        print(format_str % ('50 ~ 100', self.fare[50]))
        print(format_str % ('> 100',    self.fare[100]))

        print(''.center(width, '='))
        print("Done, %d/%d records in %.2f seconds by %d processes." %\
            (self.total-self.invalid, self.total, self.elapsed, self.opts.nprocs))

    def run(self):
        self.elapsed = time.time()

        try:
            with self.reader.open(\
                self.opts.color, self.opts.year, self.opts.month, \
                self.opts.src, self.opts.start, self.opts.end) as fin:
                self.path = fin.path
                for line in fin.readlines(): self.search(line)
        except KeyboardInterrupt as e:
            return

        # aggregate boroughs' pickups and dropoffs
        for index, count in self.pickups.items():
            self.borough_pickups[index/10000] += count
            self.borough_pickups[0] += count
        for index, count in self.dropoffs.items():
            self.borough_dropoffs[index/10000] += count
            self.borough_dropoffs[0] += count

        self.elapsed = time.time() - self.elapsed

def start_process(opts):
    p = NYCTaxiStat(opts)
    p.run()
    return p

def start_multiprocess(opts):
    def init():
        _, idx = multiprocessing.current_process().name.split('-')
        multiprocessing.current_process().name = 'mapper%02d' % int(idx)

    db = StatDB(opts)

    tasks = []
    for start, end in TaskManager.cut(opts.start, opts.end, opts.nprocs):
        opts_copy = copy.deepcopy(opts)
        opts_copy.start, opts_copy.end = start, end
        tasks.append(opts_copy)

    try:
        procs = multiprocessing.Pool(processes=opts.nprocs, initializer=init)
        results = procs.map(start_process, tasks)
    except Exception as e:
        fatal(e)
    finally:
        procs.close()
        procs.join()

    master = results[0]
    for res in results:
        logger.info('%r => reducer' % res)
        master += res
    db.append(master)

    if opts.report: master.report()

    return True

def start_worker(opts):
    task_manager = TaskManager(opts)
    if not opts.debug: opts.nprocs = multiprocessing.cpu_count()
    nth_task = 0

    while True:
        task = task_manager.retrieve_task(delete=False)
        if task:
            logger.info('task %d => start' % nth_task)
            opts.color = task.color
            opts.year = task.year
            opts.month = task.month
            opts.start = task.start
            opts.end = task.end
            if start_multiprocess(opts):
                logger.info("task %r => succeeded" % task)
                task_manager.delete_task(task)
            nth_task += 1
        else:
            logger.info("no task, wait for %d seconds..." % opts.sleep)
            time.sleep(opts.sleep)

def main(opts):
    if opts.worker: start_worker(opts)
    else: start_multiprocess(opts)

if __name__ == '__main__':
    main(parse_argv())
