#!/bin/bash
# All right reserved.

set -e

ENVIRONMENT=demo
OWNER=dun
NAME=mapper-spot
BUCKET=dun-us-west-2/aws
KEY=id_bitbucket_deploy
REPO=git@bitbucket.org:bittiger-aws/aws.git

## Instance Metadata
METADATA_URL="http://169.254.169.254"
INSTANCE_ID=`curl -s ${METADATA_URL}/latest/meta-data/instance-id`
REGION=`curl -s ${METADATA_URL}/latest/dynamic/instance-identity/document | grep region | awk -F\" '{print $4}'`
retries=0
until [ $retries -ge 5 ]; do
    LIFECYCLE=`aws --region=${REGION} ec2 describe-instances --instance-ids ${INSTANCE_ID} --query 'Reservations[*].Instances[*].[InstanceLifecycle]' --output text` && break
    ((retries++))
    sleep $((5 + RANDOM % 6))
done

echo "Executing as `whoami`"

## Self-tagging instance
TAGS=""
TAGS+="Key=Environment,Value=${ENVIRONMENT} \
       Key=User,Value=${OWNER} \
	   Key=Name,Value=${NAME}"
if [ x${LIFECYCLE} = xspot ]; then
    echo "Tagging spot instance ${INSTANCE_ID}..."
    retries=0
    until [ $retries -ge 5 ]; do
        aws --region=${REGION} ec2 create-tags --resources $INSTANCE_ID --tags ${TAGS} && break
        ((retries++))
        sleep $((5 + RANDOM % 6))
    done
fi

echo "Installing packages..."
sudo yum install -y git geos-devel
sudo /usr/local/bin/pip install -U pandas shapely

echo "Cloning repository..."
aws s3 cp s3://${BUCKET}/${KEY} ~/.ssh/id_bitbucket_deploy
chmod 400 ~/.ssh/id_bitbucket_deploy
eval `ssh-agent`
ssh-add ~/.ssh/id_bitbucket_deploy
echo -e "Host bitbucket.org\n  StrictHostKeyChecking no\n" >> ~/.ssh/config
chmod 600 ~/.ssh/config
git clone ${REPO} ~/aws

sleep 30

/home/ec2-user/aws/taxi/mapred.py -w -vv &> /home/ec2-user/aws/taxi/mapred-`date +%Y-%m-%d-%H-%M-%S`.log &
