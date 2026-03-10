"""
Waste Detection Engine
Applies rules to scanned AWS resources and flags waste.
"""

from typing import List, Dict, Any


class WasteDetector:
    """
    Rule-based waste detection for AWS resources.
    
    Rules:
    - EC2: CPU < 5% for 7 days → idle instance
    - EC2: CPU < 20% → oversized, suggest downgrade
    - EC2: stopped > 7 days → zombie instance
    - EBS: unattached volume → orphan volume
    - EBS: gp2 type → suggest upgrade to gp3 (20% cheaper)
    """

    CPU_IDLE_THRESHOLD = 5.0       # % CPU — idle if below this
    CPU_UNDERUSED_THRESHOLD = 20.0 # % CPU — oversized if below this

    def detect(self, resources: dict) -> List[Dict[str, Any]]:
        """Run all detection rules and return list of issues."""
        issues = []

        issues += self._check_ec2(resources.get("ec2_instances", []))
        issues += self._check_ebs(resources.get("ebs_volumes", []))

        # Sort by savings impact
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

            # Rule 1: Stopped instance (still costs for EBS + Elastic IPs)
            if state == "stopped":
                issues.append({
                    "resource_type": "EC2",
                    "resource_id": iid,
                    "resource_name": name,
                    "issue": "Stopped instance",
                    "detail": f"Instance {name} ({itype}) has been stopped. "
                              "Stopped instances still incur EBS storage charges.",
                    "severity": "medium",
                    "recommendation": "Terminate if no longer needed, or create an AMI and terminate.",
                    "savings_usd": round(cost * 0.15, 2),  # EBS costs ~15% of running
                    "action": "terminate_or_snapshot",
                })

            # Rule 2: Idle instance (CPU < 5%)
            elif state == "running" and cpu is not None and cpu < self.CPU_IDLE_THRESHOLD:
                issues.append({
                    "resource_type": "EC2",
                    "resource_id": iid,
                    "resource_name": name,
                    "issue": "Idle instance",
                    "detail": f"Instance {name} ({itype}) has average CPU of {cpu}% over 7 days. "
                              f"This is below the idle threshold of {self.CPU_IDLE_THRESHOLD}%.",
                    "severity": "high",
                    "recommendation": "Consider terminating or stopping this instance if it's not needed.",
                    "savings_usd": cost,
                    "action": "stop_or_terminate",
                })

            # Rule 3: Oversized instance (CPU < 20%)
            elif state == "running" and cpu is not None and cpu < self.CPU_UNDERUSED_THRESHOLD:
                downgrade = self._suggest_downgrade(itype)
                savings = round(cost * 0.4, 2)  # rough 40% savings on downgrade
                issues.append({
                    "resource_type": "EC2",
                    "resource_id": iid,
                    "resource_name": name,
                    "issue": "Oversized instance",
                    "detail": f"Instance {name} ({itype}) has average CPU of {cpu}% over 7 days. "
                              f"This suggests the instance is oversized.",
                    "severity": "medium",
                    "recommendation": f"Downgrade to {downgrade}. Estimated savings: ${savings}/month.",
                    "savings_usd": savings,
                    "action": "resize_instance",
                    "suggested_type": downgrade,
                })

        return issues

    def _check_ebs(self, volumes: list) -> list:
        issues = []

        for vol in volumes:
            vid = vol["id"]
            size = vol.get("size_gb", 0)
            vtype = vol.get("type", "gp2")
            attached = vol.get("attached", True)
            cost = vol.get("estimated_monthly_cost_usd", 0)

            # Rule 1: Unattached volume
            if not attached:
                issues.append({
                    "resource_type": "EBS",
                    "resource_id": vid,
                    "issue": "Unattached volume",
                    "detail": f"EBS volume {vid} ({size} GB, {vtype}) is not attached to any instance. "
                              "This is likely an orphaned volume from a terminated instance.",
                    "severity": "high",
                    "recommendation": "Delete this volume if data is not needed, or create a snapshot and delete.",
                    "savings_usd": cost,
                    "action": "delete_or_snapshot",
                })

            # Rule 2: gp2 → gp3 upgrade opportunity (20% cheaper, 3x IOPS baseline)
            elif vtype == "gp2":
                gp3_cost = round(size * 0.08, 2)
                savings = round(cost - gp3_cost, 2)
                if savings > 0:
                    issues.append({
                        "resource_type": "EBS",
                        "resource_id": vid,
                        "issue": "Outdated volume type (gp2)",
                        "detail": f"Volume {vid} ({size} GB) uses gp2 storage. "
                                  "gp3 offers 20% lower cost and 3x higher baseline IOPS.",
                        "severity": "low",
                        "recommendation": f"Migrate to gp3. Saves ~${savings}/month with better performance.",
                        "savings_usd": savings,
                        "action": "modify_volume_type",
                        "suggested_type": "gp3",
                    })

        return issues

    def _suggest_downgrade(self, instance_type: str) -> str:
        """Suggest a smaller instance type in the same family."""
        DOWNGRADE_MAP = {
            "t3.xlarge": "t3.large",
            "t3.large": "t3.medium",
            "t3.medium": "t3.small",
            "t3.small": "t3.micro",
            "t2.xlarge": "t2.large",
            "t2.large": "t2.medium",
            "t2.medium": "t2.small",
            "t2.small": "t2.micro",
            "m5.2xlarge": "m5.xlarge",
            "m5.xlarge": "m5.large",
            "c5.xlarge": "c5.large",
            "r5.xlarge": "r5.large",
        }
        return DOWNGRADE_MAP.get(instance_type, f"smaller {instance_type.split('.')[0]}")
