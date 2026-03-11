"""
AI Cloud Sustainability Optimizer - FastAPI Backend
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

from scanner.aws_scanner import AWSScanner
from engine.waste_detector import WasteDetector
from engine.carbon_estimator import CarbonEstimator

app = FastAPI(
    title="AI Cloud Sustainability Optimizer",
    description="Scan AWS infrastructure, detect waste, estimate carbon footprint",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "AI Cloud Sustainability Optimizer API", "status": "running",
            "timestamp": datetime.utcnow().isoformat()}


@app.get("/scan")
def scan_infrastructure(region: str = "us-east-1"):
    try:
        scanner = AWSScanner(region=region)
        results = scanner.scan_all()
        return {"status": "success", "region": region, "data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/waste")
def detect_waste(region: str = "us-east-1"):
    try:
        scanner = AWSScanner(region=region)
        resources = scanner.scan_all()
        detector = WasteDetector()
        issues = detector.detect(resources)
        return {
            "status": "success",
            "total_issues": len(issues),
            "estimated_monthly_savings_usd": sum(i.get("savings_usd", 0) for i in issues),
            "issues": issues
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/carbon")
def estimate_carbon(region: str = "us-east-1"):
    try:
        scanner = AWSScanner(region=region)
        resources = scanner.scan_all()
        detector = WasteDetector()
        issues = detector.detect(resources)
        estimator = CarbonEstimator(region=region)
        carbon = estimator.estimate(resources, waste_issues=issues)
        return {"status": "success", "region": region, "carbon": carbon}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/report")
def full_report(region: str = "us-east-1"):
    try:
        scanner = AWSScanner(region=region)
        resources = scanner.scan_all()

        detector = WasteDetector()
        issues = detector.detect(resources)

        estimator = CarbonEstimator(region=region)
        carbon = estimator.estimate(resources, waste_issues=issues)

        return {
            "status": "success",
            "generated_at": datetime.utcnow().isoformat(),
            "region": region,
            "infrastructure": resources,
            "waste": {
                "total_issues": len(issues),
                "estimated_monthly_savings_usd": sum(i.get("savings_usd", 0) for i in issues),
                "issues": issues,
            },
            "carbon": carbon,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
