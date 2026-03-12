"""
AI Cloud Sustainability Optimizer - FastAPI Backend
Phase 2: Added /chat endpoint with Gemini + RAG
"""
from engine.ai_advisor import AIAdvisor
from engine.carbon_estimator import CarbonEstimator
from engine.waste_detector import WasteDetector
from scanner.aws_scanner import AWSScanner
import os
import json
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
load_dotenv()


app = FastAPI(
    title="AI Cloud Sustainability Optimizer",
    description="Scan AWS infrastructure, detect waste, estimate carbon, chat with AI",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory report cache (last scan result) ─────────────────────────────────
# In production, store in Redis or a database
_cached_report: dict = {}


# ── Request Models ────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str       # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    question: str
    history: Optional[List[ChatMessage]] = []
    region: Optional[str] = "us-east-1"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "message": "AI Cloud Sustainability Optimizer API v2",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
        "ai": "Gemini 1.5 Flash",
    }


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
            "issues": issues,
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
    global _cached_report
    try:
        scanner = AWSScanner(region=region)
        resources = scanner.scan_all()

        detector = WasteDetector()
        issues = detector.detect(resources)

        estimator = CarbonEstimator(region=region)
        carbon = estimator.estimate(resources, waste_issues=issues)

        report = {
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

        # Cache for AI chat
        _cached_report = report
        return report

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat")
def chat(request: ChatRequest):
    """
    AI chat endpoint.
    Uses the cached scan report as RAG context for Gemini.
    If no scan has been run yet, returns a helpful message.
    """
    global _cached_report

    if not _cached_report:
        return {
            "answer": "I don't have any infrastructure data yet! "
                      "Please run a scan first by clicking **Run Scan** on the dashboard. "
                      "Once I have your AWS data, I can answer detailed questions about your infrastructure, costs, and carbon footprint."
        }

    try:
        advisor = AIAdvisor()
        history = [{"role": m.role, "content": m.content}
                   for m in (request.history or [])]
        answer = advisor.ask(
            question=request.question,
            report=_cached_report,
            chat_history=history,
        )
        return {"answer": answer}

    except ValueError as e:
        # Missing API key
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI error: {str(e)}")
