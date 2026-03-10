"""
AWS Scanner - Scans EC2, EBS, S3 resources
Uses boto3 (AWS SDK for Python)
"""

import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from datetime import datetime, timezone
from typing import Optional


class AWSScanner:
    def __init__(self, region: str = "us-east-1", profile: Optional[str] = None):
        """
        Initialize AWS scanner.
        
        Args:
            region: AWS region to scan (default: us-east-1)
            profile: AWS CLI profile name (optional, uses default if not set)
        
        Setup:
            Run `aws configure` in terminal to set up credentials, OR
            Set env vars: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
        """
        self.region = region
        session = boto3.Session(profile_name=profile, region_name=region)
        self.ec2 = session.client("ec2", region_name=region)
        self.s3 = session.client("s3")
        self.cloudwatch = session.client("cloudwatch", region_name=region)

    def scan_all(self) -> dict:
        """Run full infrastructure scan."""
        return {
            "ec2_instances": self.scan_ec2(),
            "ebs_volumes": self.scan_ebs(),
            "s3_buckets": self.scan_s3(),
        }

    def scan_ec2(self) -> list:
        """
        Scan all EC2 instances and return enriched metadata.
        Includes CPU utilization from CloudWatch for waste detection.
        """
        try:
            response = self.ec2.describe_instances()
            instances = []

            for reservation in response["Reservations"]:
                for inst in reservation["Instances"]:
                    instance_id = inst["InstanceId"]
                    state = inst["State"]["Name"]
                    instance_type = inst["InstanceType"]
                    launch_time = inst["LaunchTime"].isoformat()

                    # Get name tag if exists
                    name = ""
                    for tag in inst.get("Tags", []):
                        if tag["Key"] == "Name":
                            name = tag["Value"]

                    # Get average CPU for last 7 days (for waste detection)
                    avg_cpu = self._get_avg_cpu(instance_id) if state == "running" else None

                    # Estimate monthly cost (rough estimate by instance type)
                    estimated_cost = self._estimate_ec2_cost(instance_type)

                    instances.append({
                        "id": instance_id,
                        "name": name,
                        "type": instance_type,
                        "state": state,
                        "region": self.region,
                        "launch_time": launch_time,
                        "avg_cpu_7d": avg_cpu,
                        "estimated_monthly_cost_usd": estimated_cost,
                    })

            return instances

        except (NoCredentialsError, ClientError) as e:
            print(f"[Scanner] EC2 scan error: {e}")
            return []

    def scan_ebs(self) -> list:
        """
        Scan EBS volumes. Flags unattached volumes as waste candidates.
        """
        try:
            response = self.ec2.describe_volumes()
            volumes = []

            for vol in response["Volumes"]:
                attached = len(vol.get("Attachments", [])) > 0
                size_gb = vol["Size"]
                vol_type = vol["VolumeType"]
                create_time = vol["CreateTime"].isoformat()

                # Estimate cost: gp2 = $0.10/GB/month, gp3 = $0.08/GB/month
                cost_per_gb = 0.10 if vol_type == "gp2" else 0.08
                estimated_cost = round(size_gb * cost_per_gb, 2)

                volumes.append({
                    "id": vol["VolumeId"],
                    "size_gb": size_gb,
                    "type": vol_type,
                    "state": vol["State"],
                    "attached": attached,
                    "attachments": [a["InstanceId"] for a in vol.get("Attachments", [])],
                    "created_at": create_time,
                    "estimated_monthly_cost_usd": estimated_cost,
                })

            return volumes

        except (NoCredentialsError, ClientError) as e:
            print(f"[Scanner] EBS scan error: {e}")
            return []

    def scan_s3(self) -> list:
        """
        Scan S3 buckets. Returns bucket list with region and creation date.
        """
        try:
            response = self.s3.list_buckets()
            buckets = []

            for bucket in response.get("Buckets", []):
                bucket_name = bucket["Name"]
                creation_date = bucket["CreationDate"].isoformat()

                # Try to get bucket location
                try:
                    loc = self.s3.get_bucket_location(Bucket=bucket_name)
                    location = loc["LocationConstraint"] or "us-east-1"
                except ClientError:
                    location = "unknown"

                buckets.append({
                    "name": bucket_name,
                    "created_at": creation_date,
                    "region": location,
                })

            return buckets

        except (NoCredentialsError, ClientError) as e:
            print(f"[Scanner] S3 scan error: {e}")
            return []

    def _get_avg_cpu(self, instance_id: str) -> Optional[float]:
        """Get average CPU utilization over the last 7 days from CloudWatch."""
        try:
            from datetime import timedelta
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=7)

            response = self.cloudwatch.get_metric_statistics(
                Namespace="AWS/EC2",
                MetricName="CPUUtilization",
                Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
                StartTime=start,
                EndTime=end,
                Period=86400,  # 1-day granularity
                Statistics=["Average"],
            )

            datapoints = response.get("Datapoints", [])
            if not datapoints:
                return None

            avg = sum(d["Average"] for d in datapoints) / len(datapoints)
            return round(avg, 2)

        except Exception:
            return None

    def _estimate_ec2_cost(self, instance_type: str) -> float:
        """
        Rough hourly → monthly cost estimate for common instance types.
        Replace with AWS Pricing API for production accuracy.
        """
        # On-demand Linux prices (us-east-1), multiplied by 730 hours/month
        HOURLY_PRICES = {
            "t2.micro": 0.0116,
            "t2.small": 0.023,
            "t2.medium": 0.0464,
            "t2.large": 0.0928,
            "t3.micro": 0.0104,
            "t3.small": 0.0208,
            "t3.medium": 0.0416,
            "t3.large": 0.0832,
            "t3.xlarge": 0.1664,
            "m5.large": 0.096,
            "m5.xlarge": 0.192,
            "m5.2xlarge": 0.384,
            "c5.large": 0.085,
            "c5.xlarge": 0.17,
            "r5.large": 0.126,
        }
        hourly = HOURLY_PRICES.get(instance_type, 0.05)  # default to $0.05
        return round(hourly * 730, 2)
