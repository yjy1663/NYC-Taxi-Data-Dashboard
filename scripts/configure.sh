#!/bin/bash

# Configure AWS Environment

set -e

echo "Setup AWS credentials..."

# HOWTO:
#   - http://docs.aws.amazon.com/cli/latest/topic/config-vars.html
#   - http://docs.aws.amazon.com/cli/latest/reference/configure/set.html
aws configure
aws configure set default.cli_timestamp_format iso8601
aws configure set default.s3.max_concurrent_requests 20
aws configure set default.s3.max_queue_size 10000
aws configure set default.s3.multipart_threshold 64MB
aws configure set default.s3.multipart_chunksize 16MB
aws configure set default.s3.use_accelerate_endpoint false
aws configure set default.s3.addressing_style path

echo
echo "Test AWS CLI..."
aws iam get-user --output text
aws ec2 describe-account-attributes --output text

echo
echo "Test AWS Boto3 Python APIs..."
python -c "\
import boto3; 
import pprint;
pprint.pprint(boto3.client('iam').get_account_summary())"
