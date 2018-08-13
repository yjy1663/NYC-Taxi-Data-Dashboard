#
# Makefile for Infrastructure Management
#
# Nan Dun <nan.dun@acm.org>
#

# Configure variables
DEFAULT_AWS_REGION := us-west-2
DEFAULT_AWS_BUCKET := dun-us-west-2
DEFAULT_AWS_PROFILE := default
TF_CONFIG_VARS := cluster.tfvars

USERDATA_BUCKET := dun-us-west-2/aws
USERDATA_SSHKEY := ~/.ssh/id_bitbucket_deploy

######## DO NOT EDIT BELOW THIS UNLESS YOU KNOW WHAT YOU ARE DOING ########
TF := terraform
TF_FLAGS := -var-file=$(TF_CONFIG_VARS)
USER ?= `whoami`
AS  := ansible
ASP := ansible-playbook

# Read input given by user, otherwise use default value
read_input = $(shell read -p $(1) REPLY; \
	if [ -z "$${REPLY}" ]; then echo $(2); else echo $${REPLY}; fi)

all: help
help:
	@echo "usage: make <action>"
	@echo "Available actions are:"
	@echo "  ami         build customized AMI"
	@echo "  userdata    upload userdata"
	@echo "  plan        create infrastructure plan"
	@echo "  show        show infrasctructure plan"
	@echo "  apply       apply infrastructure plan"
	@echo "  deploy      deploy ansible playbook"
	@echo "  destroy     destroy infrastructure"

.PHONY: ami
ami:
	./build_ami.sh

.PHONY: userdata
userdata:
	aws s3 cp setup.sh s3://$(USERDATA_BUCKET)/setup.sh
	aws s3 cp $(USERDATA_SSHKEY) s3://$(USERDATA_BUCKET)

.PHONY: config
config:
	@echo "Configuring Terraform..."
	$(eval __bucket := $(call read_input, \
		"AWS S3 bucket (default: $(DEFAULT_AWS_BUCKET)): ",\
		$(DEFAULT_AWS_BUCKET)))
	$(eval __region := $(call read_input, \
		"AWS region (default: $(DEFAULT_AWS_REGION)): ",\
		$(DEFAULT_AWS_REGION)))
	$(eval __profile := $(call read_input, \
		"AWS profile (default: $(DEFAULT_AWS_PROFILE)): ",\
		$(DEFAULT_AWS_PROFILE)))
	@$(TF) remote config -backend=s3 \
		-backend-config="bucket=$(__bucket)" \
		-backend-config="region=$(__region)" \
		-backend-config="profile=$(__profile)" \
		-backend-config="key=cluster.tfstate"

.PHONY: plan
plan:
	@echo "Generating infrastructure plan..."
	$(TF) validate
	$(TF) remote pull
	$(TF) plan $(TF_FLAGS)

.PHONY: show
show:
	@echo "Showing infrastructure plan..."
	$(TF) show

.PHONY: apply
apply:
	@echo "Applying infrastructure plan..."
	$(TF) remote pull
	$(TF) apply $(TF_FLAGS)
	$(TF) remote push
	@echo "Creating Ansible inventory..."
	$(TF) output -json | ./json2ini.py --keywords webservers,mappers,reducers,dockers -o hosts

.PHONY: deploy
deploy:
	@echo "Deploying Ansible playbook..."
	$(ASP) deploy.yaml

.PHONY: destroy
destroy:
	@echo "Destroying infrastructure..."
	$(TF) destroy $(TF_FLAGS)
