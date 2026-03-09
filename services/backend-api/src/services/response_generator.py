"""
Response Generator Service.

Handles:
- Variable resolution: replace {{var}} placeholders in template bodies
- AI response generation: build LLM prompt from feedback context, call the model
"""

import json
import logging
import os
import re
from typing import Optional

import httpx

from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.models.user import User

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
DEFAULT_MODEL = "gpt-4o-mini"
MAX_TOKENS = 500
TEMPERATURE = 0.7
TIMEOUT_SECONDS = 15


# ============================================================================
# Variable resolution
# ============================================================================

def resolve_variables(
    template_body: str,
    feedback: FeedbackItem,
    org: Organization,
    user: Optional[User] = None,
) -> str:
    """
    Replace {{variable}} placeholders in a template body with actual values.

    Available variables:
      customer_name, customer_email, company_name, feedback_excerpt,
      category, sentiment, source, product_name, agent_name,
      support_email, health_score, risk_level, churn_factors
    """
    # Build source metadata helpers
    source_meta = feedback.source_metadata or {}

    # Resolve each variable with a best-effort fallback to empty string
    customer_name = (
        source_meta.get("author_name")
        or source_meta.get("customer_name")
        or ""
    )
    customer_email = feedback.customer_email or ""
    company_name = source_meta.get("company_name") or (org.name if org else "")
    feedback_excerpt = (feedback.text or "")[:200]
    category = (
        feedback.pain_point_category
        or feedback.feature_request_category
        or feedback.urgent_category
        or ""
    )
    sentiment = feedback.sentiment_label or ""
    source = feedback.source or ""
    product_name = (org.product_name_display if org else None) or "Rereflect"
    agent_name = f"{user.name}" if (user and hasattr(user, "name") and user.name) else (user.email.split("@")[0] if user else "")
    support_email = (org.support_email_display if org else None) or ""
    health_score = str(feedback.churn_risk_score) if feedback.churn_risk_score is not None else ""
    risk_level = _risk_level_from_score(feedback.churn_risk_score)
    churn_factors = _format_churn_factors(feedback.churn_risk_factors)

    variable_map = {
        "customer_name": customer_name,
        "customer_email": customer_email,
        "company_name": company_name,
        "feedback_excerpt": feedback_excerpt,
        "category": category,
        "sentiment": sentiment,
        "source": source,
        "product_name": product_name,
        "agent_name": agent_name,
        "support_email": support_email,
        "health_score": health_score,
        "risk_level": risk_level,
        "churn_factors": churn_factors,
    }

    def _replace(match: re.Match) -> str:
        key = match.group(1).strip()
        return variable_map.get(key, "")

    return re.sub(r"\{\{(\w+)\}\}", _replace, template_body)


def _risk_level_from_score(score: Optional[int]) -> str:
    if score is None:
        return ""
    if score >= 70:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"


def _format_churn_factors(factors: Optional[dict]) -> str:
    if not factors:
        return ""
    top = sorted(factors.items(), key=lambda kv: kv[1].get("score", 0) if isinstance(kv[1], dict) else 0, reverse=True)[:3]
    return ", ".join(k for k, _ in top)


# ============================================================================
# AI response generation
# ============================================================================

async def generate_response(
    feedback: FeedbackItem,
    org: Organization,
    user: Optional[User],
    tone: Optional[str] = None,
) -> dict:
    """
    Build an LLM prompt from the feedback context and call OpenAI to generate
    a response.

    Returns:
        {
            "response_text": str,
            "tokens_used": int,
        }

    Raises RuntimeError on LLM failure (caller should handle).
    """
    resolved_tone = tone or (org.default_tone if org else None) or "professional"
    product_name = (org.product_name_display if org else None) or "Rereflect"
    source_meta = feedback.source_metadata or {}
    customer_name = source_meta.get("author_name") or source_meta.get("customer_name") or "there"
    customer_email = feedback.customer_email or "unknown"
    agent_name_str = (
        f"{user.name}"
        if (user and hasattr(user, "name") and user.name)
        else (user.email.split("@")[0] if user else "Support Agent")
    )
    category = (
        feedback.pain_point_category
        or feedback.feature_request_category
        or feedback.urgent_category
        or "General"
    )

    # Construct system prompt
    brand_voice_section = ""
    if org and org.brand_voice:
        brand_voice_section = f"\nBrand voice guidelines:\n{org.brand_voice}\n"

    system_prompt = (
        f"You are a customer support AI for {product_name}. "
        f"Generate a response to customer feedback."
        f"{brand_voice_section}\n"
        f"Tone: {resolved_tone}\n\n"
        "Instructions:\n"
        "- Write a natural, human-sounding response\n"
        "- Address the specific feedback content\n"
        "- Match the requested tone\n"
        "- Keep it concise (3-5 short paragraphs max)\n"
        "- Do not use placeholder text like [insert X]\n"
        "- Resolve any known information (customer name, product name)\n"
        "- Sign off with the agent's name\n"
        "- Do not make promises about timelines unless the feedback is about a known resolved issue"
    )

    user_message = (
        f"Context:\n"
        f"- Feedback: \"{feedback.text}\"\n"
        f"- Category: {category}\n"
        f"- Sentiment: {feedback.sentiment_label or 'unknown'}\n"
        f"- Source: {feedback.source or 'unknown'}\n"
        f"- Customer: {customer_name} ({customer_email})\n\n"
        f"Agent name: {agent_name_str}\n"
        f"Product name: {product_name}"
    )

    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not configured")

    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as http_client:
        resp = await http_client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": DEFAULT_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                "max_tokens": MAX_TOKENS,
                "temperature": TEMPERATURE,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    response_text = data["choices"][0]["message"]["content"].strip()
    tokens_used = data.get("usage", {}).get("total_tokens", 0)

    return {
        "response_text": response_text,
        "tokens_used": tokens_used,
    }
