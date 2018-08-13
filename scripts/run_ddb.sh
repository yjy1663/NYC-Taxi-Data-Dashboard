#!/bin/bash

DDB_PATH=$HOME/local/dynamodb
DDB_LOG=$DDB_PATH/dynamodb.log

if [ $# != 1 ]; then
  printf "usage: $0 start|stop\n" 1>&2
  exit 1
fi

if [ $1 = 'start' ]; then
	pid=`pgrep -f DynamoDBLocal.jar`
	if [ -z "$pid" ]; then
		echo "start DynamoDB Local..."
		java -Djava.library.path=$DDB_PATH/DynamoDBLocal_lib \
			-jar $DDB_PATH/DynamoDBLocal.jar -sharedDb >$DDB_LOG 2>&1 &
	else
		echo "DynamoDB Local ($pid) is already running, skip..."
	fi
elif [ $1 = 'stop' ]; then
	echo "stop DynamoDB Local..."
	pkill -f DynamoDBLocal.jar
fi
