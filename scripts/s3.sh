#!/bin/bash

# S3 CLI Crash Examples


if [ $# != 1 ]; then
  printf "usage: $0 choice\n" 1>&2
  exit 1
fi

CHOICE=$1
CMD=''

AWS_USER_ID=$(aws iam list-users --query Users[].UserId --output text | tr '[:upper:]' '[:lower:]')
SRC_BUCKET="s3-cli-demo-${AWS_USER_ID}-src"
DST_BUCKET="s3-cli-demo-${AWS_USER_ID}-dst"

# Functions
function list_s3_endpoints() {
  local bucket_name=$2
  local try=$2
  while [ $try -gt 0 ]; do
    dig +noall +answer $bucket_name.s3.amazonaws.com
	sleep 1
  done
}

# list S3 endpoints
[ 1 = $CHOICE ] && CMD="list_s3_endpoints aws-nyc-taxi-data 5"

# create buckets
[ 2 = $CHOICE ] && CMD="\
aws s3 mb s3://${SRC_BUCKET}; \
aws s3 mb s3://${DST_BUCKET}"

# delete buckets
[ 3 = $CHOICE ] && CMD="\
aws s3 rb s3://${SRC_BUCKET}; \
aws s3 rb s3://${DST_BUCKET}"

# empty buckets
[ 4 = $CHOICE ] && CMD="\
aws s3 rm s3://${SRC_BUCKET} --recursive; \
aws s3 rm s3://${DST_BUCKET} --recursive"

# list buckets
[ 5 = $CHOICE ] && CMD="\
aws s3 ls s3://${SRC_BUCKET} --recursive; \
aws s3 ls s3://${DST_BUCKET} --recursive"

# copy a local directory to bucket
[ 6 = $CHOICE ] && CMD="\
aws s3 cp ../ s3://${SRC_BUCKET} --recursive"

# copy local directory with prefix to bucket
[ 7 = $CHOICE ] && CMD="\
aws s3 cp ../ s3://${SRC_BUCKET} --recursive --exclude '*' --include 'scripts/*'"

# copy from one bucket to another
[ 8 = $CHOICE ] && CMD="\
aws s3 cp s3://${SRC_BUCKET} s3://${DST_BUCKET} --recursive"

# download a file to stdout
[ 9 = $CHOICE ] && CMD="\
aws s3 cp s3://${SRC_BUCKET}/scripts/s3.sh -"

if [ -z "$CMD" ]; then
  printf "error: no such choice: %s\n" "$CHOICE" 1>&2
  exit 1
fi

printf "%02d> %s\n" "$CHOICE" "$CMD" 1>&2
eval $CMD
