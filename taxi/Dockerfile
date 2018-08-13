# DOCKER-VERSION 1.13.1
FROM amazonlinux

# Install Packages
RUN yum install -y yum-utils
RUN yum-config-manager --enable epel
RUN yum -y update
RUN yum install -y gcc openssl-devel geos-devel python27 python27-test python27-pip python27-devel
RUN `command -v pip` install -U pip
RUN `command -v pip` install -U boto boto3 awscli bokeh paramiko bytebuffer pandas shapely flexx

# Copy Project Files
RUN ["mkdir", "-p", "/tmp/taxi"]
COPY ./* /tmp/taxi/
CMD ["/tmp/taxi/mapred.py", "-w", "-vv"]
