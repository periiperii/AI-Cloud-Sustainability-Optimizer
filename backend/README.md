# 🌿 AI Cloud Sustainability Optimizer

> Scan your AWS infrastructure, detect waste, estimate carbon footprint, and get AI-powered optimization suggestions.

![Phase](https://img.shields.io/badge/Phase-1%20%E2%80%93%20Scanner%20%2B%20Waste%20Detection-green)
![Stack](https://img.shields.io/badge/Stack-FastAPI%20%7C%20boto3%20%7C%20React-blue)
![AWS](https://img.shields.io/badge/AWS-EC2%20%7C%20EBS%20%7C%20S3-orange)

---

## 🚀 What It Does

| Feature | Status |
|---|---|
| AWS Infrastructure Scanner (EC2, EBS, S3) | ✅ Phase 1 |
| Cloud Waste Detection Engine | ✅ Phase 1 |
| Carbon Footprint Estimator | ✅ Phase 1 |
| Interactive Dashboard | ✅ Phase 1 |
| AI Optimization Suggestions (RAG) | 🔜 Phase 2 |
| Chat Interface | 🔜 Phase 2 |
| Auto-remediation Agent | 🔜 Phase 3 |

---

## 📁 Project Structure

```
ai-cloud-optimizer/
├── backend/
│   ├── main.py                    # FastAPI app + API routes
│   ├── requirements.txt
│   ├── .env.example               # Copy to .env with your AWS keys
│   ├── scanner/
│   │   └── aws_scanner.py         # Scans EC2, EBS, S3 via boto3
│   └── engine/
│       ├── waste_detector.py      # Rule-based waste detection
│       └── carbon_estimator.py    # CO₂ estimation by region
└── frontend/
    └── index.html                 # Dashboard UI
```

---

## ⚡ Quickstart

### 1. Clone & Install

```bash
git clone https://github.com/YOUR_USERNAME/ai-cloud-optimizer
cd ai-cloud-optimizer/backend
pip install -r requirements.txt
```

### 2. Configure AWS Credentials

**Option A: AWS CLI (recommended)**
```bash
aws configure
# Enter: Access Key, Secret Key, Region (e.g. us-east-1), output format (json)
```

**Option B: Environment variables**
```bash
cp .env.example .env
# Edit .env with your credentials
```

**Required IAM Permissions:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeVolumes",
        "s3:ListAllMyBuckets",
        "s3:GetBucketLocation",
        "cloudwatch:GetMetricStatistics"
      ],
      "Resource": "*"
    }
  ]
}
```

### 3. Run the API

```bash
cd backend
uvicorn main:app --reload
```

API is live at: http://localhost:8000

API Docs: http://localhost:8000/docs

### 4. Open the Dashboard

Open `frontend/index.html` in your browser.

---

## 🔌 API Endpoints

| Endpoint | Description |
|---|---|
| `GET /` | Health check |
| `GET /scan?region=us-east-1` | Scan all AWS resources |
| `GET /waste?region=us-east-1` | Detect waste issues |
| `GET /carbon?region=us-east-1` | Estimate carbon footprint |
| `GET /report?region=us-east-1` | Full report (scan + waste + carbon) |

---

## 🌱 Carbon Estimation Methodology

- **EC2**: Instance power draw (Watts) × CPU utilization × AWS PUE (1.2) → kWh → kg CO₂
- **EBS**: GB stored × 0.000278 kWh/GB → kg CO₂  
- **S3**: Bucket count × assumed 50GB × 0.000278 kWh/GB → kg CO₂
- **Grid factors**: Regional CO₂/kWh from US EPA eGRID + international equivalents

---

## 🗺️ Roadmap

- **Phase 1** (Days 1–7): Scanner + Waste Detection + Dashboard ← *You are here*
- **Phase 2** (Days 8–11): Carbon estimator + AI suggestions with RAG + LangChain
- **Phase 3** (Days 12–14): Chat interface + Polish + Deployment

---

## 🏆 Built For

- Internship applications in Cloud / GenAI / Sustainability
- Demonstrating AWS + AI + Green Computing skills
- Medium blog post / portfolio project

---

*Built with ❤️ using FastAPI, boto3, and a commitment to greener cloud computing.*
