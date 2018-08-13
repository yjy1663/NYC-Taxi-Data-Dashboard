# Copyright 2017, Nan Dun <nan.dun@acm.org>
# All rights reserved.

# Terraform Configurations

variable "aws" {
    type = "map"
    default = {
        region          = ""
        ami             = ""
        key_name        = ""
        route53_zone    = ""
        security_group  = ""
        subnet_id       = ""
        subnet_ids      = ""
        monitoring      = ""
        vpc_id          = ""
        associate_public_ip_address = ""
        iam_instance_profile = ""
        in_ssh_cidr_block = ""
        use_spot_instances = ""
        use_load_balancer = ""
    }
}

variable "terraform" {
    type = "map"
    default = {
        backend = ""
        region  = ""
        bucket  = ""
    }
}

variable "tags" {
    type = "map"
    default = {
        environment = ""
        user        = ""
    }
}

variable "webserver" {
    type = "map"
    default = {
        instance_type        = ""
        count                = ""
        root_volume_type     = ""
        root_volume_size     = ""
        root_volume_delete   = ""
        in_http_cidr_block   = ""
    }
}

variable "mapper" {
    type = "map"
    default = {
        instance_type   = ""
        count           = 0
        spot_price      = ""

        ebs_device_name = ""
        ebs_volume_type = ""
        ebs_volume_size = ""
        ebs_volume_deletion = ""

        use_as_ecs               = ""

        use_asg                  = ""
        asg_instance_types       = ""
        asg_instance_counts      = ""
        asg_termination_policies = ""

        use_spotfeet             = ""
        spot_instance_types      = ""
        spot_instance_counts     = ""
        spot_prices              = ""
        spot_iam_role            = ""
        spot_allocation_strategy = ""
        spot_valid_until         = ""
        spot_availability_zone   = ""
    }
}

variable "reducer" {
    type = "map"
    default = {
        instance_type = ""
        count         = 0
        spot_price    = ""
    }
}

variable "docker" {
    type = "map"
    default = {
        ami           = ""
        instance_type = ""
        count         = 0
        spot_price    = ""
    }
}

provider "aws" {
    region = "${var.aws["region"]}"
}

### EC2 Resources ###

# Web Server
resource "aws_instance" "webserver" {
    ami                         = "${var.aws["ami"]}"
    vpc_security_group_ids      = [ "${aws_security_group.default.id}", "${aws_security_group.webserver.id}" ]
    subnet_id                   = "${var.aws["subnet_id"]}"
    key_name                    = "${var.aws["key_name"]}"
    monitoring                  = "${var.aws["monitoring"]}"
    associate_public_ip_address = "${var.aws["associate_public_ip_address"]}"
    iam_instance_profile        = "${var.aws["iam_instance_profile"]}"

    instance_type               = "${var.webserver["instance_type"]}"
    count                       = "${var.webserver["count"]}"

    root_block_device {
        volume_type = "${var.webserver["root_volume_type"]}"
        volume_size = "${var.webserver["root_volume_size"]}"
        delete_on_termination = "${var.webserver["root_volume_delete"]}"
    }

    tags {
        Environment = "${var.tags["environment"]}"
        User        = "${var.tags["user"]}"
        Group       = "webserver"
        Name        = "webserver${count.index}"
    }
}

# Mapper
resource "aws_instance" "mapper" {
    ami                         = "${var.aws["ami"]}"
    vpc_security_group_ids      = [ "${aws_security_group.default.id}", "${aws_security_group.mapper.id}" ]
    subnet_id                   = "${var.aws["subnet_id"]}"
    key_name                    = "${var.aws["key_name"]}"
    monitoring                  = "${var.aws["monitoring"]}"
    associate_public_ip_address = "${var.aws["associate_public_ip_address"]}"
    iam_instance_profile        = "${var.aws["iam_instance_profile"]}"

    instance_type               = "${var.mapper["instance_type"]}"
    count                       = "${var.aws["use_spot_instances"] ? 0 : var.mapper["count"]}"

    #ebs_block_device {
    #    device_name = "${var.mapper["ebs_device_name"]}"
    #    volume_size = "${var.mapper["ebs_volume_size"]}"
    #    volume_type = "${var.mapper["ebs_volume_type"]}"
    #    delete_on_termination = "${var.mapper["ebs_volume_deletion"]}"
    #}

    tags {
        Environment = "${var.tags["environment"]}"
        User        = "${var.tags["user"]}"
        Group       = "mapper"
        Name        = "mapper${count.index}"
    }
}

