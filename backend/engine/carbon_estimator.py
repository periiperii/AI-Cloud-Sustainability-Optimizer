"""
Carbon Footprint Estimator - Enhanced
Estimates CO₂ emissions from AWS infrastructure.

Covers: EC2, EBS, S3, RDS, Lambda
New features:
  - ap-south-1 (Mumbai) + more regions
  - RDS carbon estimation
  - Lambda carbon estimation
  - Potential carbon savings (from waste)
  - Green Region Recommendation
  - Sustainability Score (0-100)

Sources:
- AWS sustainability report (average PUE ~1.2)
- US EPA eGRID + international grid emission factors
- Cloud Carbon Footprint methodology (cloudcarbonfootprint.org)
"""

from typing import Dict, Any, List


# ── Region Emission Factors (kgCO₂/kWh) ─────────────────────────────────────
REGION_EMISSION_FACTORS = {
    # USA
    "us-east-1": 0.379,       # Virginia (mixed grid)
    "us-east-2": 0.410,       # Ohio
    "us-west-1": 0.322,       # N. California
    "us-west-2": 0.136,       # Oregon 🌿 (mostly hydro/wind)
    # Europe
    "eu-west-1": 0.279,       # Ireland
    "eu-west-2": 0.228,       # London
    "eu-west-3": 0.052,       # Paris 🌿 (nuclear-heavy)
    "eu-central-1": 0.338,    # Frankfurt
    "eu-north-1": 0.008,      # Stockholm 🌿 (almost 100% renewable)
    "eu-south-1": 0.233,      # Milan
    # Asia Pacific
    "ap-south-1": 0.708,      # Mumbai 🔴 (coal-heavy Indian grid)
    "ap-south-2": 0.708,      # Hyderabad 🔴
    "ap-southeast-1": 0.408,  # Singapore
    "ap-southeast-2": 0.610,  # Sydney (coal-heavy)
    "ap-northeast-1": 0.506,  # Tokyo
    "ap-northeast-2": 0.425,  # Seoul
    "ap-northeast-3": 0.506,  # Osaka
    "ap-east-1": 0.360,       # Hong Kong
    # Americas
    "ca-central-1": 0.120,    # Canada 🌿 (mostly hydro)
    "sa-east-1": 0.074,       # São Paulo 🌿 (very clean grid)
    # Middle East & Africa
    "me-south-1": 0.732,      # Bahrain 🔴 (gas-heavy)
    "af-south-1": 0.928,      # Cape Town 🔴 (coal-heavy)
}

DEFAULT_EMISSION_FACTOR = 0.379

# ── EC2 Power Draw (Watts) ───────────────────────────────────────────────────
INSTANCE_POWER_WATTS = {
    "t2.micro": 3.5,   "t2.small": 7.0,   "t2.medium": 14.0,  "t2.large": 28.0,
    "t3.micro": 3.5,   "t3.small": 7.0,   "t3.medium": 14.0,
    "t3.large": 28.0,  "t3.xlarge": 56.0, "t3.2xlarge": 112.0,
    "m5.large": 30.0,  "m5.xlarge": 60.0, "m5.2xlarge": 120.0,
    "c5.large": 27.0,  "c5.xlarge": 54.0, "c5.2xlarge": 108.0,
    "r5.large": 32.0,  "r5.xlarge": 64.0,
    "m6g.large": 25.0, "m6g.xlarge": 50.0,   # Graviton (more efficient)
    "c6g.large": 22.0, "c6g.xlarge": 44.0,
}

# RDS roughly same power as equivalent EC2 class
RDS_POWER_WATTS = {
    "db.t3.micro": 3.5,  "db.t3.small": 7.0,  "db.t3.medium": 14.0,
    "db.t3.large": 28.0, "db.m5.large": 30.0, "db.m5.xlarge": 60.0,
    "db.r5.large": 32.0, "db.r5.xlarge": 64.0,
}

AWS_PUE = 1.2           # AWS average Power Usage Effectiveness
HOURS_PER_MONTH = 730

# ── Green Regions for recommendations ────────────────────────────────────────
GREEN_REGIONS = {
    "us-west-2":    {"name": "Oregon",     "factor": 0.136},
    "ca-central-1": {"name": "Canada",     "factor": 0.120},
    "eu-north-1":   {"name": "Stockholm",  "factor": 0.008},
    "eu-west-3":    {"name": "Paris",      "factor": 0.052},
    "sa-east-1":    {"name": "São Paulo",  "factor": 0.074},
}


