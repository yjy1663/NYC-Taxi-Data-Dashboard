#!/bin/bash

VERSION=8

JAVA_RPM_URL=http://download.oracle.com/otn-pub/java/jdk/8u112-b15/jdk-8u112-linux-x64.rpm
if [ "$VERSION" == "7" ]; then
    JAVA_RPM_URL=http://download.oracle.com/otn-pub/java/jdk/7u79-b15/jdk-7u79-linux-x64.rpm
fi

set -e
set -x

wget --no-cookies --no-check-certificate --header "Cookie: oraclelicense=accept-securebackup-cookie" $JAVA_RPM_URL -O jdk-$VERSION-linux-x64.rpm

rpm -Uvh jdk-$VERSION-linux-x64.rpm

alternatives --install /usr/bin/java java /usr/java/latest/bin/java 2

rm -rf jdk-$VERSION-linux-x64.rpm