resource "aws_spot_instance_request" "mapper" {
    ami                         = "${var.aws["ami"]}"
    vpc_security_group_ids      = [ "${aws_security_group.default.id}", "${aws_security_group.mapper.id}" ]
    subnet_id                   = "${var.aws["subnet_id"]}"
    key_name                    = "${var.aws["key_name"]}"
    monitoring                  = "${var.aws["monitoring"]}"
    associate_public_ip_address = "${var.aws["associate_public_ip_address"]}"
    iam_instance_profile        = "${var.aws["iam_instance_profile"]}"

    instance_type               = "${var.mapper["instance_type"]}"
    count                       = "${var.aws["use_spot_instances"] ? var.mapper["count"] : 0}"
    spot_price                  = "${var.mapper["spot_price"]}"
    wait_for_fulfillment        = true

    ebs_block_device {
        device_name = "${var.mapper["ebs_device_name"]}"
        volume_size = "${var.mapper["ebs_volume_size"]}"
        volume_type = "${var.mapper["ebs_volume_type"]}"
        delete_on_termination = "${var.mapper["ebs_volume_deletion"]}"
    }

    tags {
        Environment = "${var.tags["environment"]}"
        User        = "${var.tags["user"]}"
        Group       = "mapper"
        Name        = "mapper${count.index}"
    }
}

# Auto-scaling and spot instances
resource "aws_launch_configuration" "mapper" {
    image_id = "${var.aws["ami"]}"
    count = "${var.mapper["use_asg"] ? length(split(",", var.mapper["asg_instance_types"])) : 0}"
    name  = "mapper-${element(split(",", var.mapper["asg_instance_types"]), count.index)}"
    instance_type = "${element(split(",", var.mapper["asg_instance_types"]), count.index)}"
    key_name = "${var.aws["key_name"]}"
    security_groups = [ "${aws_security_group.default.id}", "${aws_security_group.mapper.id}" ]
    user_data = "${file("userdata.sh")}"

    enable_monitoring = "${var.aws["monitoring"]}"
    iam_instance_profile = "${var.aws["iam_instance_profile"]}"

    lifecycle {
        create_before_destroy = true
    }
}

resource "aws_autoscaling_group" "mapper" {
    count = "${var.mapper["use_asg"] ? length(split(",", var.mapper["asg_instance_types"])) : 0}"
    name  = "mapper-${element(split(",", var.mapper["asg_instance_types"]), count.index)}"
    min_size = 0
    max_size         = "${element(split(",", var.mapper["asg_instance_counts"]), count.index)}"
    desired_capacity = "${element(split(",", var.mapper["asg_instance_counts"]), count.index)}"
    termination_policies = [ "${split(",", var.mapper["asg_termination_policies"])}" ]
    launch_configuration = "${element(aws_launch_configuration.mapper.*.name, count.index)}"
    vpc_zone_identifier  = [ "${var.aws["subnet_id"]}" ]

    tag {
        key                 = "Environment"
        value               = "${var.tags["environment"]}"
        propagate_at_launch = true
    }

    tag {
        key                 = "User"
        value               = "${var.tags["user"]}"
        propagate_at_launch = true
    }

    tag {
        key                 = "Group"
        value               = "mapper"
        propagate_at_launch = true
    }

    tag {
        key                 = "Name"
        value               = "mapper-asg"
        propagate_at_launch = true
    }
}

resource "aws_spot_fleet_request" "mapper" {
    iam_fleet_role = "${var.mapper["spot_iam_role"]}"
    allocation_strategy = "${var.mapper["spot_allocation_strategy"]}"
    valid_until = "${var.mapper["spot_valid_until"]}"
    count = "${var.mapper["use_spotfleet"] ? length(split(",", var.mapper["spot_instance_types"])) : 0}"
    target_capacity = "${element(split(",", var.mapper["spot_instance_counts"]), count.index)}"
    spot_price = "${element(split(",", var.mapper["spot_prices"]), count.index)}"
    terminate_instances_with_expiration = true
    launch_specification {
        ami = "${var.mapper["use_as_ecs"] ? var.docker["ami"] : var.aws["ami"]}"
        instance_type = "${element(split(",", var.mapper["spot_instance_types"]), count.index)}"
        key_name = "${var.aws["key_name"]}"
        subnet_id = "${var.aws["subnet_id"]}"
        vpc_security_group_ids = [ "${aws_security_group.default.id}","${aws_security_group.mapper.id}" ]
        monitoring = "${var.aws["monitoring"]}"
        iam_instance_profile = "${var.aws["iam_instance_profile"]}"
        weighted_capacity = 1
        spot_price = "${element(split(",", var.mapper["spot_prices"]), count.index)}"
        user_data = "${var.mapper["use_as_ecs"] ? file("userdata_ecs.sh") : file("userdata.sh")}"
    }
}

