"""
AWS Scanner - Scans EC2, EBS, S3, RDS, Elastic IPs, Load Balancers, Lambda
Uses boto3 (AWS SDK for Python)
"""

import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from datetime import datetime, timezone, timedelta
from typing import Optional


class AWSScanner:
    def __init__(self, region: str = "us-east-1", profile: Optional[str] = None):
        self.region = region
        session = boto3.Session(profile_name=profile, region_name=region)
        self.ec2 = session.client("ec2", region_name=region)
        self.s3 = session.client("s3")
        self.cloudwatch = session.client("cloudwatch", region_name=region)
        self.rds = session.client("rds", region_name=region)
        self.elbv2 = session.client("elbv2", region_name=region)
        self.lambda_ = session.client("lambda", region_name=region)

    def scan_all(self) -> dict:
        """Run full infrastructure scan across all supported services."""
        return {
            "ec2_instances": self.scan_ec2(),
            "ebs_volumes": self.scan_ebs(),
            "s3_buckets": self.scan_s3(),
            "rds_instances": self.scan_rds(),
            "elastic_ips": self.scan_elastic_ips(),
            "load_balancers": self.scan_load_balancers(),
            "lambda_functions": self.scan_lambda(),
        }

    def scan_ec2(self) -> list:
        try:
            response = self.ec2.describe_instances()
            instances = []
            for reservation in response["Reservations"]:
                for inst in reservation["Instances"]:
                    instance_id = inst["InstanceId"]
                    state = inst["State"]["Name"]
                    instance_type = inst["InstanceType"]
                    name = next((t["Value"] for t in inst.get(
                        "Tags", []) if t["Key"] == "Name"), "")
                    avg_cpu = self._get_avg_cpu(
                        instance_id) if state == "running" else None
                    instances.append({
                        "id": instance_id, "name": name, "type": instance_type,
                        "state": state, "region": self.region,
                        "launch_time": inst["LaunchTime"].isoformat(),
                        "avg_cpu_7d": avg_cpu,
                        "estimated_monthly_cost_usd": self._estimate_ec2_cost(instance_type),
                    })
            return instances
        except (NoCredentialsError, ClientError) as e:
            print(f"[Scanner] EC2 error: {e}")
            return []

    def scan_ebs(self) -> list:
        try:
            volumes = []
            for vol in self.ec2.describe_volumes()["Volumes"]:
                attached = len(vol.get("Attachments", [])) > 0
                size_gb = vol["Size"]
                vol_type = vol["VolumeType"]
                cost_per_gb = 0.10 if vol_type == "gp2" else 0.08
                volumes.append({
                    "id": vol["VolumeId"], "size_gb": size_gb, "type": vol_type,
                    "state": vol["State"], "attached": attached,
                    "attachments": [a["InstanceId"] for a in vol.get("Attachments", [])],
                    "created_at": vol["CreateTime"].isoformat(),
                    "estimated_monthly_cost_usd": round(size_gb * cost_per_gb, 2),
                })
            return volumes
        except (NoCredentialsError, ClientError) as e:
            print(f"[Scanner] EBS error: {e}")
            return []

    def scan_s3(self) -> list:
        try:
            buckets = []
            for bucket in self.s3.list_buckets().get("Buckets", []):
                try:
                    loc = self.s3.get_bucket_location(Bucket=bucket["Name"])
                    location = loc["LocationConstraint"] or "us-east-1"
                except ClientError:
                    location = "unknown"
                buckets.append({
                    "name": bucket["Name"],
                    "created_at": bucket["CreationDate"].isoformat(),
                    "region": location,
                })
            return buckets
        except (NoCredentialsError, ClientError) as e:
            print(f"[Scanner] S3 error: {e}")
            return []

    def scan_rds(self) -> list:
        """Scan RDS instances. Checks for idle/stopped databases."""
        try:
            instances = []
            for db in self.rds.describe_db_instances()["DBInstances"]:
                db_id = db["DBInstanceIdentifier"]
                status = db["DBInstanceStatus"]
                avg_connections = self._get_rds_connections(
                    db_id) if status == "available" else None
                instances.append({
                    "id": db_id,
                    "class": db["DBInstanceClass"],
                    "engine": db["Engine"],
                    "status": status,
                    "multi_az": db.get("MultiAZ", False),
                    "storage_gb": db.get("AllocatedStorage", 0),
                    "avg_connections_7d": avg_connections,
                    "estimated_monthly_cost_usd": self._estimate_rds_cost(db["DBInstanceClass"]),
                })
            return instances
        except (NoCredentialsError, ClientError) as e:
            print(f"[Scanner] RDS error: {e}")
            return []

    def scan_elastic_ips(self) -> list:
        """Scan Elastic IPs. Unattached EIPs cost ~$3.65/mo each."""
        try:
            eips = []
            for addr in self.ec2.describe_addresses()["Addresses"]:
                attached = "AssociationId" in addr
                eips.append({
                    "id": addr.get("AllocationId", ""),
                    "public_ip": addr.get("PublicIp", ""),
                    "attached": attached,
                    "instance_id": addr.get("InstanceId", None),
                    "estimated_monthly_cost_usd": 0.0 if attached else 3.65,
                })
            return eips
        except (NoCredentialsError, ClientError) as e:
            print(f"[Scanner] Elastic IP error: {e}")
            return []

    def scan_load_balancers(self) -> list:
        """Scan ALBs/NLBs. Idle LBs cost ~$16/mo with zero traffic."""
        try:
            balancers = []
            for lb in self.elbv2.describe_load_balancers()["LoadBalancers"]:
                lb_arn = lb["LoadBalancerArn"]
                lb_type = lb["Type"]
                state = lb["State"]["Code"]
                avg_requests = self._get_alb_requests(
                    lb_arn, lb_type) if state == "active" else None
                balancers.append({
                    "name": lb["LoadBalancerName"],
                    "arn": lb_arn,
                    "type": lb_type,
                    "state": state,
                    "dns": lb["DNSName"],
                    "avg_requests_7d": avg_requests,
                    "estimated_monthly_cost_usd": 16.0,
                })
            return balancers
        except (NoCredentialsError, ClientError) as e:
            print(f"[Scanner] Load Balancer error: {e}")
            return []

    def scan_lambda(self) -> list:
        """Scan Lambda functions. Flags dead (0 invocations) and broken (high errors) functions."""
        try:
            functions = []
            paginator = self.lambda_.get_paginator("list_functions")
            for page in paginator.paginate():
                for fn in page["Functions"]:
                    fn_name = fn["FunctionName"]
                    invocations = self._get_lambda_invocations(fn_name)
                    error_rate = self._get_lambda_error_rate(fn_name)
                    functions.append({
                        "name": fn_name,
                        "runtime": fn.get("Runtime", "unknown"),
                        "memory_mb": fn.get("MemorySize", 128),
                        "timeout_seconds": fn.get("Timeout", 3),
                        "last_modified": fn.get("LastModified", ""),
                        "code_size_bytes": fn.get("CodeSize", 0),
                        "invocations_30d": invocations,
                        "error_rate_percent": error_rate,
                    })
            return functions
        except (NoCredentialsError, ClientError) as e:
            print(f"[Scanner] Lambda error: {e}")
            return []

    # ── CloudWatch Helpers ────────────────────────────────────────────────────

    def _get_avg_cpu(self, instance_id: str) -> Optional[float]:
        try:
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=7)
            response = self.cloudwatch.get_metric_statistics(
                Namespace="AWS/EC2", MetricName="CPUUtilization",
                Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
                StartTime=start, EndTime=end, Period=86400, Statistics=["Average"],
            )
            dp = response.get("Datapoints", [])
            return round(sum(d["Average"] for d in dp) / len(dp), 2) if dp else None
        except Exception:
            return None

    def _get_rds_connections(self, db_id: str) -> Optional[float]:
        try:
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=7)
            response = self.cloudwatch.get_metric_statistics(
                Namespace="AWS/RDS", MetricName="DatabaseConnections",
                Dimensions=[{"Name": "DBInstanceIdentifier", "Value": db_id}],
                StartTime=start, EndTime=end, Period=86400, Statistics=["Average"],
            )
            dp = response.get("Datapoints", [])
            return round(sum(d["Average"] for d in dp) / len(dp), 2) if dp else 0.0
        except Exception:
            return None

    def _get_alb_requests(self, lb_arn: str, lb_type: str) -> Optional[float]:
        try:
            metric = "RequestCount" if lb_type == "application" else "ActiveFlowCount"
            ns = "AWS/ApplicationELB" if lb_type == "application" else "AWS/NetworkELB"
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=7)
            response = self.cloudwatch.get_metric_statistics(
                Namespace=ns, MetricName=metric,
                Dimensions=[{"Name": "LoadBalancer",
                             "Value": lb_arn.split(":")[-1]}],
                StartTime=start, EndTime=end, Period=86400, Statistics=["Sum"],
            )
            dp = response.get("Datapoints", [])
            return round(sum(d["Sum"] for d in dp) / len(dp), 0) if dp else 0.0
        except Exception:
            return None

    def _get_lambda_invocations(self, fn_name: str) -> Optional[int]:
        try:
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=30)
            response = self.cloudwatch.get_metric_statistics(
                Namespace="AWS/Lambda", MetricName="Invocations",
                Dimensions=[{"Name": "FunctionName", "Value": fn_name}],
                StartTime=start, EndTime=end, Period=2592000, Statistics=["Sum"],
            )
            dp = response.get("Datapoints", [])
            return int(dp[0]["Sum"]) if dp else 0
        except Exception:
            return None

    def _get_lambda_error_rate(self, fn_name: str) -> Optional[float]:
        try:
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=30)

            def get_sum(metric):
                r = self.cloudwatch.get_metric_statistics(
                    Namespace="AWS/Lambda", MetricName=metric,
                    Dimensions=[{"Name": "FunctionName", "Value": fn_name}],
                    StartTime=start, EndTime=end, Period=2592000, Statistics=["Sum"],
                )
                dp = r.get("Datapoints", [])
                return dp[0]["Sum"] if dp else 0
            invocations = get_sum("Invocations")
            errors = get_sum("Errors")
            if invocations == 0:
                return 0.0
            return round((errors / invocations) * 100, 1)
        except Exception:
            return None

    # ── Cost Estimators ───────────────────────────────────────────────────────

    def _estimate_ec2_cost(self, instance_type: str) -> float:
        prices = {
            "t2.micro": 0.0116, "t2.small": 0.023, "t2.medium": 0.0464, "t2.large": 0.0928,
            "t3.micro": 0.0104, "t3.small": 0.0208, "t3.medium": 0.0416,
            "t3.large": 0.0832, "t3.xlarge": 0.1664,
            "m5.large": 0.096, "m5.xlarge": 0.192, "m5.2xlarge": 0.384,
            "c5.large": 0.085, "c5.xlarge": 0.17, "r5.large": 0.126,
        }
        return round(prices.get(instance_type, 0.05) * 730, 2)

    def _estimate_rds_cost(self, db_class: str) -> float:
        prices = {
            "db.t3.micro": 0.017, "db.t3.small": 0.034, "db.t3.medium": 0.068,
            "db.t3.large": 0.136, "db.m5.large": 0.171, "db.m5.xlarge": 0.342,
            "db.r5.large": 0.24, "db.r5.xlarge": 0.48,
        }
        return round(prices.get(db_class, 0.10) * 730, 2)
