"""
AI Cloud Sustainability Optimizer - FastAPI Backend
Phase 1: AWS Scanner + Waste Detection Engine
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
from datetime import datetime

from scanner.aws_scanner import AWSScanner
from engine.waste_detector import WasteDetector
from engine.carbon_estimator import CarbonEstimator

app = FastAPI(
    title="AI Cloud Sustainability Optimizer",
    description="Scan AWS infrastructure, detect waste, estimate carbon footprint",
    version="1.0.0"
)

# Allow frontend to call backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "message": "AI Cloud Sustainability Optimizer API",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/scan")
def scan_infrastructure(region: str = "us-east-1"):
    """
    Scan AWS infrastructure in the given region.
    Returns EC2, EBS, S3 summary.
    """
    try:
        scanner = AWSScanner(region=region)
        results = scanner.scan_all()
        return {"status": "success", "region": region, "data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/waste")
def detect_waste(region: str = "us-east-1"):
    """
    Run waste detection engine on scanned resources.
    Returns list of issues and recommendations.
    """
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
    """
    Estimate carbon footprint of AWS infrastructure.
    """
    try:
        scanner = AWSScanner(region=region)
        resources = scanner.scan_all()

        estimator = CarbonEstimator(region=region)
        carbon = estimator.estimate(resources)

        return {"status": "success", "region": region, "carbon": carbon}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/report")
def full_report(region: str = "us-east-1"):
    """
    Full sustainability report: scan + waste + carbon.
    """
    try:
        scanner = AWSScanner(region=region)
        resources = scanner.scan_all()

        detector = WasteDetector()
        issues = detector.detect(resources)

        estimator = CarbonEstimator(region=region)
        carbon = estimator.estimate(resources)

        return {
            "status": "success",
            "generated_at": datetime.utcnow().isoformat(),
            "region": region,
            "infrastructure": resources,
            "waste": {
                "total_issues": len(issues),
                "estimated_monthly_savings_usd": sum(i.get("savings_usd", 0) for i in issues),
                "issues": issues
            },
            "carbon": carbon
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
