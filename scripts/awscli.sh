#!/bin/bash

# AWS CLI Crash Examples

REGION_NAME=${REGION_NAME:-"us-west-2"}
INSTANCE_TYPE=${INSTANCE_TYPE:-"t2.micro"}
VPC_NAME=${VPC_NAME:-"main"}

# Don't modify unless you know what you are doing
set -e
#set -x

if [ $# != 1 ]; then
  printf "usage: $0 choice\n" 1>&2
  exit 1
fi

CHOICE=$1
CMD=''

# Functions
function find_vpc() {
  aws ec2 describe-vpcs \
    --filters \
	  Name=tag:Name,Values=${VPC_NAME} \
    --query "Vpcs[].VpcId" \
	--output text
}

function find_subnet() {
  local subnet_name=$1
  aws ec2 describe-subnets \
    --filters \
	  Name=vpc-id,Values=$(find_vpc) \
	  Name=tag:Name,Values=${subnet_name} \
    --query "Subnets[].SubnetId" \
	--output text
}

function list_amis() {
  local region=$1
  local name=$2
  aws ec2 describe-images \
    --region "${region}" \
    --filters \
      Name=owner-alias,Values=amazon \
      Name=name,Values="$name" \
      Name=architecture,Values=x86_64 \
      Name=virtualization-type,Values=hvm \
      Name=root-device-type,Values=ebs \
      Name=block-device-mapping.volume-type,Values=gp2 \
   --query "Images[*].['$region',ImageId,Name,Description]" \
   --output text
}

function wait_instance_state() {
  local instance_id=$1
  local required_state=$2
  local instance_state=$(aws ec2 describe-instances --instance-ids $instance_id \
	  --query 'Reservations[].Instances[].State.Name')
  while [ "$instances_state" != "$required_state" ]; do
  	sleep 3
    instance_state=$(aws ec2 describe-instances --instance-ids $instance_id \
	  --query 'Reservations[].Instances[].State.Name')
  done
}

function get_security_group() {
  local group_name=$1
  aws ec2 describe-security-groups \
    --region "$REGION_NAME" \
    --filters Name=group-name,Values=default \
	          Name=vpc-id,Values=$(find_vpc) \
	--query SecurityGroups[].GroupId \
    --output text
}

function get_keypair() {
  aws ec2 describe-key-pairs --query KeyPairs[].KeyName --output text
}

function launch_instance() {
  local image_id=$(list_amis $REGION_NAME amzn-ami-hvm-* | sort -rk 3,3 | grep -v rc | head -n 1 | cut -f 2)
  local subnet_id=$(find_subnet public)
  local security_groups=$(get_security_group default)
  local instance_id=$(aws ec2 run-instances \
    --associate-public-ip-address \
    --image-id "$image_id" \
    --key-name "$(get_keypair)" \
	--subnet-id "${subnet_id}" \
    --security-group-ids "$security_groups" \
    --instance-type "$INSTANCE_TYPE" \
    --output text \
    --query "Instances[0].InstanceId")

  aws ec2 create-tags \
    --resources "$instance_id" \
    --tags Key=environment,Value=demo

  printf "wait %s: %s until running...\n" $INSTANCE_TYPE $instance_id
  # wait_instance_state "$instance_id" "running"
  aws ec2 wait instance-running --instance-ids "$instance_id"

  local instance_hostname=$(aws ec2 describe-instances \
    --instance-ids "$instance_id" \
    --output text \
    --query Reservations[].Instances[0].PublicDnsName)

  printf "wait for SSH ready to connect...\n"
  local retry=5
  while [ $retry -gt 0 ]; do
    ssh -o StrictHostKeyChecking=no $instance_hostname
	if [ $? -eq 0 ]; then
	  echo "succeeded."
	  break
	fi
	echo "retry..."
	((retry-=1))
  done
}

function terminate_instances() {
  local instance_ids=$(aws ec2 describe-instances \
    --filters Name="instance-state-name",Values="running" \
	--query "Reservations[].Instances[0].InstanceId" \
	--output text)

  aws ec2 terminate-instances --instance-ids ${instance_ids}
}

# Run selected example
[ 1 = $CHOICE ] && CMD="aws ec2 describe-regions"

[ 2 = $CHOICE ] && CMD="aws ec2 describe-regions --output text"

[ 3 = $CHOICE ] && CMD="aws ec2 describe-regions --output table"

[ 4 = $CHOICE ] && CMD="aws ec2 describe-regions --query Regions[].RegionName"

[ 5 = $CHOICE ] && CMD="aws ec2 describe-regions --query Regions[0].RegionName"

[ 6 = $CHOICE ] && CMD="list_amis $REGION_NAME amzn-ami-hvm-*"

[ 7 = $CHOICE ] && CMD="launch_instance"

[ 8 = $CHOICE ] && CMD="terminate_instances"

[ 9 = $CHOICE ] && CMD="find_vpc"

[ 10 = $CHOICE ] && CMD="aws cloudwatch list-metrics"

[ 11 = $CHOICE ] && CMD="aws cloudwatch list-metrics --region us-east-1"

[ 12 = $CHOICE ] && CMD="aws cloudwatch list-metrics --region us-east-1 --metric-name EstimatedCharges"

[ 13 = $CHOICE ] && CMD="aws cloudwatch get-metric-statistics --namespace AWS/EC2 --metric-name CPUUtilization --dimensions Name=InstanceId,Value=i-123456 --start-time '2017-02-10T00:00:00Z' --end-time '2014-11-12T00:00:00Z' --period 300 --statistics {'Average', 'Maximum'}"

[ 14 = $CHOICE ] && CMD="aws ec2 request-spot-fleet --spot-fleet-request-config file://spotfleet.json"

# Use JSON to pass template
#  --cli-input-json
#  --generate-cli-skeleton

# http://docs.aws.amazon.com/cli/latest/reference/s3api/get-object.html

if [ -z "$CMD" ]; then
  printf "error: no such choice: %s\n" "$CHOICE" 1>&2
  exit 1
fi

printf "%02d> %s\n" "$CHOICE" "$CMD" 1>&2
eval $CMD
