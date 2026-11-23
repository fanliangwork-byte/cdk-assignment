
from aws_cdk import (
    Stack,
    CfnOutput,
    Duration,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_rds as rds,
    aws_elasticloadbalancingv2 as elbv2,
    aws_elasticloadbalancingv2_targets as targets,
)
from constructs import Construct


class CdkLabWebServerStack(Stack):

    def __init__(self, scope: Construct, construct_id: str,
                 cdk_lab_vpc: ec2.Vpc, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # Security groups
        web_sg = ec2.SecurityGroup(
            self, "WebSG", vpc=cdk_lab_vpc
        )
        web_sg.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(80)
        )

        db_sg = ec2.SecurityGroup(
            self, "DatabaseSG", vpc=cdk_lab_vpc
        )
        db_sg.add_ingress_rule(
            web_sg, ec2.Port.tcp(3306)
        )

        # Web servers
        public_subnets = cdk_lab_vpc.public_subnets
        web_servers = []

        for i in range(2):
            server = ec2.Instance(
                self, f"WebServer{i + 1}",
                vpc=cdk_lab_vpc,
                instance_type=ec2.InstanceType("t3.micro"),
                machine_image=ec2.MachineImage.latest_amazon_linux2023(),
                security_group=web_sg,
                vpc_subnets=ec2.SubnetSelection(
                    subnets=[public_subnets[i]]
                )
            )

            server.user_data.add_commands(
                "dnf install -y httpd",
                f"echo 'Web Server {i + 1}' > /var/www/html/index.html",
                "systemctl enable --now httpd"
            )

            web_servers.append(server)

        # MySQL database
        database = rds.DatabaseInstance(
            self, "MySQLDatabase",
            engine=rds.DatabaseInstanceEngine.mysql(
                version=rds.MysqlEngineVersion.VER_8_0_46
            ),
            vpc=cdk_lab_vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            instance_type=ec2.InstanceType("t3.micro"),
            allocated_storage=20,
            storage_encrypted=True,
            multi_az=False,
            publicly_accessible=False,
            security_groups=[db_sg],
            credentials=rds.Credentials.from_generated_secret("admin"),
            backup_retention=Duration.days(0),
            removal_policy=RemovalPolicy.DESTROY,
            deletion_protection=False,
            delete_automated_backups=True
        )

        # Load balancer
        alb = elbv2.ApplicationLoadBalancer(
            self, "WebALB",
            vpc=cdk_lab_vpc,
            internet_facing=True
        )

        alb.connections.allow_to(web_sg, ec2.Port.tcp(80))

        listener = alb.add_listener(
            "HTTPListener", port=80, open=True
        )

        listener.add_targets(
            "WebTargets",
            port=80,
            targets=[targets.InstanceTarget(server) for server in web_servers],
            health_check=elbv2.HealthCheck(path="/")
        )

        CfnOutput(
            self, "LoadBalancerURL",
            value=f"http://{alb.load_balancer_dns_name}"
        )

        CfnOutput(
            self, "DatabaseEndpoint",
            value=database.db_instance_endpoint_address
        )
