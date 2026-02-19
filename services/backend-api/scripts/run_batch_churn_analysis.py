"""
Batch LLM churn analysis for at-risk customers (health_score < 40).

Reads all CustomerHealth records with health_score < 40, fetches their recent
feedback, calls OpenAI with the same CHURN_ANALYSIS_PROMPT used by the worker,
and writes results back to the CustomerHealth.llm_analysis field.

Requires OPENAI_API_KEY to be set in the environment or the org's BYOK key.
A small delay is added between calls to avoid rate limiting.

Run:
    cd services/backend-api && source venv/bin/activate && python scripts/run_batch_churn_analysis.py
"""
import sys
import os
import json
import time
import logging
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.database.session import SessionLocal
from src.models.customer_health import CustomerHealth
from src.models.feedback import FeedbackItem
from src.models.organization import Organization

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Delay between LLM calls to avoid rate limiting (seconds)
CALL_DELAY = 1.5

CHURN_ANALYSIS_PROMPT = """You are a customer success analyst. Analyze the following feedback data for a single customer and provide a concise churn risk analysis.

Customer email: {customer_email}
Health score: {health_score}/100 (lower = higher risk)
Risk level: {risk_level}
Component scores:
- Churn risk: {churn_risk_component}/100
- Sentiment: {sentiment_component}/100
- Resolution time: {resolution_component}/100
- Feedback frequency: {frequency_component}/100

Recent feedback items (most recent first):
{feedback_items}

Return ONLY valid JSON with this structure:
{{
  "analysis": "2-3 sentence summary of why this customer is at risk and what the key drivers are",
  "recommended_actions": ["action 1", "action 2", "action 3"],
  "risk_drivers": ["driver 1", "driver 2"],
  "estimated_urgency": "immediate" | "this_week" | "this_month"
}}"""


def _get_openai_client(api_key: Optional[str] = None):
    """Build an OpenAI client using the provided key or OPENAI_API_KEY env var."""
    try:
        from openai import OpenAI
    except ImportError:
        print("openai package not installed. Run: pip install openai")
        return None

    key = api_key or os.environ.get("OPENAI_API_KEY", "")
    if not key:
        return None
    return OpenAI(api_key=key)


def _call_churn_analysis(
    client,
    customer: CustomerHealth,
    feedback_texts: list,
    model: str = "gpt-4o-mini",
) -> Optional[str]:
    """Call OpenAI and return a formatted analysis string, or None on failure."""
    formatted = "\n".join(
        f'{i+1}. "{text[:400]}"' for i, text in enumerate(feedback_texts[:20])
    )

    prompt = CHURN_ANALYSIS_PROMPT.format(
        customer_email=customer.customer_email,
        health_score=customer.health_score,
        risk_level=customer.risk_level,
        churn_risk_component=customer.churn_risk_component or 50,
        sentiment_component=customer.sentiment_component or 50,
        resolution_component=customer.resolution_component or 50,
        frequency_component=customer.frequency_component or 50,
        feedback_items=formatted,
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=500,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            return None

        result = json.loads(content)

        analysis_parts = [str(result.get("analysis", ""))[:500]]
        actions = result.get("recommended_actions", [])
        if actions:
            analysis_parts.append("Actions: " + "; ".join(str(a)[:200] for a in actions[:5]))
        urgency = result.get("estimated_urgency")
        if urgency:
            analysis_parts.append(f"Urgency: {urgency}")

        return " | ".join(analysis_parts)

    except Exception as e:
        logger.error(f"OpenAI call failed for {customer.customer_email}: {e}")
        return None


def main():
    db = SessionLocal()
    try:
        # Build a map of org_id -> org for BYOK key lookup
        orgs = {org.id: org for org in db.query(Organization).all()}

        # Find all at-risk customers across all orgs
        at_risk = (
            db.query(CustomerHealth)
            .filter(
                CustomerHealth.health_score < 40,
                CustomerHealth.is_archived == False,
            )
            .order_by(CustomerHealth.health_score.asc())
            .all()
        )

        if not at_risk:
            print("No at-risk customers (health_score < 40) found.")
            return

        print(f"Found {len(at_risk)} at-risk customers to analyze")

        # Detect system-level API key
        system_key = os.environ.get("OPENAI_API_KEY", "")

        analyzed = 0
        skipped = 0
        errors = 0

        for idx, customer in enumerate(at_risk, 1):
            org = orgs.get(customer.organization_id)

            # Prefer org BYOK key, fall back to system key
            org_key = (org.openai_api_key if org else None) or system_key
            client = _get_openai_client(org_key)

            if client is None:
                print(f"  [{idx}/{len(at_risk)}] SKIP {customer.customer_email} — no OpenAI key available")
                skipped += 1
                continue

            # Fetch recent feedback for this customer
            recent_feedback = (
                db.query(FeedbackItem)
                .filter(
                    FeedbackItem.organization_id == customer.organization_id,
                    FeedbackItem.customer_email == customer.customer_email,
                )
                .order_by(FeedbackItem.created_at.desc())
                .limit(20)
                .all()
            )

            if len(recent_feedback) < 2:
                print(f"  [{idx}/{len(at_risk)}] SKIP {customer.customer_email} — insufficient feedback ({len(recent_feedback)} items)")
                skipped += 1
                continue

            feedback_texts = [f.text for f in recent_feedback]

            model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
            result = _call_churn_analysis(client, customer, feedback_texts, model=model)

            if result:
                customer.llm_analysis = result
                customer.llm_analyzed_at = datetime.utcnow()
                db.commit()
                analyzed += 1
                print(
                    f"  [{idx}/{len(at_risk)}] OK  {customer.customer_email} "
                    f"(score={customer.health_score}, org={customer.organization_id})"
                )
                print(f"         {result[:120]}...")
            else:
                errors += 1
                print(f"  [{idx}/{len(at_risk)}] ERR {customer.customer_email} — LLM returned no result")

            # Avoid rate limiting
            if idx < len(at_risk):
                time.sleep(CALL_DELAY)

        print(
            f"\nDone. analyzed={analyzed}, skipped={skipped}, errors={errors} "
            f"(total={len(at_risk)})"
        )

    except Exception as e:
        db.rollback()
        print(f"Fatal error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
