"""
Waste Detection Engine - Enhanced
Covers underutilization, unused resources, AND overutilization.

Categories:
  UNDERUSED  → idle/oversized (save money)
  UNUSED     → orphaned/stopped (delete it)
  OVERUSED   → undersized/overwhelmed (prevent outages)
"""

from typing import List, Dict, Any


class WasteDetector:
    # Underutilization thresholds
    CPU_IDLE_THRESHOLD = 5.0    # % CPU — idle
    CPU_UNDERUSED_THRESHOLD = 20.0   # % CPU — oversized
    RDS_IDLE_CONNECTIONS = 1.0    # avg connections — idle DB

    # Overutilization thresholds
    CPU_HIGH_THRESHOLD = 80.0   # % CPU — undersized
    CPU_CRITICAL_THRESHOLD = 90.0   # % CPU — critical, crash risk
    RDS_HIGH_CONNECTIONS = 80.0   # % of max connections — overwhelmed
    LAMBDA_HIGH_ERROR_RATE = 10.0   # % errors — broken
    LAMBDA_TIMEOUT_THRESHOLD = 80.0   # % of timeout used — needs more memory

    # Max connections per RDS class (approximate)
    RDS_MAX_CONNECTIONS = {
        "db.t3.micro":   66,
        "db.t3.small":   150,
        "db.t3.medium":  312,
        "db.t3.large":   648,
        "db.m5.large":   823,
        "db.m5.xlarge":  1645,
        "db.r5.large":   1258,
        "db.r5.xlarge":  2516,
    }

    def detect(self, resources: dict) -> List[Dict[str, Any]]:
        """Run all detection rules. Returns issues sorted by severity then savings."""
        issues = []
        issues += self._check_ec2(resources.get("ec2_instances", []))
        issues += self._check_ebs(resources.get("ebs_volumes", []))
        issues += self._check_rds(resources.get("rds_instances", []))
        issues += self._check_elastic_ips(resources.get("elastic_ips", []))
        issues += self._check_load_balancers(
            resources.get("load_balancers", []))
        issues += self._check_lambda(resources.get("lambda_functions", []))

        # Sort: critical first, then high, then by savings
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        issues.sort(key=lambda x: (
            severity_order.get(x.get("severity", "low"), 3),
            -x.get("savings_usd", 0)
        ))
        return issues

    # ── EC2 ──────────────────────────────────────────────────────────────────

    def _check_ec2(self, instances: list) -> list:
        issues = []
        for inst in instances:
            iid = inst["id"]
            name = inst.get("name") or iid
            state = inst.get("state")
            cpu = inst.get("avg_cpu_7d")
            cost = inst.get("estimated_monthly_cost_usd", 0)
            itype = inst.get("type", "")

            # ── UNUSED ──
            if state == "stopped":
                issues.append({
                    "resource_type": "EC2", "resource_id": iid, "resource_name": name,
                    "category": "UNUSED",
                    "issue": "Stopped instance",
                    "detail": f"{name} ({itype}) is stopped but still incurs EBS storage charges.",
                    "severity": "medium",
                    "recommendation": "Terminate if no longer needed, or snapshot and terminate.",
                    "savings_usd": round(cost * 0.15, 2),
                    "action": "terminate_or_snapshot",
                })

            elif state == "running" and cpu is not None:

                # ── OVERUTILIZED — CRITICAL ──
                if cpu >= self.CPU_CRITICAL_THRESHOLD:
                    upgrade = self._suggest_ec2_upgrade(itype)
                    issues.append({
                        "resource_type": "EC2", "resource_id": iid, "resource_name": name,
                        "category": "OVERUSED",
                        "issue": "Critically overloaded instance",
                        "detail": f"{name} ({itype}) is at {cpu}% avg CPU over 7 days. High crash risk.",
                        "severity": "critical",
                        "recommendation": f"Upgrade to {upgrade} immediately to prevent outages.",
                        "savings_usd": 0,
                        "action": "upgrade_instance",
                        "suggested_type": upgrade,
                    })

                # ── OVERUTILIZED — HIGH ──
                elif cpu >= self.CPU_HIGH_THRESHOLD:
                    upgrade = self._suggest_ec2_upgrade(itype)
                    issues.append({
                        "resource_type": "EC2", "resource_id": iid, "resource_name": name,
                        "category": "OVERUSED",
                        "issue": "Undersized instance",
                        "detail": f"{name} ({itype}) is at {cpu}% avg CPU over 7 days. Performance degradation likely.",
                        "severity": "high",
                        "recommendation": f"Upgrade to {upgrade} to improve performance and reliability.",
                        "savings_usd": 0,
                        "action": "upgrade_instance",
                        "suggested_type": upgrade,
                    })

                # ── UNDERUTILIZED — IDLE ──
                elif cpu < self.CPU_IDLE_THRESHOLD:
                    issues.append({
                        "resource_type": "EC2", "resource_id": iid, "resource_name": name,
                        "category": "UNDERUSED",
                        "issue": "Idle instance",
                        "detail": f"{name} ({itype}) has only {cpu}% avg CPU over 7 days.",
                        "severity": "high",
                        "recommendation": "Stop or terminate this instance.",
                        "savings_usd": cost,
                        "action": "stop_or_terminate",
                    })

                # ── UNDERUTILIZED — OVERSIZED ──
                elif cpu < self.CPU_UNDERUSED_THRESHOLD:
                    downgrade = self._suggest_ec2_downgrade(itype)
                    savings = round(cost * 0.4, 2)
                    issues.append({
                        "resource_type": "EC2", "resource_id": iid, "resource_name": name,
                        "category": "UNDERUSED",
                        "issue": "Oversized instance",
                        "detail": f"{name} ({itype}) has only {cpu}% avg CPU over 7 days.",
                        "severity": "medium",
                        "recommendation": f"Downgrade to {downgrade}. Save ~${savings}/month.",
                        "savings_usd": savings,
                        "action": "resize_instance",
                        "suggested_type": downgrade,
                    })

        return issues

    # ── EBS ──────────────────────────────────────────────────────────────────

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
                    "category": "UNUSED",
                    "issue": "Unattached volume",
                    "detail": f"{vid} ({size} GB, {vtype}) is not attached to any instance.",
                    "severity": "high",
                    "recommendation": "Delete or snapshot this orphaned volume.",
                    "savings_usd": cost,
                    "action": "delete_or_snapshot",
                })
            elif vtype == "gp2":
                savings = round(cost - size * 0.08, 2)
                if savings > 0:
                    issues.append({
                        "resource_type": "EBS", "resource_id": vid,
                        "category": "UNDERUSED",
                        "issue": "Outdated volume type (gp2)",
                        "detail": f"{vid} ({size} GB) uses gp2. gp3 is 20% cheaper with better IOPS.",
                        "severity": "low",
                        "recommendation": f"Migrate to gp3. Save ~${savings}/month.",
                        "savings_usd": savings,
                        "action": "modify_volume_type",
                        "suggested_type": "gp3",
                    })
        return issues

    # ── RDS ──────────────────────────────────────────────────────────────────

    def _check_rds(self, instances: list) -> list:
        issues = []
        for db in instances:
            db_id = db["id"]
            db_class = db.get("class", "")
            status = db.get("status")
            cost = db.get("estimated_monthly_cost_usd", 0)
            connections = db.get("avg_connections_7d")
            multi_az = db.get("multi_az", False)

            max_conn = self.RDS_MAX_CONNECTIONS.get(db_class, 100)

            # ── UNUSED ──
            if status == "stopped":
                issues.append({
                    "resource_type": "RDS", "resource_id": db_id,
                    "category": "UNUSED",
                    "issue": "Stopped RDS instance",
                    "detail": f"{db_id} ({db_class}) is stopped. Storage charges still apply.",
                    "severity": "medium",
                    "recommendation": "Delete and take a final snapshot if data must be retained.",
                    "savings_usd": round(cost * 0.20, 2),
                    "action": "delete_rds",
                })

            elif connections is not None:

                conn_pct = (connections / max_conn) * 100

                # ── OVERUTILIZED — CRITICAL ──
                if conn_pct >= 90:
                    issues.append({
                        "resource_type": "RDS", "resource_id": db_id,
                        "category": "OVERUSED",
                        "issue": "Database connection limit critical",
                        "detail": f"{db_id} ({db_class}) is using {round(conn_pct)}% of max connections ({int(connections)}/{max_conn}). Risk of connection errors.",
                        "severity": "critical",
                        "recommendation": "Upgrade instance class or add read replicas immediately.",
                        "savings_usd": 0,
                        "action": "upgrade_rds",
                    })

                # ── OVERUTILIZED — HIGH ──
                elif conn_pct >= self.RDS_HIGH_CONNECTIONS:
                    issues.append({
                        "resource_type": "RDS", "resource_id": db_id,
                        "category": "OVERUSED",
                        "issue": "High database connection usage",
                        "detail": f"{db_id} ({db_class}) is using {round(conn_pct)}% of max connections ({int(connections)}/{max_conn}).",
                        "severity": "high",
                        "recommendation": "Consider upgrading instance class or implementing connection pooling (RDS Proxy).",
                        "savings_usd": 0,
                        "action": "upgrade_rds_or_add_proxy",
                    })

                # ── UNDERUTILIZED — IDLE ──
                elif connections <= self.RDS_IDLE_CONNECTIONS:
                    issues.append({
                        "resource_type": "RDS", "resource_id": db_id,
                        "category": "UNDERUSED",
                        "issue": "Idle database",
                        "detail": f"{db_id} ({db_class}) has avg {connections} connections over 7 days.",
                        "severity": "high",
                        "recommendation": "Stop or delete this database. Take a snapshot first.",
                        "savings_usd": cost,
                        "action": "stop_or_delete_rds",
                    })

            # ── RELIABILITY ──
            if not multi_az and status == "available":
                issues.append({
                    "resource_type": "RDS", "resource_id": db_id,
                    "category": "RELIABILITY",
                    "issue": "Single-AZ deployment",
                    "detail": f"{db_id} is Single-AZ. A hardware failure will cause downtime.",
                    "severity": "low",
                    "recommendation": "Enable Multi-AZ for production workloads.",
                    "savings_usd": 0,
                    "action": "enable_multi_az",
                })

        return issues

    # ── ELASTIC IPs ───────────────────────────────────────────────────────────

    def _check_elastic_ips(self, eips: list) -> list:
        issues = []
        for eip in eips:
            if not eip.get("attached", True):
                issues.append({
                    "resource_type": "Elastic IP",
                    "resource_id": eip["id"],
                    "category": "UNUSED",
                    "issue": "Unattached Elastic IP",
                    "detail": f"EIP {eip['public_ip']} is not associated with any instance.",
                    "severity": "high",
                    "recommendation": "Release this Elastic IP to stop charges.",
                    "savings_usd": 3.65,
                    "action": "release_eip",
                })
        return issues

    # ── LOAD BALANCERS ────────────────────────────────────────────────────────

    def _check_load_balancers(self, balancers: list) -> list:
        issues = []
        for lb in balancers:
            requests = lb.get("avg_requests_7d")
            cost = lb.get("estimated_monthly_cost_usd", 16.0)

            if requests is not None and requests <= 100:
                issues.append({
                    "resource_type": "Load Balancer",
                    "resource_id": lb["name"],
                    "category": "UNUSED",
                    "issue": "Idle load balancer",
                    "detail": f"{lb['name']} ({lb['type']}) has avg {requests} requests/day over 7 days.",
                    "severity": "high",
                    "recommendation": "Delete this load balancer if no longer routing traffic.",
                    "savings_usd": cost,
                    "action": "delete_load_balancer",
                })
        return issues

    # ── LAMBDA ────────────────────────────────────────────────────────────────

    def _check_lambda(self, functions: list) -> list:
        issues = []
        for fn in functions:
            name = fn["name"]
            invocations = fn.get("invocations_30d")
            error_rate = fn.get("error_rate_percent")
            timeout = fn.get("timeout_seconds", 3)
            memory_mb = fn.get("memory_mb", 128)
            avg_duration = fn.get("avg_duration_ms")  # optional, from X-Ray

            # ── UNUSED ──
            if invocations == 0:
                issues.append({
                    "resource_type": "Lambda", "resource_id": name,
                    "category": "UNUSED",
                    "issue": "Dead Lambda function",
                    "detail": f"{name} had 0 invocations in the last 30 days.",
                    "severity": "medium",
                    "recommendation": "Delete this function if it's no longer needed.",
                    "savings_usd": 0,
                    "action": "delete_lambda",
                })

            else:
                # ── OVERUTILIZED — HIGH ERROR RATE ──
                if error_rate is not None and error_rate >= self.LAMBDA_HIGH_ERROR_RATE:
                    issues.append({
                        "resource_type": "Lambda", "resource_id": name,
                        "category": "OVERUSED",
                        "issue": "High Lambda error rate",
                        "detail": f"{name} has a {error_rate}% error rate over 30 days ({invocations} invocations).",
                        "severity": "high",
                        "recommendation": "Check CloudWatch logs. Common causes: memory limits, timeouts, missing permissions.",
                        "savings_usd": 0,
                        "action": "fix_lambda_errors",
                    })

                # ── OVERUTILIZED — TIMEOUT RISK ──
                if avg_duration is not None:
                    timeout_ms = timeout * 1000
                    duration_pct = (avg_duration / timeout_ms) * 100
                    if duration_pct >= self.LAMBDA_TIMEOUT_THRESHOLD:
                        issues.append({
                            "resource_type": "Lambda", "resource_id": name,
                            "category": "OVERUSED",
                            "issue": "Lambda timeout risk",
                            "detail": f"{name} uses {round(duration_pct)}% of its {timeout}s timeout on average.",
                            "severity": "high",
                            "recommendation": f"Increase timeout or memory (currently {memory_mb}MB). More memory = faster CPU = faster execution.",
                            "savings_usd": 0,
                            "action": "increase_lambda_memory",
                        })

        return issues

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _suggest_ec2_upgrade(self, instance_type: str) -> str:
        UPGRADE_MAP = {
            "t3.micro":   "t3.small",
            "t3.small":   "t3.medium",
            "t3.medium":  "t3.large",
            "t3.large":   "t3.xlarge",
            "t3.xlarge":  "t3.2xlarge",
            "t2.micro":   "t2.small",
            "t2.small":   "t2.medium",
            "t2.medium":  "t2.large",
            "t2.large":   "t2.xlarge",
            "m5.large":   "m5.xlarge",
            "m5.xlarge":  "m5.2xlarge",
            "c5.large":   "c5.xlarge",
            "c5.xlarge":  "c5.2xlarge",
            "r5.large":   "r5.xlarge",
        }
        return UPGRADE_MAP.get(instance_type, f"larger {instance_type.split('.')[0]}")

    def _suggest_ec2_downgrade(self, instance_type: str) -> str:
        DOWNGRADE_MAP = {
            "t3.2xlarge": "t3.xlarge",
            "t3.xlarge":  "t3.large",
            "t3.large":   "t3.medium",
            "t3.medium":  "t3.small",
            "t3.small":   "t3.micro",
            "t2.xlarge":  "t2.large",
            "t2.large":   "t2.medium",
            "t2.medium":  "t2.small",
            "t2.small":   "t2.micro",
            "m5.2xlarge": "m5.xlarge",
            "m5.xlarge":  "m5.large",
            "c5.xlarge":  "c5.large",
            "r5.xlarge":  "r5.large",
        }
        return DOWNGRADE_MAP.get(instance_type, f"smaller {instance_type.split('.')[0]}")
