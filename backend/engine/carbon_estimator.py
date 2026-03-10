"""
Carbon Footprint Estimator
Estimates CO₂ emissions from AWS infrastructure.

Methodology:
- EC2: CPU usage → kWh → kg CO₂ using regional grid emission factor
- EBS: GB stored → kWh → kg CO₂
- S3: Number of buckets → rough estimate

Sources:
- AWS sustainability report (average PUE ~1.2)
- US EPA eGRID emission factors by region
- Cloud Carbon Footprint methodology (https://www.cloudcarbonfootprint.org/)
"""

from typing import Dict, Any


# kgCO₂/kWh for AWS regions (approximate grid emission factors)
REGION_EMISSION_FACTORS = {
    "us-east-1": 0.379,       # Virginia (mixed grid)
    "us-east-2": 0.410,       # Ohio
    "us-west-1": 0.322,       # N. California
    "us-west-2": 0.136,       # Oregon (mostly hydro/wind)
    "eu-west-1": 0.279,       # Ireland
    "eu-west-2": 0.228,       # London
    "eu-central-1": 0.338,    # Frankfurt
    "ap-southeast-1": 0.408,  # Singapore
    "ap-southeast-2": 0.610,  # Sydney (coal-heavy)
    "ap-northeast-1": 0.506,  # Tokyo
    "ca-central-1": 0.120,    # Canada (mostly hydro)
    "sa-east-1": 0.074,       # São Paulo (very clean grid)
}

DEFAULT_EMISSION_FACTOR = 0.379  # fallback

# Average power draw per EC2 instance type (Watts)
INSTANCE_POWER_WATTS = {
    "t2.micro": 3.5,
    "t2.small": 7.0,
    "t2.medium": 14.0,
    "t2.large": 28.0,
    "t3.micro": 3.5,
    "t3.small": 7.0,
    "t3.medium": 14.0,
    "t3.large": 28.0,
    "t3.xlarge": 56.0,
    "m5.large": 30.0,
    "m5.xlarge": 60.0,
    "m5.2xlarge": 120.0,
    "c5.large": 27.0,
    "c5.xlarge": 54.0,
    "r5.large": 32.0,
}

DEFAULT_INSTANCE_WATTS = 20.0  # fallback
AWS_PUE = 1.2                  # AWS average Power Usage Effectiveness
HOURS_PER_MONTH = 730


class CarbonEstimator:
    def __init__(self, region: str = "us-east-1"):
        self.region = region
        self.emission_factor = REGION_EMISSION_FACTORS.get(region, DEFAULT_EMISSION_FACTOR)

    def estimate(self, resources: dict) -> Dict[str, Any]:
        """Estimate total monthly carbon footprint of scanned resources."""

        ec2_result = self._estimate_ec2(resources.get("ec2_instances", []))
        ebs_result = self._estimate_ebs(resources.get("ebs_volumes", []))
        s3_result = self._estimate_s3(resources.get("s3_buckets", []))

        total_kwh = ec2_result["kwh_month"] + ebs_result["kwh_month"] + s3_result["kwh_month"]
        total_co2 = round(total_kwh * self.emission_factor, 2)

        return {
            "region": self.region,
            "emission_factor_kg_per_kwh": self.emission_factor,
            "total_kwh_month": round(total_kwh, 2),
            "total_co2_kg_month": total_co2,
            "equivalent_driving_km": round(total_co2 / 0.21, 1),  # avg car ~210g CO₂/km
            "breakdown": {
                "ec2": ec2_result,
                "ebs": ebs_result,
                "s3": s3_result,
            },
            "renewable_energy_note": self._get_renewable_note(),
        }

    def _estimate_ec2(self, instances: list) -> dict:
        total_kwh = 0.0
        running_count = 0

        for inst in instances:
            if inst.get("state") != "running":
                continue

            itype = inst.get("type", "")
            watts = INSTANCE_POWER_WATTS.get(itype, DEFAULT_INSTANCE_WATTS)

            # Apply CPU utilization scaling if available
            cpu = inst.get("avg_cpu_7d")
            if cpu is not None:
                # Energy scales between idle (~30% of max) and full load
                utilization_factor = 0.3 + (cpu / 100) * 0.7
                watts = watts * utilization_factor

            kwh = (watts * AWS_PUE * HOURS_PER_MONTH) / 1000
            total_kwh += kwh
            running_count += 1

        co2 = round(total_kwh * self.emission_factor, 2)
        return {
            "running_instances": running_count,
            "kwh_month": round(total_kwh, 2),
            "co2_kg_month": co2,
        }

    def _estimate_ebs(self, volumes: list) -> dict:
        """EBS: ~0.000278 kWh per GB per month (SSD)"""
        total_gb = sum(v.get("size_gb", 0) for v in volumes)
        kwh = total_gb * 0.000278
        co2 = round(kwh * self.emission_factor, 4)
        return {
            "total_gb": total_gb,
            "kwh_month": round(kwh, 4),
            "co2_kg_month": co2,
        }

    def _estimate_s3(self, buckets: list) -> dict:
        """S3: rough estimate — each bucket assumed ~50GB average usage"""
        count = len(buckets)
        assumed_gb = count * 50
        kwh = assumed_gb * 0.000278
        co2 = round(kwh * self.emission_factor, 4)
        return {
            "bucket_count": count,
            "assumed_total_gb": assumed_gb,
            "kwh_month": round(kwh, 4),
            "co2_kg_month": co2,
            "note": "S3 estimate assumes ~50GB average per bucket. Use S3 Storage Lens for accuracy."
        }

    def _get_renewable_note(self) -> str:
        clean_regions = {"us-west-2", "ca-central-1", "sa-east-1", "eu-west-1"}
        if self.region in clean_regions:
            return f"{self.region} runs on a predominantly clean/renewable grid. Great choice!"
        elif self.region == "ap-southeast-2":
            return "Sydney (ap-southeast-2) has a coal-heavy grid. Consider migrating workloads to us-west-2 (Oregon) to reduce emissions by ~78%."
        else:
            return f"Consider migrating to us-west-2 (Oregon) or ca-central-1 (Canada) for lower carbon emissions."