# Reducer
resource "aws_instance" "reducer" {
    ami                         = "${var.aws["ami"]}"
    vpc_security_group_ids      = [ "${aws_security_group.default.id}", "${aws_security_group.reducer.id}" ]
    subnet_id                   = "${var.aws["subnet_id"]}"
    key_name                    = "${var.aws["key_name"]}"
    monitoring                  = "${var.aws["monitoring"]}"
    associate_public_ip_address = "${var.aws["associate_public_ip_address"]}"
    iam_instance_profile        = "${var.aws["iam_instance_profile"]}"

    instance_type               = "${var.reducer["instance_type"]}"
    count                       = "${var.reducer["count"]}"

    tags {
        Environment = "${var.tags["environment"]}"
        User        = "${var.tags["user"]}"
        Group       = "reducer"
        Name        = "reducer${count.index}"
    }
}

resource "aws_spot_instance_request" "reducer" {
    ami                         = "${var.aws["ami"]}"
    vpc_security_group_ids      = [ "${aws_security_group.default.id}", "${aws_security_group.reducer.id}" ]
    subnet_id                   = "${var.aws["subnet_id"]}"
    key_name                    = "${var.aws["key_name"]}"
    monitoring                  = "${var.aws["monitoring"]}"
    associate_public_ip_address = "${var.aws["associate_public_ip_address"]}"
    iam_instance_profile        = "${var.aws["iam_instance_profile"]}"

    instance_type               = "${var.reducer["instance_type"]}"
    count                       = "${var.aws["use_spot_instances"] ? var.reducer["count"] : 0}"
    spot_price                  = "${var.reducer["spot_price"]}"
    wait_for_fulfillment        = true

    tags {
        Environment = "${var.tags["environment"]}"
        User        = "${var.tags["user"]}"
        Group       = "reducer"
        Name        = "reducer${count.index}"
    }
}

# Docker
resource "aws_instance" "docker" {
    ami                         = "${var.docker["ami"]}"
    vpc_security_group_ids      = [ "${aws_security_group.default.id}", "${aws_security_group.mapper.id}" ]
    subnet_id                   = "${var.aws["subnet_id"]}"
    key_name                    = "${var.aws["key_name"]}"
    monitoring                  = "${var.aws["monitoring"]}"
    associate_public_ip_address = "${var.aws["associate_public_ip_address"]}"
    iam_instance_profile        = "${var.aws["iam_instance_profile"]}"

    instance_type               = "${var.docker["instance_type"]}"
    count                       = "${var.aws["use_spot_instances"] ? 0 : var.docker["count"]}"

    tags {
        Environment = "${var.tags["environment"]}"
        User        = "${var.tags["user"]}"
        Group       = "docker"
        Name        = "docker${count.index}"
    }
}

resource "aws_spot_instance_request" "docker" {
    ami                         = "${var.docker["ami"]}"
    vpc_security_group_ids      = [ "${aws_security_group.default.id}", "${aws_security_group.reducer.id}" ]
    subnet_id                   = "${var.aws["subnet_id"]}"
    key_name                    = "${var.aws["key_name"]}"
    monitoring                  = "${var.aws["monitoring"]}"
    associate_public_ip_address = "${var.aws["associate_public_ip_address"]}"
    iam_instance_profile        = "${var.aws["iam_instance_profile"]}"

    instance_type               = "${var.docker["instance_type"]}"
    count                       = "${var.aws["use_spot_instances"] ? var.docker["count"] : 0}"
    spot_price                  = "${var.docker["spot_price"]}"
    wait_for_fulfillment        = true

    tags {
        Environment = "${var.tags["environment"]}"
        User        = "${var.tags["user"]}"
        Group       = "docker"
        Name        = "docker${count.index}"
    }
}

resource "aws_ecs_task_definition" "mapper" {
    count = "${var.mapper["use_as_ecs"] ? 1 : 0}"
    family = "mapper-ecs-service"
    container_definitions = "${file("mapper.json")}"
}

resource "aws_ecs_service" "mapper" {
    count = "${var.mapper["use_as_ecs"] ? 1 : 0}"
    name = "mapper-ecs-service"
    cluster = "${aws_ecs_cluster.mapper.id}"
    task_definition = "${aws_ecs_task_definition.mapper.arn}"
    desired_count = 1

    placement_strategy {
        type = "binpack"
        field = "cpu"
    }
}

resource "aws_ecs_cluster" "mapper" {
    count = "${var.mapper["use_as_ecs"] ? 1 : 0}"
    ename = "mapper-ecs-cluster"
}

