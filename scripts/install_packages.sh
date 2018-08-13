#!/bin/bash

# Install Required Packages on Your Unix/Linux System

PREFIX=${PREFIX:-${HOME}/local}

PYTHON_PACKAGES=${PYTHON_PACKAGES:-"awscli aws-shell boto boto3 bokeh paramiko \
shapely bytebuffer jmespath-terminal ansible flexx docker docker-py docker-compose"}

PACKER_VERSION=${PACKER_VERSION:-0.12.2}
TERRAFORM_VERSION=${TERRAFORM_VERSION:-0.8.7}

# Install Python Packages
echo "Installing Python Packages: ${PYTHON_PACKAGES}..."
sudo pip install -U ${PYTHON_PACKAGES}

# Install Packer
echo "Installing Packer..."
PACKER_URL="https://releases.hashicorp.com/packer/${PACKER_VERSION}"
PACKER_BIN=$(command -v packer)

if [ ! -z "${PACKER_BIN}" ]; then
    echo "Packer $(packer -v) already installed at ${PACKER_BIN}, skip..."
else
	echo "Installing Packer..."
    curl ${PACKER_URL}/packer_${PACKER_VERSION}_darwin_amd64.zip -o packer.zip
	mkdir -p ${PREFIX}/bin
    unzip packer.zip -d ${PREFIX}/bin
    rm -rf packer.zip
fi

# Install Terraform
echo "Installing Terraform..."
TERRAFORM_URL="https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}"
TERRAFORM_BIN=$(command -v terraform)
if [ ! -z "${TERRAFORM_BIN}" ]; then
    echo "$(terraform -v) already installed at ${TERRAFORM_BIN}, skip..."
else
	echo "Installing Terraform..."
    curl ${TERRAFORM_URL}/terraform_${TERRAFORM_VERSION}_darwin_amd64.zip -o terraform.zip
	mkdir -p ${PREFIX}/bin
    unzip terraform.zip -d ${PREFIX}/bin
    rm -rf terraform.zip
fi

# Install DynamoDB Local
# http://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBLocal.html
echo "Installing DynamoDB Local..."
DDB_URL="https://s3-us-west-2.amazonaws.com/dynamodb-local/dynamodb_local_latest.tar.gz"
DDB_PATH=$PREFIX/dynamodb
if [ ! -d "$DDB_PATH" ]; then
	mkdir -p $DDB_PATH
	curl $DDB_URL | tar zxv -C $DDB_PATH
fi

# Install ECS CLI
echo "Installing ECS CLI..."
ECSCLI_URL="https://s3.amazonaws.com/amazon-ecs-cli/ecs-cli-darwin-amd64-latest"
ECSCLI_BIN=$(command -v ecs-cli)
if [ ! -z "${ECSCLI_BIN}" ]; then
    echo "$(ecs-cli -v) already installed at ${ECSCLI_BIN}, skip..."
else
	curl ${ECSCLI_URL} -o ${PREFIX}/bin/ecs-cli
	chmod +x ${PREFIX}/bin/ecs-cli
fi

# Install Docker
echo "Installing Docker..."
DOCKER_URL="https://download.docker.com/mac/stable/Docker.dmg"
DOCKER_BIN=$(command -v docker)
if [ ! -z "${DOCKER_BIN}" ]; then
	echo "$(docker -v) already installed at ${DOCKER_BIN}, skip..."
else
	curl ${DOCKER_URL} -o Docker.dmg
	open Docker.dmg
	echo "Don't forget to run Docker.app from Launchpad."
fi
