#
# Makefile for Infrastructure Management
#

# Configure variables
DEFAULT_AWS_REGION := us-west-2
DEFAULT_AWS_BUCKET := dun-us-west-2
DEFAULT_AWS_PROFILE := default
DEFAULT_AWS_ACCOUNT := 026979347307

######## DO NOT EDIT BELOW THIS UNLESS YOU KNOW WHAT YOU ARE DOING ########
DK := docker

# Read input given by user, otherwise use default value
read_input = $(shell read -p $(1) REPLY; \
	if [ -z "$${REPLY}" ]; then echo $(2); else echo $${REPLY}; fi)

all: help
help:
	@echo "usage: make <action>"
	@echo "Available actions are:"
	@echo "  login  ECS login"
	@echo "  build  build Docker image"
	@echo "  push   push image"
	@echo "  pull   show pull command"
	@echo "  task   generate task definition"
	@echo "  debug  debugging run"

.PHONY: login
login:
	@eval `aws ecr get-login --region $(DEFAULT_AWS_REGION)`
	@echo Login valid until `date -j -v12H` # date --date='12 hours'

.PHONY: build
build:
	$(DK) build -t taxi .

.PHONY: push
push:
	$(DK) tag taxi:latest $(DEFAULT_AWS_ACCOUNT).dkr.ecr.$(DEFAULT_AWS_REGION).amazonaws.com/taxi:latest
	$(DK) push $(DEFAULT_AWS_ACCOUNT).dkr.ecr.$(DEFAULT_AWS_REGION).amazonaws.com/taxi:latest

.PHONY: pull
pull:
	@echo "Copy and paste following commands to Docker instance"
	@echo "\`aws ecr get-login --region $(DEFAULT_AWS_REGION)\`"
	@echo $(DK) pull $(DEFAULT_AWS_ACCOUNT).dkr.ecr.$(DEFAULT_AWS_REGION).amazonaws.com/taxi:latest

.PHONY: debug
debug:
	@echo "Starting DynamoDB Local..."
	cd ../scripts/ && ./run_ddb.sh start
	@echo "Debugging entire website..."
	BOKEH_LOG_LEVEL=debug BOKEH_PY_LOG_LEVEL=debug bokeh serve ../taxi --args --debug -vv

.PHONY: task
task:
	@aws ecs register-task-definition --generate-cli-skeleton
