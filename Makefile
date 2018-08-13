#
# Makefile for BitTiger AWS Data Processing Infrastructure Lecture
# Copyright 2017 Nan Dun <nan.dun@acm.org>
#

# Configure variables
PREFIX := $(HOME)/local

# Don't modify unless you know what you are doing
PATH := $(PREFIX)/bin:$(PATH)

all: help
help:
	@echo "usage: make <action>"
	@echo "Available actions are:"
	@echo "  prepare      install prerequisite software packages"
	@echo "  configure    configure AWS environment"
	@echo "  bill         show AWS billing"
	@echo "  benchmark    benchmark AWS resources"
	@echo "  clean        clean project"
	@echo "  version      show tools version"

.PHONY: prepare
prepare:
	@cd scripts/ && PREFIX=$(PREFIX) ./install_packages.sh

.PHONY: configure
configure:
	@cd scripts/ && ./configure.sh

.PHONY: bill
bill:
	@cd scripts/ && ./bill.py

.PHONY: benchmark
benchmark:
	@echo "Bechmarking AWS resources..."
	@cd scripts/ && ./ec2_benchmark.py --wait --verbose 2

.PHONY: clean
clean:
	@cd scripts/ && ./ec2_benchmark.py --clean --verbose 2
	@cd scripts/ && ./run_ddb.sh stop
	@echo "Clean the project..."
	rm -rf *.pyc */*.pyc */*.db

.PHONY: version
version:
	@python --version
	@git --version
	@make -version | head -n 1
	@terraform -v | head -n 1
	@packer version | head -n 1
	@ansible --version | head -n 1
	@echo boto3 v`python -c 'import boto3; print boto3.__version__'`
	@aws --version
	@echo Branch `git rev-parse --abbrev-ref HEAD` on `git config --get remote.origin.url` : `git rev-parse HEAD`