### Security Groups ###
resource "aws_security_group" "default" {
    vpc_id = "${var.aws["vpc_id"]}"
    name = "default-security-group-${var.tags["environment"]}"
    description = "default security group in ${var.tags["environment"]}"

    # Allow all traffic within the default group
    ingress {
        from_port = 0
        to_port = 0
        protocol = "-1"
        self = "true"
    }
    egress {
        from_port = 0
        to_port = 0
        protocol = "-1"
        self = "true"
    }

    # Allow inbound SSH
    ingress {
        from_port = 22
        to_port = 22
        protocol = "tcp"
        cidr_blocks = ["${var.aws["in_ssh_cidr_block"]}"]
    }

    # Allow all outbound
    egress {
        from_port = 0
        to_port = 0
        protocol = "-1"
        cidr_blocks = ["0.0.0.0/0"]
    }

    tags {
        Environment = "${var.tags["environment"]}"
        Name        = "default-security-group-${var.tags["environment"]}"
    }
}

resource "aws_security_group" "webserver" {
    vpc_id = "${var.aws["vpc_id"]}"
    name = "webserver-security-group-${var.tags["environment"]}"
    description = "webserver security group in ${var.tags["environment"]}"

    // allow inbound HTTP
    ingress {
        from_port = 80
        to_port = 80
        protocol = "tcp"
        cidr_blocks = [ "${var.webserver["in_http_cidr_block"]}" ]
    }

    ingress {
        from_port = 5006
        to_port = 5006
        protocol = "tcp"
        cidr_blocks = [ "${var.webserver["in_http_cidr_block"]}" ]
    }

    tags {
        Environment = "${var.tags["environment"]}"
        User        = "${var.tags["user"]}"
        Name = "webserver-security-group-${var.tags["environment"]}"
    }
}

resource "aws_security_group" "mapper" {
    vpc_id = "${var.aws["vpc_id"]}"
    name = "mapper-security-group-${var.tags["environment"]}"
    description = "mapper security group in ${var.tags["environment"]}"

    // allow outbound to SQS
    ingress {
        from_port = 443
        to_port = 443
        protocol = "tcp"
        cidr_blocks = ["${var.mapper["out_sqs_cidr_block"]}"]
    }

    tags {
        Environment = "${var.tags["environment"]}"
        User        = "${var.tags["user"]}"
        Name        = "mapper-security-group-${var.tags["environment"]}"
    }
}

resource "aws_security_group" "reducer" {
    vpc_id = "${var.aws["vpc_id"]}"
    name = "reducer-security-group-${var.tags["environment"]}"
    description = "reducer security group in ${var.tags["environment"]}"

    // allow outbound to S3
    tags {
        Environment = "${var.tags["environment"]}"
        User        = "${var.tags["user"]}"
        Name        = "reducer-security-group-${var.tags["environment"]}"
    }
}

### ELB ###
resource "aws_alb" "web" {
  name = "webserver-alb-${var.tags["environment"]}"
  internal = false
  subnets = ["${split(",", var.aws["subnet_ids"])}"]
  security_groups = [ "${aws_security_group.default.id}", "${aws_security_group.webserver.id}" ]
  enable_deletion_protection = false
  count = "${(var.aws["use_load_balancer"] && var.webserver["count"] > 0) ? 1 : 0}"

  tags {
    Environment = "${var.tags["environment"]}"
    User        = "${var.tags["user"]}"
    Name        = "webserver-alb-${var.tags["environment"]}"
  }
}

resource "aws_alb_target_group" "web" {
  name     = "web${count.index}-target-group"
  port     = 80
  protocol = "HTTP"
  count    = "${var.aws["use_load_balancer"] ? var.webserver["count"] : 0}"
  vpc_id = "${var.aws["vpc_id"]}"
}

resource "aws_alb_target_group_attachment" "web" {
  count            = "${var.aws["use_load_balancer"] ? var.webserver["count"] : 0}"
  target_group_arn = "${element(aws_alb_target_group.web.*.arn, count.index)}"
  target_id        = "${element(aws_instance.webserver.*.id, count.index)}"
  port = 80
}

resource "aws_alb_listener" "web" {
  load_balancer_arn = "${aws_alb.web.id}"
  port              = "80"
  protocol          = "HTTP"
  count             = "${(var.aws["use_load_balancer"] && var.webserver["count"] > 0) ? 1 : 0}"

  default_action {
    target_group_arn = "${element(aws_alb_target_group.web.*.arn, 0)}"
    type             = "forward"
  }
}

