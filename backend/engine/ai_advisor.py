"""
AI Advisor - Phase 2
Uses Groq (free tier, fast inference) to answer questions
about your AWS infrastructure using RAG.
"""

import os
from groq import Groq
from typing import Optional


class AIAdvisor:
    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY not set in environment variables.")
        self.client = Groq(api_key=api_key)
        self.model = "llama-3.3-70b-versatile"

    def build_context(self, report: dict) -> str:
        """Convert scan report into text context for RAG."""
        infra = report.get("infrastructure", {})
        waste = report.get("waste", {})
        carbon = report.get("carbon", {})

        ec2 = infra.get("ec2_instances", [])
        ebs = infra.get("ebs_volumes", [])
        s3 = infra.get("s3_buckets", [])
        rds = infra.get("rds_instances", [])
        eips = infra.get("elastic_ips", [])
        lbs = infra.get("load_balancers", [])
        lambdas = infra.get("lambda_functions", [])

        score = carbon.get("sustainability_score", {})
        green = carbon.get("green_region_recommendation", {})
        savings = carbon.get("potential_savings", {})

        lines = [
            "=== AWS INFRASTRUCTURE REPORT ===",
            f"Region: {report.get('region', 'unknown')}",
            f"Generated: {report.get('generated_at', 'unknown')}",
            "",
            "--- EC2 INSTANCES ---",
        ]

        for inst in ec2:
            cpu = f"{inst.get('avg_cpu_7d')}%" if inst.get(
                'avg_cpu_7d') is not None else "N/A"
            lines.append(
                f"  - {inst.get('name') or inst.get('id')} | {inst.get('type')} | "
                f"{inst.get('state')} | CPU: {cpu} | ${inst.get('estimated_monthly_cost_usd')}/mo"
            )

        lines += ["", "--- EBS VOLUMES ---"]
        for vol in ebs:
            lines.append(
                f"  - {vol.get('id')} | {vol.get('size_gb')}GB {vol.get('type')} | "
                f"{'attached' if vol.get('attached') else 'UNATTACHED'} | "
                f"${vol.get('estimated_monthly_cost_usd')}/mo"
            )

        lines += ["", "--- RDS INSTANCES ---"]
        for db in rds:
            conn = db.get('avg_connections_7d')
            lines.append(
                f"  - {db.get('id')} | {db.get('class')} {db.get('engine')} | "
                f"{db.get('status')} | Connections: {conn if conn is not None else 'N/A'} | "
                f"${db.get('estimated_monthly_cost_usd')}/mo"
            )

        lines += ["", "--- ELASTIC IPs ---"]
        for eip in eips:
            lines.append(
                f"  - {eip.get('public_ip')} | "
                f"{'ATTACHED' if eip.get('attached') else 'UNATTACHED - $3.65/mo'}"
            )

        lines += ["", "--- LOAD BALANCERS ---"]
        for lb in lbs:
            lines.append(
                f"  - {lb.get('name')} | {lb.get('type')} | "
                f"Requests/day: {lb.get('avg_requests_7d', 'N/A')} | "
                f"${lb.get('estimated_monthly_cost_usd')}/mo"
            )

        lines += ["", "--- LAMBDA FUNCTIONS ---"]
        for fn in lambdas:
            lines.append(
                f"  - {fn.get('name')} | {fn.get('runtime')} | "
                f"Invocations (30d): {fn.get('invocations_30d', 0)} | "
                f"Error rate: {fn.get('error_rate_percent', 0)}%"
            )

        lines += ["", "--- S3 BUCKETS ---"]
        for b in s3:
            lines.append(f"  - {b.get('name')} | {b.get('region')}")

        lines += [
            "",
            "--- WASTE ISSUES ---",
            f"Total issues: {waste.get('total_issues', 0)}",
            f"Estimated monthly savings if fixed: ${waste.get('estimated_monthly_savings_usd', 0)}",
        ]
        for issue in waste.get("issues", []):
            lines.append(
                f"  [{issue.get('severity', '').upper()}] {issue.get('resource_type')} - "
                f"{issue.get('issue')}: {issue.get('recommendation')}"
            )

        lines += [
            "",
            "--- CARBON FOOTPRINT ---",
            f"Total CO₂: {carbon.get('total_co2_kg_month')} kg/month",
            f"Equivalent driving: {carbon.get('equivalent_driving_km')} km",
            f"Emission factor: {carbon.get('emission_factor_kg_per_kwh')} kgCO₂/kWh",
            f"Potential CO₂ savings: {savings.get('potential_co2_reduction_kg', 0)} kg/mo if waste fixed",
            "",
            "--- SUSTAINABILITY SCORE ---",
            f"Score: {score.get('score', 'N/A')} / 100 "
            f"(Grade: {score.get('grade', 'N/A')} - {score.get('label', 'N/A')})",
            f"  Region cleanliness: {score.get('breakdown', {}).get('region_cleanliness', 0)} / 30",
            f"  Waste reduction:    {score.get('breakdown', {}).get('waste_reduction', 0)} / 30",
            f"  Carbon efficiency:  {score.get('breakdown', {}).get('carbon_efficiency', 0)} / 25",
            f"  Lambda hygiene:     {score.get('breakdown', {}).get('lambda_hygiene', 0)} / 15",
            "",
            "--- GREEN REGION RECOMMENDATION ---",
            green.get("message", "N/A"),
        ]

        return "\n".join(lines)

    def ask(self, question: str, report: dict, chat_history: list = None) -> str:
        """
        Answer a question using the infrastructure report as RAG context.
        Uses Groq for fast, reliable inference with generous free tier.
        """
        context = self.build_context(report)

        system_prompt = f"""You are an expert AWS cloud engineer and sustainability consultant.
You have access to a real-time scan of the user's AWS infrastructure shown below.
Answer questions accurately based on this data. Be specific — mention actual resource IDs,
costs, and numbers from the report. Keep answers concise and actionable.
If asked for recommendations, prioritize by cost savings and carbon impact.

{context}

## RESPONSE FORMAT REQUIREMENTS:
- Use clean bullet points (•) for lists, one item per line
- Use bold for key metrics (**value**)
- Group related items with sub-bullets (use -) 
- No verbose explanations unless explicitly requested
- Max 150 words for most responses
- Break long actionable steps into numbered lists
- Always include specific values/IDs when mentioning resources

Answer the user's question based on the infrastructure data above.
If the question is not related to their infrastructure, still answer helpfully as a cloud expert.
"""

        # Build conversation history for Groq (OpenAI-compatible format)
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        # Add chat history (last 6 messages)
        if chat_history:
            for msg in chat_history[-6:]:
                messages.append({
                    "role": msg["role"],  # "user" or "assistant"
                    "content": msg["content"]
                })

        # Add current question
        messages.append({
            "role": "user",
            "content": question
        })

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=1024,
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"AI advisor error: {str(e)}"
