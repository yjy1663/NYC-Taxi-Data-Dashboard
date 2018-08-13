#!/bin/bash -v

SETUP_SCRIPT=dun-us-west-2/aws/setup.sh
SETUP_USER=ec2-user

aws s3 cp s3://${SETUP_SCRIPT} /home/${SETUP_USER}/setup.sh
chown ${SETUP_USER}:${SETUP_USER} /home/${SETUP_USER}/setup.sh
chmod 700 /home/${SETUP_USER}/setup.sh
su - ${SETUP_USER} -c "/home/${SETUP_USER}/setup.sh"