resource "aws_alb_listener_rule" "web" {
  listener_arn = "${aws_alb_listener.web.arn}"
  count        = "${var.aws["use_load_balancer"] ? var.webserver["count"] : 0}"
  priority     = "${count.index + 100}"

  action {
    type = "forward"
    target_group_arn = "${element(aws_alb_target_group.web.*.arn, count.index)}"
  }

  condition {
    field = "path-pattern"
    values = ["/webserver${count.index}/*"]
  }
}

### Route 53 Records ###
resource "aws_route53_record" "webserver" {
    zone_id = "${var.aws["route53_zone"]}"
    count   = "${var.webserver["count"]}"
    name    = "${element(aws_instance.webserver.*.tags.Name, count.index)}"
    type    = "A"
    ttl     = "300"
    records = ["${element(aws_instance.webserver.*.public_ip, count.index)}"]
}

resource "aws_route53_record" "web" {
    zone_id = "${var.aws["route53_zone"]}"
    count   = "${(! var.aws["use_load_balancer"] && var.webserver["count"] > 0) ? 1 : 0}"
    name    = "web"
    type    = "CNAME"
    ttl     = "300"
    records = ["${element(aws_route53_record.webserver.*.fqdn, 0)}"]
}

resource "aws_route53_record" "web_elb" {
    zone_id = "${var.aws["route53_zone"]}"
    count   = "${(var.aws["use_load_balancer"] && var.webserver["count"] > 0) ? 1 : 0}"
    name    = "web"
    type    = "CNAME"
    ttl     = "300"
    records = ["${aws_alb.web.dns_name}"]
}

resource "aws_route53_record" "mapper" {
    zone_id = "${var.aws["route53_zone"]}"
    count   = "${var.aws["use_spot_instances"] ? 0 : var.mapper["count"]}"
    name    = "${element(aws_instance.mapper.*.tags.Name, count.index)}"
    type    = "A"
    ttl     = "300"
    records = ["${element(aws_instance.mapper.*.public_ip, count.index)}"]
}

resource "aws_route53_record" "mapper_spot" {
    zone_id = "${var.aws["route53_zone"]}"
    count   = "${var.aws["use_spot_instances"] ? var.mapper["count"] : 0}"
    name    = "${element(aws_spot_instance_request.mapper.*.tags.Name, count.index)}"
    type    = "A"
    ttl     = "300"
    records = ["${element(aws_spot_instance_request.mapper.*.public_ip, count.index)}"]
}

resource "aws_route53_record" "reducer" {
    zone_id = "${var.aws["route53_zone"]}"
    count   = "${var.aws["use_spot_instances"] ? 0 : var.reducer["count"]}"
    name    = "${element(aws_instance.reducer.*.tags.Name, count.index)}"
    type    = "A"
    ttl     = "300"
    records = ["${element(aws_instance.reducer.*.public_ip, count.index)}"]
}

resource "aws_route53_record" "reducer_spot" {
    zone_id = "${var.aws["route53_zone"]}"
    count   = "${var.aws["use_spot_instances"] ? var.reducer["count"] : 0}"
    name    = "${element(aws_spot_instance_request.reducer.*.tags.Name, count.index)}"
    type    = "A"
    ttl     = "300"
    records = ["${element(aws_spot_instance_request.reducer.*.public_ip, count.index)}"]
}

resource "aws_route53_record" "docker" {
    zone_id = "${var.aws["route53_zone"]}"
    count   = "${var.aws["use_spot_instances"] ? 0 : var.docker["count"]}"
    name    = "${element(aws_instance.docker.*.tags.Name, count.index)}"
    type    = "A"
    ttl     = "300"
    records = ["${element(aws_instance.docker.*.public_ip, count.index)}"]
}

resource "aws_route53_record" "docker_spot" {
    zone_id = "${var.aws["route53_zone"]}"
    count   = "${var.aws["use_spot_instances"] ? var.docker["count"] : 0}"
    name    = "${element(aws_spot_instance_request.docker.*.tags.Name, count.index)}"
    type    = "A"
    ttl     = "300"
    records = ["${element(aws_spot_instance_request.docker.*.public_ip, count.index)}"]
}

### Output ###
output "webservers"  {
    value = ["${aws_route53_record.webserver.*.fqdn}"]
}

output "mappers" {
    value = ["${aws_route53_record.mapper.*.fqdn}", "${aws_route53_record.mapper_spot.*.fqdn}"]
}

output "reducers" {
    value = ["${aws_route53_record.reducer.*.fqdn}", "${aws_route53_record.reducer_spot.*.fqdn}"]
}

output "dockers" {
    value = ["${aws_route53_record.docker.*.fqdn}", "${aws_route53_record.docker_spot.*.fqdn}"]
}
