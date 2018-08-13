#!/usr/bin/env python

# Get AWS billing
# http://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CW_Support_For_AWS.html

import boto3
import datetime

# HOWTO: billing only available in us-east-1 (N. Virginia)
session = boto3.session.Session(region_name='us-east-1')
client = session.client('cloudwatch')
cloudwatch = session.resource('cloudwatch')

one_day = datetime.timedelta(days=1)
today = datetime.datetime.today()
if today.day == 1: today += one_day
yesterday = today - one_day

def get_charge(service='Total'):
    dimensions = [{'Name': 'Currency', 'Value': 'USD'}]
    if service != 'Total':
        dimensions.append({'Name': 'ServiceName', 'Value': service})
    metric = cloudwatch.Metric('AWS/Billing','EstimatedCharges')
    stat = metric.get_statistics(
        StartTime=yesterday,
        EndTime=today,
        Period=86400,
        Statistics=['Average'],
        Dimensions=dimensions
    )

    if len(stat['Datapoints']):
        return stat['Datapoints'][0]['Average']
    return 0.0

field_width = 5
def get_services():
    global field_width
    services = []
    metrics = client.list_metrics(
        Dimensions=[{'Name':'Currency', 'Value': 'USD'}])['Metrics']
    for metric in metrics:
        if metric['Dimensions'][0]['Name'] == 'ServiceName':
            service = metric['Dimensions'][0]['Value']
            field_width = max(len(service), field_width)
            services.append(service)
    services.append('Total')
    return services

print (today.strftime('%B %Y')).center(field_width + 18, '-')
for service in get_services():
    charge = get_charge(service)
    if charge != 0:
        print service.ljust(field_width, ' '), ' $%.3f' % charge
