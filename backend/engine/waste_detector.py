"""
Waste Detection Engine
Applies rules to scanned AWS resources and flags waste.
Covers: EC2, EBS, RDS, Elastic IPs, Load Balancers, Lambda
"""

from typing import List, Dict, Any


class WasteDetector:
    CPU_IDLE_THRESHOLD = 5.0
    CPU_UNDERUSED_THRESHOLD = 20.0
    RDS_IDLE_CONNECTIONS = 1.0
    LB_IDLE_REQUESTS = 100.0
    LAMBDA_DEAD_DAYS = 30

    def detect(self, resources: dict) -> List[Dict[str, Any]]:
        """Run all detection rules and return list of issues sorted by savings."""
        issues = []
        issues += self._check_ec2(resources.get("ec2_instances", []))
        issues += self._check_ebs(resources.get("ebs_volumes", []))
        issues += self._check_rds(resources.get("rds_instances", []))
        issues += self._check_elastic_ips(resources.get("elastic_ips", []))
        issues += self._check_load_balancers(resources.get("load_balancers", []))
        issues += self._check_lambda(resources.get("lambda_functions", []))
        issues.sort(key=lambda x: x.get("savings_usd", 0), reverse=True)
        return issues

    def _check_ec2(self, instances: list) -> list:
        issues = []
        for inst in instances:
            iid = inst["id"]
            name = inst.get("name") or iid
            state = inst.get("state")
            cpu = inst.get("avg_cpu_7d")
            cost = inst.get("estimated_monthly_cost_usd", 0)
            itype = inst.get("type", "")

            if state == "stopped":
                issues.append({
                    "resource_type": "EC2", "resource_id": iid, "resource_name": name,
                    "issue": "Stopped instance",
                    "detail": f"{name} ({itype}) is stopped but still incurs EBS storage charges.",
                    "severity": "medium",
                    "recommendation": "Terminate if no longer needed, or create an AMI and terminate.",
                    "savings_usd": round(cost * 0.15, 2), "action": "terminate_or_snapshot",
                })
            elif state == "running" and cpu is not None and cpu < self.CPU_IDLE_THRESHOLD:
                issues.append({
                    "resource_type": "EC2", "resource_id": iid, "resource_name": name,
                    "issue": "Idle instance",
                    "detail": f"{name} ({itype}) has {cpu}% avg CPU over 7 days.",
                    "severity": "high",
                    "recommendation": "Stop or terminate this instance.",
                    "savings_usd": cost, "action": "stop_or_terminate",
                })
            elif state == "running" and cpu is not None and cpu < self.CPU_UNDERUSED_THRESHOLD:
                downgrade = self._suggest_ec2_downgrade(itype)
                savings = round(cost * 0.4, 2)
                issues.append({
                    "resource_type": "EC2", "resource_id": iid, "resource_name": name,
                    "issue": "Oversized instance",
                    "detail": f"{name} ({itype}) has {cpu}% avg CPU over 7 days.",
                    "severity": "medium",
                    "recommendation": f"Downgrade to {downgrade}. Save ~${savings}/month.",
                    "savings_usd": savings, "action": "resize_instance", "suggested_type": downgrade,
                })
        return issues

    def _check_ebs(self, volumes: list) -> list:
        issues = []
        for vol in volumes:
            vid = vol["id"]
            size = vol.get("size_gb", 0)
            vtype = vol.get("type", "gp2")
            cost = vol.get("estimated_monthly_cost_usd", 0)

            if not vol.get("attached", True):
                issues.append({
                    "resource_type": "EBS", "resource_id": vid,
                    "issue": "Unattached volume",
                    "detail": f"{vid} ({size} GB, {vtype}) is not attached to any instance.",
                    "severity": "high",
                    "recommendation": "Delete or snapshot this orphaned volume.",
                    "savings_usd": cost, "action": "delete_or_snapshot",
                })
            elif vtype == "gp2":
                savings = round(cost - size * 0.08, 2)
                if savings > 0:
                    issues.append({
                        "resource_type": "EBS", "resource_id": vid,
                        "issue": "Outdated volume type (gp2)",
                        "detail": f"{vid} ({size} GB) uses gp2. gp3 is 20% cheaper with better IOPS.",
                        "severity": "low",
                        "recommendation": f"Migrate to gp3. Save ~${savings}/month.",
                        "savings_usd": savings, "action": "modify_volume_type", "suggested_type": "gp3",
                    })
        return issues

    def _check_rds(self, instances: list) -> list:
        issues = []
        for db in instances:
            db_id = db["id"]
            db_class = db.get("class", "")
            status = db.get("status")
            cost = db.get("estimated_monthly_cost_usd", 0)
            connections = db.get("avg_connections_7d")
            multi_az = db.get("multi_az", False)

            if status == "stopped":
                issues.append({
                    "resource_type": "RDS", "resource_id": db_id,
                    "issue": "Stopped RDS instance",
                    "detail": f"{db_id} ({db_class}) is stopped. Storage charges still apply.",
                    "severity": "medium",
                    "recommendation": "Delete and take a final snapshot if data must be retained.",
                    "savings_usd": round(cost * 0.20, 2), "action": "delete_rds",
                })
            elif connections is not None and connections <= self.RDS_IDLE_CONNECTIONS:
                issues.append({
                    "resource_type": "RDS", "resource_id": db_id,
                    "issue": "Idle database",
                    "detail": f"{db_id} ({db_class}) has avg {connections} connections over 7 days.",
                    "severity": "high",
                    "recommendation": "Stop or delete this database. Take a snapshot first.",
                    "savings_usd": cost, "action": "stop_or_delete_rds",
                })

            # Single-AZ production warning (not a cost issue, but a reliability one)
            if not multi_az and status == "available":
                issues.append({
                    "resource_type": "RDS", "resource_id": db_id,
                    "issue": "Single-AZ deployment",
                    "detail": f"{db_id} is Single-AZ. A failure will cause downtime.",
                    "severity": "low",
                    "recommendation": "Enable Multi-AZ for production workloads.",
                    "savings_usd": 0, "action": "enable_multi_az",
                })
        return issues

    def _check_elastic_ips(self, eips: list) -> list:
        issues = []
        for eip in eips:
            if not eip.get("attached", True):
                issues.append({
                    "resource_type": "Elastic IP",
                    "resource_id": eip["id"],
                    "issue": "Unattached Elastic IP",
                    "detail": f"EIP {eip['public_ip']} is not associated with any instance.",
                    "severity": "high",
                    "recommendation": "Release this Elastic IP to stop charges.",
                    "savings_usd": 3.65, "action": "release_eip",
                })
        return issues

    def _check_load_balancers(self, balancers: list) -> list:
        issues = []
        for lb in balancers:
            requests = lb.get("avg_requests_7d")
            cost = lb.get("estimated_monthly_cost_usd", 16.0)

            if requests is not None and requests <= self.LB_IDLE_REQUESTS:
                issues.append({
                    "resource_type": "Load Balancer",
                    "resource_id": lb["name"],
                    "issue": "Idle load balancer",
                    "detail": f"{lb['name']} ({lb['type']}) has avg {requests} requests/day over 7 days.",
                    "severity": "high",
                    "recommendation": "Delete this load balancer if no longer routing traffic.",
                    "savings_usd": cost, "action": "delete_load_balancer",
                })
        return issues

    def _check_lambda(self, functions: list) -> list:
        issues = []
        for fn in functions:
            name = fn["name"]
            invocations = fn.get("invocations_30d")
            error_rate = fn.get("error_rate_percent")

            if invocations == 0:
                issues.append({
                    "resource_type": "Lambda", "resource_id": name,
                    "issue": "Dead Lambda function",
                    "detail": f"{name} had 0 invocations in the last 30 days.",
                    "severity": "medium",
                    "recommendation": "Delete this function if it's no longer needed.",
                    "savings_usd": 0, "action": "delete_lambda",
                })
            elif error_rate is not None and error_rate > 10:
                issues.append({
                    "resource_type": "Lambda", "resource_id": name,
                    "issue": "High error rate",
                    "detail": f"{name} has a {error_rate}% error rate over 30 days.",
                    "severity": "high",
                    "recommendation": "Investigate CloudWatch logs and fix the underlying errors.",
                    "savings_usd": 0, "action": "fix_lambda_errors",
                })
        return issues

    def _suggest_ec2_downgrade(self, instance_type: str) -> str:
        DOWNGRADE_MAP = {
            "t3.xlarge": "t3.large", "t3.large": "t3.medium",
            "t3.medium": "t3.small", "t3.small": "t3.micro",
            "t2.xlarge": "t2.large", "t2.large": "t2.medium",
            "t2.medium": "t2.small", "t2.small": "t2.micro",
            "m5.2xlarge": "m5.xlarge", "m5.xlarge": "m5.large",
            "c5.xlarge": "c5.large", "r5.xlarge": "r5.large",
        }
        return DOWNGRADE_MAP.get(instance_type, f"smaller {instance_type.split('.')[0]}")