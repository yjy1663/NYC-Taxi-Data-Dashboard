#!/usr/bin/env python

import argparse
import ConfigParser
import random
import sys
import time

import boto3
import boto3.session
import botocore
import paramiko

from collections import defaultdict
from paramiko.ssh_exception import *
from test import pystone

def parse_argv():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument("--config", metavar='PATH',
        type=str, default='ec2_benchmark.cfg', help="config file")

    parser.add_argument("--profile", metavar="NAME",
        type=str, default='t_series', help='benchmark profile')

    parser.add_argument("--wait", action="store_true",
        help='benchmark profile')

    parser.add_argument("--retry", metavar='NUM', type=int,
        default=3, help='retry number')

    parser.add_argument("--dryrun", help="dry run, nothing will be executed",
        action="store_true")

    parser.add_argument("--verbose", metavar='INT', type=int, default=0,
        help="output verbosity")

    parser.add_argument("--clean", dest='clean', action='store_true',
        default=False, help="clean up benchmark environment")

    args = parser.parse_args()
    return args

class Benchmark:
    def __init__(self, opts):
        self.opts = opts
        self.parse_config(self.opts.config, self.opts.profile)

        self.session = boto3.session.Session()
        self.ec2 = self.session.resource('ec2', region_name=self.config['region'])
        self.s3 = self.session.resource('s3', region_name=self.config['region'])

        self.tags = defaultdict()
        self.tags['environment'] = 'benchmark-%s' % self.opts.profile

        self.ssh = defaultdict()

    def verbose(self, msg, level=0):
        if self.opts.verbose >= level:
            sys.stdout.write(msg)
            sys.stdout.flush()

    def parse_config(self, cfg, profile):
        self.verbose("Loading configurations from %s with profile %s...\n" % \
            (cfg, profile), 0)
        self.config = defaultdict(list)
        parser = ConfigParser.RawConfigParser()
        parser.read(cfg)

        # Load default configurations
        self.config = parser.defaults()
        if not parser.has_section(profile):
            self.verbose("warning: no profile %s found in %s" % (profile, cfg), 0)
            return

        # Load profile cofigurations
        for name, value in parser.items(profile):
            if name == 'instance_types' or name == 'tests':
                self.config[name] = value.split(',')
            else:
                try:
                    self.config[name] = int(value)
                except ValueError:
                    pass

            if self.opts.verbose >= 1:
                print "  %s: %s = %s" % (profile, name, self.config[name])

    def get_instances(self, state='running', instance_types=''):
        instances = self.ec2.instances.filter(
            Filters=[{'Name': 'instance-state-name', 'Values': ['running']},
                     {'Name': 'tag:environment', 'Values': [self.tags['environment']]}])
        if instance_types:
            instance_types = instance_types.split(',')
            instances = [instance for instance in instances
                if instance.instance_type in instance_types]
        return instances

    def create_instance(self, instance_type, count):
        self.verbose("  create: %s " % instance_type + \
            "(ami=%(ami)s, count=%(count)s, key=%(key)s)..." % self.config, 1)

        launched_instances = defaultdict(list)
        try:
            instances = self.ec2.create_instances(DryRun=self.opts.dryrun,
                ImageId=self.config['ami'],
                InstanceType=instance_type,
                MinCount=count, MaxCount=count,
                KeyName=self.config['key'],
                SubnetId=self.config['subnet_id'],
                BlockDeviceMappings=[
                        {
                            'DeviceName': '/dev/xvda',
                            'Ebs': {
                                'VolumeSize': 16,
                                'DeleteOnTermination': True,
                                'VolumeType': 'gp2',
                            },
                        }],
                )
            for instance in instances:
                instance.create_tags(DryRun=self.opts.dryrun,
                    Tags=[{'Key': 'environment', 'Value': self.tags['environment']}])
            launched_instances[instance_type].extend(instances)
            self.verbose("succeeded.\n", 1)
        except botocore.exceptions.ClientError as e:
            if e.response['Error'].get('Code') == 'DryRunOperation':
                self.verbose("\n", 1)
            else:
                raise
        return launched_instances

    def terminate_instance(self, instance):
        self.verbose("  terminate: %s (id=%s)..." % \
            (instance.instance_type, instance.instance_id), 1)

        try:
            instance.terminate(DryRun=self.opts.dryrun)
            self.verbose("succeeded.\n", 1)
        except botocore.exceptions.ClientError as e:
            if e.response['Error'].get('Code') == 'DryRunOperation':
                self.verbose("\n", 1)
            else:
                raise

    def launch(self):
        self.verbose("Launching total %s instances...\n" % \
            (self.config['count'] * len(self.config['instance_types'])), 0)

        for instance_type in self.config['instance_types']:
            running_instances = self.get_instances(instance_types=instance_type)
            n_running_instances = len(list(running_instances))
            count = self.config['count'] - n_running_instances
            if n_running_instances > 0:
                msg = "  %s: %s instances already running, " % (instance_type, n_running_instances)
                if count == 0:
                    self.verbose(msg + "do nothing.\n", 1)
                elif count > 0:
                    self.verbose(msg + "create %s more.\n" % count, 1)
                    self.create_instance(instance_type, count)
                else:
                    self.verbose(msg + "terminate %s.\n" % -count, 1)
                    for instance in random.sample(list(running_instances), -count):
                        self.terminate_instance(instance)
            elif count > 0:
                launched_instances = self.create_instance(instance_type, count)
                if self.opts.wait:
                    for instance_type, instances in launched_instances.items():
                        for instance in instances:
                            self.verbose("  wait %s: %s until running...\n" % \
                                (instance_type, instance.instance_id), 1)
                            instance.wait_until_running()

    def configure(self):
        self.verbose("Configuring running instances...\n")
        session = botocore.session.get_session()
        access_key = session.get_credentials().access_key
        secret_key = session.get_credentials().secret_key

        retry = 0
        for instance in self.get_instances():
            client = paramiko.SSHClient()
            client.load_system_host_keys()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            while retry < self.opts.retry:
                try:
                    client.connect(instance.public_ip_address, port=22, username='ec2-user',
                        key_filename='/Users/dun/.ssh/id_aws.pem')
                    break
                except (BadHostKeyException, AuthenticationException,
                        NoValidConnectionsError, SSHException, socket.error) as e:
                     self.verbose("  failed to connect %s, retry...\n" % instance.public_ip_address, 0)
                     time.sleep(10)
                     retry += 1
            self.ssh[instance.instance_id] = client
            channel = client.invoke_shell()
            stdin = channel.makefile('wb')
            stdout = channel.makefile('rb')

            self.verbose("  %s: installing packages...\n" % instance.instance_id, 1)

            stdin.write('''
sudo yum-config-manager --enable epel
sudo yum install -y iperf3 fio python27-test
sudo `which pip` install -U pip
sudo `which pip` install -U boto boto3 awscli
mkdir -p ~/.aws
exit
''')
            self.verbose(stdout.read(), 2)

            sftp = client.open_sftp()
            aws_config = sftp.file("/home/ec2-user/.aws/config", "w+", -1)
            aws_config.write('''
[default]
region = us-west-2
aws_access_key_id = %s
aws_secret_access_key = %s
s3 =
  max_concurrent_requests = 20
  max_queue_size = 10000
  multipart_threshold = 64MB
  multipart_chunksize = 16MB
  addressing_style = path
''' % (access_key, secret_key))
# TODO: use_accelerate_endpoint
            aws_config.flush()
            aws_config.close()

    def do(self):
        self.verbose("Benchmarking...\n")
        for instance in self.get_instances():
            ssh = self.ssh[instance.instance_id]

            self.verbose("-" * 90 + '\n')

            # CPU
            if 'cpu' in self.config['tests']:
                self.verbose("  %s: evaluating CPU...\n" % instance.instance_type)
                stdin, stdout, stderr = ssh.exec_command(
                    "python -c 'from test import pystone; pystone.main(1000000)'")
                self.verbose(stdout.read(), 2)

            # EBS
            if 'ebs' in self.config['tests']:
                self.verbose("  %s: evaluating EBS...\n" % instance.instance_type)
                stdin, stdout, stderr = ssh.exec_command(
                    "sudo fio --directory=/ \
--name fio_test_file --direct=1 --rw=write --bs=1m --size=128M \
--numjobs=1 --time_based --runtime=10 --group_reporting --norandommap")
                self.verbose(stdout.read(), 2)

                stdin, stdout, stderr = ssh.exec_command(
                    "sudo fio --directory=/ \
--name fio_test_file --direct=1 --rw=read --bs=1m --size=128M \
--numjobs=1 --time_based --runtime=10 --group_reporting --norandommap")
                self.verbose(stdout.read(), 2)

            # S3
            if 's3' in self.config['tests']:
                bucket_name = "benchmark-%s" % instance.instance_id
                self.s3.create_bucket(Bucket=bucket_name,
                    CreateBucketConfiguration = \
                        {'LocationConstraint': self.config['region']})
                self.verbose("  %s: evaluating S3...\n" % instance.instance_type)
                stdin, stdout, stderr = ssh.exec_command(
                    "time ls /fio* | xargs -P 4 -I '{}' aws s3 cp '{}' s3://%s/" % bucket_name)
                self.verbose(stdout.read(), 2)
                self.verbose(stderr.read(), 2)

                # Homework: iPerf

    def clean(self):
        for instance in self.get_instances():
            self.terminate_instance(instance)

            bucket = self.s3.Bucket("benchmark-%s" % instance.instance_id)
            self.verbose("  delete bucket %s...\n" % bucket.name)
            for key in bucket.objects.all(): key.delete()
            bucket.delete()

    def run(self):
        if self.opts.clean:
            self.clean()
            return

        self.launch()
        self.configure()
        self.do()
        if self.opts.dryrun:
            print "\nDryrun, nothing was executed."
        else:
            print "\nDone."

def main():
    b = Benchmark(parse_argv())
    b.run()

if __name__ == '__main__':
    main()
