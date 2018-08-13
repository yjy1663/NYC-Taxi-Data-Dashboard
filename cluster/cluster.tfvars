# AWS Settings
aws = {
  region         = "us-west-2"
  key_name       = "dun"                                # TODO
  ami            = "ami-8fad2eef"                       # TODO
  subnet_id      = "subnet-dd26e594"
  subnet_ids     = "subnet-dd26e594,subnet-7fa51618"    # TODO
  route53_zone   = "Z2GWJPXVAX0OOB"                     # TODO
  monitoring     = "false"
  vpc_id         = "vpc-51a73336"                       # TODO
  associate_public_ip_address = "true"
  in_ssh_cidr_block    = "0.0.0.0/0"
  iam_instance_profile = "Taxi-EC2-Instance-Profile"    # TODO
  use_spot_instances   = false
  use_load_balancer    = false
}

# Terraform Settings
terraform = {
  backend = "s3"
  region  = "us-west-2"
  bucket  = "dun-us-west-2" # TODO
}

# Tags
tags = {
  environment = "demo"
  user        = "dun"       # TODO
}

# Web Server Settings
webserver = {
  instance_type        = "t2.micro"
  count                = "1"
  root_volume_type     = "gp2"
  root_volume_size     = "8"
  in_http_cidr_block   = "0.0.0.0/0"
}

# Mapper Settings
mapper = {
  instance_type        = "c4.8xlarge"
  count                = "0"
  spot_price           = "1.5"
  ebs_device_name      = "/dev/sdb"
  ebs_volume_size      = 2
  ebs_volume_type      = "gp2"
  ebs_volume_deletion  = "true"
  out_sqs_cidr_block   = "0.0.0.0/0"

  use_as_ecs           = true
  use_asg              = false
  asg_instance_types   = "c4.large,c4.2xlarge,c4.4xlarge"
  asg_instance_counts  = "1,0,0"
  asg_termination_policies = "ClosestToNextInstanceHour,OldestInstance"

  use_spotfleet        = true
  spot_instance_types  = "c3.large"
  spot_instance_counts = "1"
  spot_prices          = "0.5"
  spot_iam_role = "arn:aws:iam::026979347307:role/MapperSpotFleetRole"  # TODO
  spot_allocation_strategy = "lowestPrice"
  spot_valid_until = "2018-01-01T00:00:00Z"
  spot_availability_zone = "us-west-2a"
}

# Reducer Settings
reducer = {
  instance_type        = "c4.8xlarge"
  count                = "0"
  spot_price           = "1.5"
}

# Docker Settings
docker = {
  ami                  = "ami-12b23172"
  instance_type        = "t2.micro"
  count                = "1"
  spot_price           = "1.0"
}
