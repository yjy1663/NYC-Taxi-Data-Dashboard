#!/bin/bash

# Build an AMI using Packer

set -e

AMI_SPEC=${1:-"ami.json"}

AMI="ami-f173cc91"
NAME="BitTiger-Amazon-Linux-AMI-2017.01.1-x86_64-HVM-SSD"
ARGS="-var source_ami_id=${AMI} -var ami_name_prefix=${NAME} ${AMI_SPEC}"
echo "Build customized Amazon Linux AMI from ${AMI} ..."
packer validate ${ARGS}
packer build ${ARGS}

AMI="ami-022b9262"
NAME="BitTiger-Amazon-ECS-AMI-2016.09.f-x86_64-HVM-GP2"
ARGS="-var source_ami_id=${AMI} -var ami_name_prefix=${NAME} ${AMI_SPEC}"
echo "Build customized Amazon Linux AMI from ${AMI} ..."
packer validate ${ARGS}
packer build ${ARGS}