class CarbonEstimator:
    def __init__(self, region: str = "us-east-1"):
        self.region = region
        self.emission_factor = REGION_EMISSION_FACTORS.get(
            region, DEFAULT_EMISSION_FACTOR)

    def estimate(self, resources: dict, waste_issues: list = None) -> Dict[str, Any]:
        """
        Estimate total monthly carbon footprint.
        Optionally accepts waste_issues to compute potential savings.
        """
        ec2_result = self._estimate_ec2(resources.get("ec2_instances", []))
        ebs_result = self._estimate_ebs(resources.get("ebs_volumes", []))
        s3_result = self._estimate_s3(resources.get("s3_buckets", []))
        rds_result = self._estimate_rds(resources.get("rds_instances", []))
        lamb_result = self._estimate_lambda(
            resources.get("lambda_functions", []))

        total_kwh = sum([
            ec2_result["kwh_month"],
            ebs_result["kwh_month"],
            s3_result["kwh_month"],
            rds_result["kwh_month"],
            lamb_result["kwh_month"],
        ])
        total_co2 = round(total_kwh * self.emission_factor, 2)

        # Potential savings from fixing waste
        savings = self._estimate_carbon_savings(resources, waste_issues or [])

        # Green region recommendation
        green_rec = self._green_region_recommendation(total_co2)

        # Sustainability score
        score = self._sustainability_score(
            total_co2=total_co2,
            region=self.region,
            waste_count=len(waste_issues) if waste_issues else 0,
            resources=resources,
        )

        return {
            "region": self.region,
            "emission_factor_kg_per_kwh": self.emission_factor,
            "total_kwh_month": round(total_kwh, 2),
            "total_co2_kg_month": total_co2,
            "equivalent_driving_km": round(total_co2 / 0.21, 1),
            # 1 tree absorbs ~21kg CO₂/year
            "equivalent_trees_needed": round(total_co2 / 21, 1),
            "breakdown": {
                "ec2":    ec2_result,
                "ebs":    ebs_result,
                "s3":     s3_result,
                "rds":    rds_result,
                "lambda": lamb_result,
            },
            "potential_savings": savings,
            "green_region_recommendation": green_rec,
            "sustainability_score": score,
            "renewable_energy_note": self._get_renewable_note(),
        }

    # ── Service Estimators ───────────────────────────────────────────────────

    def _estimate_ec2(self, instances: list) -> dict:
        total_kwh = 0.0
        running_count = 0

        for inst in instances:
            if inst.get("state") != "running":
                continue
            itype = inst.get("type", "")
            watts = INSTANCE_POWER_WATTS.get(itype, 20.0)
            cpu = inst.get("avg_cpu_7d")
            if cpu is not None:
                utilization_factor = 0.3 + (cpu / 100) * 0.7
                watts = watts * utilization_factor
            total_kwh += (watts * AWS_PUE * HOURS_PER_MONTH) / 1000
            running_count += 1

        return {
            "running_instances": running_count,
            "kwh_month": round(total_kwh, 2),
            "co2_kg_month": round(total_kwh * self.emission_factor, 2),
        }

    def _estimate_ebs(self, volumes: list) -> dict:
        """0.000278 kWh per GB per month (SSD)"""
        total_gb = sum(v.get("size_gb", 0) for v in volumes)
        kwh = total_gb * 0.000278
        return {
            "total_gb": total_gb,
            "kwh_month": round(kwh, 4),
            "co2_kg_month": round(kwh * self.emission_factor, 4),
        }

    def _estimate_s3(self, buckets: list) -> dict:
        """Assumes ~50GB average per bucket until S3 Storage Lens is integrated."""
        count = len(buckets)
        assumed_gb = count * 50
        kwh = assumed_gb * 0.000278
        return {
            "bucket_count": count,
            "assumed_total_gb": assumed_gb,
            "kwh_month": round(kwh, 4),
            "co2_kg_month": round(kwh * self.emission_factor, 4),
            "note": "Assumes ~50GB/bucket. Integrate S3 Storage Lens for accuracy.",
        }

    def _estimate_rds(self, instances: list) -> dict:
        """
        RDS carbon estimation.
        Power ≈ equivalent EC2 instance class × PUE.
        Only counts 'available' (running) instances.
        """
        total_kwh = 0.0
        running_count = 0

        for db in instances:
            if db.get("status") != "available":
                continue
            db_class = db.get("class", "")
            watts = RDS_POWER_WATTS.get(db_class, 14.0)

            # RDS connections as proxy for utilization
            connections = db.get("avg_connections_7d")
            if connections is not None:
                # Rough: idle at 30%, scale up with connections (cap at 90%)
                util = min(0.3 + (min(connections, 100) / 100) * 0.6, 0.90)
                watts = watts * util

            total_kwh += (watts * AWS_PUE * HOURS_PER_MONTH) / 1000
            running_count += 1

        return {
            "running_instances": running_count,
            "kwh_month": round(total_kwh, 2),
            "co2_kg_month": round(total_kwh * self.emission_factor, 2),
        }

    def _estimate_lambda(self, functions: list) -> dict:
        """
        Lambda carbon estimation.
        Formula: Wh = duration_avg_ms/1000 × memory_gb × invocations × 0.00001667
        Default: assume avg duration 500ms if unknown.
        """
        total_kwh = 0.0
        total_invocations = 0

        for fn in functions:
            invocations = fn.get("invocations_30d") or 0
            memory_mb = fn.get("memory_mb", 128)
            memory_gb = memory_mb / 1024
            avg_duration_sec = 0.5  # assume 500ms default

            # Wh per invocation
            wh = avg_duration_sec * memory_gb * 0.00001667
            fn_kwh = (wh * invocations) / 1000
            total_kwh += fn_kwh
            total_invocations += invocations

        return {
            "function_count": len(functions),
            "total_invocations_30d": total_invocations,
            "kwh_month": round(total_kwh, 6),
            "co2_kg_month": round(total_kwh * self.emission_factor, 6),
            "note": "Assumes 500ms avg duration. Use X-Ray traces for accuracy.",
        }

    # ── Carbon Savings from Waste Fixes ──────────────────────────────────────

    def _estimate_carbon_savings(self, resources: dict, waste_issues: list) -> dict:
        """
        Estimate how much CO₂ could be saved by fixing all detected waste issues.
        Maps each waste action to an estimated energy reduction.
        """
        total_kwh_savings = 0.0

        # Build lookup maps
        ec2_map = {i["id"]: i for i in resources.get("ec2_instances", [])}
        rds_map = {i["id"]: i for i in resources.get("rds_instances", [])}

        for issue in waste_issues:
            action = issue.get("action", "")
            rid = issue.get("resource_id", "")

            if action in ("stop_or_terminate", "terminate_or_snapshot"):
                inst = ec2_map.get(rid)
                if inst:
                    itype = inst.get("type", "")
                    watts = INSTANCE_POWER_WATTS.get(itype, 20.0)
                    total_kwh_savings += (watts * AWS_PUE *
                                          HOURS_PER_MONTH) / 1000

            elif action == "resize_instance":
                inst = ec2_map.get(rid)
                if inst:
                    itype = inst.get("type", "")
                    watts = INSTANCE_POWER_WATTS.get(itype, 20.0)
                    total_kwh_savings += (watts * AWS_PUE *
                                          HOURS_PER_MONTH) / 1000 * 0.4

            elif action == "stop_or_delete_rds":
                db = rds_map.get(rid)
                if db:
                    watts = RDS_POWER_WATTS.get(db.get("class", ""), 14.0)
                    total_kwh_savings += (watts * AWS_PUE *
                                          HOURS_PER_MONTH) / 1000

            elif action == "delete_load_balancer":
                total_kwh_savings += 0.5  # LBs use ~0.5 kWh/month

        co2_savings = round(total_kwh_savings * self.emission_factor, 2)
        return {
            "potential_kwh_reduction": round(total_kwh_savings, 2),
            "potential_co2_reduction_kg": co2_savings,
            "equivalent_driving_km_saved": round(co2_savings / 0.21, 1),
        }

    # ── Green Region Recommendation ───────────────────────────────────────────

    def _green_region_recommendation(self, current_co2: float) -> dict:
        """Recommend the cleanest AWS region and estimate CO₂ reduction."""
        if self.region in GREEN_REGIONS:
            return {
                "current_region": self.region,
                "message": f"You're already in a green region! ({self.region})",
                "already_green": True,
            }

        # Find best green region (lowest emission factor)
        best_region = min(GREEN_REGIONS.items(), key=lambda x: x[1]["factor"])
        best_code, best_info = best_region

        if self.emission_factor > 0:
            reduction_pct = round(
                (1 - best_info["factor"] / self.emission_factor) * 100, 1)
            new_co2 = round(
                current_co2 * best_info["factor"] / self.emission_factor, 2)
            co2_saved = round(current_co2 - new_co2, 2)
        else:
            reduction_pct = 0
            co2_saved = 0
            new_co2 = current_co2

        return {
            "current_region": self.region,
            "current_emission_factor": self.emission_factor,
            "recommended_region": best_code,
            "recommended_region_name": best_info["name"],
            "recommended_emission_factor": best_info["factor"],
            "potential_co2_reduction_pct": reduction_pct,
            "potential_co2_saved_kg": co2_saved,
            "new_estimated_co2_kg": new_co2,
            "already_green": False,
            "message": f"Migrating to {best_info['name']} ({best_code}) could reduce emissions by {reduction_pct}%.",
        }

    # ── Sustainability Score ──────────────────────────────────────────────────

    def _sustainability_score(
        self, total_co2: float, region: str,
        waste_count: int, resources: dict
    ) -> dict:
        """
        Score 0–100 based on:
          - Region cleanliness     (30 pts)
          - Waste issues           (30 pts)
          - Carbon per instance    (25 pts)
          - Lambda/RDS efficiency  (15 pts)
        """
        score = 100

        # 1. Region cleanliness (30 pts)
        emission_factor = REGION_EMISSION_FACTORS.get(
            region, DEFAULT_EMISSION_FACTOR)
        max_factor = 0.928   # Cape Town (worst)
        min_factor = 0.008   # Stockholm (best)
        region_score = 30 * \
            (1 - (emission_factor - min_factor) / (max_factor - min_factor))
        region_score = max(0, min(30, region_score))

        # 2. Waste issues (30 pts) — lose 3 pts per issue, min 0
        waste_penalty = min(30, waste_count * 3)
        waste_score = 30 - waste_penalty

        # 3. Carbon per running instance (25 pts)
        running_instances = len([
            i for i in resources.get("ec2_instances", []) if i.get("state") == "running"
        ]) + len([
            d for d in resources.get("rds_instances", []) if d.get("status") == "available"
        ])
        if running_instances == 0:
            carbon_score = 25  # no instances = no emissions
        else:
            co2_per_instance = total_co2 / running_instances
            # Benchmark: 10 kg/instance/month = good, 50+ = bad
            if co2_per_instance <= 10:
                carbon_score = 25
            elif co2_per_instance >= 50:
                carbon_score = 0
            else:
                carbon_score = round(
                    25 * (1 - (co2_per_instance - 10) / 40), 1)

        # 4. Lambda dead functions (15 pts)
        lambda_functions = resources.get("lambda_functions", [])
        if not lambda_functions:
            lambda_score = 15
        else:
            dead = sum(1 for f in lambda_functions if (
                f.get("invocations_30d") or 0) == 0)
            dead_ratio = dead / len(lambda_functions)
            lambda_score = round(15 * (1 - dead_ratio), 1)

        total_score = round(region_score + waste_score +
                            carbon_score + lambda_score, 1)
        total_score = max(0, min(100, total_score))

        # Grade
        if total_score >= 80:
            grade, label = "A", "Excellent"
        elif total_score >= 65:
            grade, label = "B", "Good"
        elif total_score >= 50:
            grade, label = "C", "Needs Improvement"
        elif total_score >= 35:
            grade, label = "D", "Poor"
        else:
            grade, label = "F", "Critical"

        return {
            "score": total_score,
            "grade": grade,
            "label": label,
            "breakdown": {
                "region_cleanliness": round(region_score, 1),
                "waste_reduction": round(waste_score, 1),
                "carbon_efficiency": round(carbon_score, 1),
                "lambda_hygiene": round(lambda_score, 1),
            },
            "max_scores": {
                "region_cleanliness": 30,
                "waste_reduction": 30,
                "carbon_efficiency": 25,
                "lambda_hygiene": 15,
            }
        }

    def _get_renewable_note(self) -> str:
        factor = self.emission_factor
        if factor <= 0.10:
            return f"{self.region} is one of the cleanest AWS regions in the world. Excellent choice! 🌿"
        elif factor <= 0.20:
            return f"{self.region} has a relatively clean grid. Good sustainability choice."
        elif factor <= 0.40:
            return f"{self.region} has a moderate carbon grid. Consider us-west-2 or eu-north-1 for cleaner compute."
        elif factor <= 0.60:
            return f"{self.region} has a carbon-heavy grid. Migrating to us-west-2 (Oregon) could cut emissions by ~{round((1-0.136/factor)*100)}%."
        else:
            return f"⚠️ {self.region} has one of the highest carbon grids on AWS. Strongly consider migrating to us-west-2, eu-north-1, or ca-central-1."
