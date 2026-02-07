"""
OpenAI integration for LLM-powered feedback categorization.
Supports system-wide API key and per-org BYOK (Bring Your Own Key).
"""

import json
import logging
from typing import Optional

from openai import OpenAI, APIError, RateLimitError, APITimeoutError

from src.config import settings

logger = logging.getLogger(__name__)

# Built-in pain point categories (12)
PAIN_POINT_CATEGORIES = [
    "security_breach", "data_loss", "payment_issue", "system_crash",
    "authentication", "functionality_broken", "performance", "usability",
    "compatibility", "missing_feature", "documentation", "cosmetic",
]

# Built-in feature request categories (10)
FEATURE_REQUEST_CATEGORIES = [
    "core_functionality", "automation", "integration", "reporting",
    "customization", "collaboration", "export_import", "mobile",
    "notifications", "ui_enhancement",
]

# Built-in urgent categories (10)
URGENT_CATEGORIES = [
    "service_outage", "data_breach", "payment_failure", "data_corruption",
    "account_locked", "critical_bug", "billing_dispute", "churn_risk",
    "compliance", "reputation_risk",
]

CATEGORIZATION_PROMPT = """You are a customer feedback analyst. Analyze the following feedback and return a JSON object.

Available pain point categories: {pain_point_categories}
Available feature request categories: {feature_request_categories}
Available urgent categories: {urgent_categories}
{custom_categories_section}

Return ONLY valid JSON with these fields:
{{
  "sentiment_label": "positive" | "neutral" | "negative",
  "sentiment_score": float (-1.0 to 1.0),
  "is_urgent": boolean,
  "pain_point_category": string | null (from available list),
  "pain_point_severity": "critical" | "major" | "moderate" | "minor" | "trivial" | null,
  "feature_request_category": string | null (from available list),
  "feature_request_priority": "high" | "medium" | "low" | null,
  "urgent_category": string | null (from available list, only if is_urgent),
  "urgent_response_time": "immediate" | "1_hour" | "4_hours" | "24_hours" | null,
  "churn_risk_score": integer (0-100, likelihood customer will churn),
  "suggested_action": string (1-2 sentence recommendation),
  "tags": array of strings (max 5 relevant tags),
  "confidence": float (0.0-1.0)
}}

Feedback text:
\"\"\"{feedback_text}\"\"\""""


def _get_client(org_api_key: Optional[str] = None) -> Optional[OpenAI]:
    """Get OpenAI client, preferring org BYOK key over system key."""
    api_key = org_api_key or settings.openai_api_key
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def categorize_feedback(
    text: str,
    custom_categories: Optional[list[dict]] = None,
    org_api_key: Optional[str] = None,
) -> Optional[dict]:
    """
    Use GPT to categorize a feedback item.

    Args:
        text: The feedback text to analyze.
        custom_categories: List of custom category dicts with {name, category_type}.
        org_api_key: Optional BYOK API key for this organization.

    Returns:
        Parsed JSON dict with categorization results, or None on failure.
    """
    client = _get_client(org_api_key)
    if not client:
        logger.warning("No OpenAI API key configured, skipping LLM categorization")
        return None

    # Build custom categories section
    custom_section = ""
    if custom_categories:
        custom_pain = [c["name"] for c in custom_categories if c["category_type"] == "pain_point"]
        custom_feature = [c["name"] for c in custom_categories if c["category_type"] == "feature_request"]
        custom_general = [c["name"] for c in custom_categories if c["category_type"] == "general"]
        parts = []
        if custom_pain:
            parts.append(f"Additional custom pain point categories: {', '.join(custom_pain)}")
        if custom_feature:
            parts.append(f"Additional custom feature request categories: {', '.join(custom_feature)}")
        if custom_general:
            parts.append(f"Additional general categories (can be used for any field): {', '.join(custom_general)}")
        if parts:
            custom_section = "\n" + "\n".join(parts)

    prompt = CATEGORIZATION_PROMPT.format(
        pain_point_categories=", ".join(PAIN_POINT_CATEGORIES),
        feature_request_categories=", ".join(FEATURE_REQUEST_CATEGORIES),
        urgent_categories=", ".join(URGENT_CATEGORIES),
        custom_categories_section=custom_section,
        feedback_text=text[:2000],  # Truncate very long feedback
    )

    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        if not content:
            logger.error("OpenAI returned empty content")
            return None

        result = json.loads(content)

        # Validate and clamp churn_risk_score
        if "churn_risk_score" in result:
            score = result["churn_risk_score"]
            if isinstance(score, (int, float)):
                result["churn_risk_score"] = max(0, min(100, int(score)))
            else:
                result["churn_risk_score"] = 0

        # Validate confidence
        if "confidence" in result:
            conf = result["confidence"]
            if isinstance(conf, (int, float)):
                result["confidence"] = max(0.0, min(1.0, float(conf)))
            else:
                result["confidence"] = 0.5

        # Validate tags is a list
        if "tags" not in result or not isinstance(result["tags"], list):
            result["tags"] = []
        result["tags"] = result["tags"][:5]

        return result

    except (APIError, RateLimitError, APITimeoutError) as e:
        logger.error(f"OpenAI API error: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OpenAI response as JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in OpenAI categorization: {e}")
        return None


INSIGHTS_PROMPT = """You are a customer feedback analyst. Analyze the following batch of customer feedback items and generate 3-5 actionable insights for the product team.

Each insight should identify a pattern, trend, or actionable recommendation based on the feedback.

Feedback items:
{feedback_items}

Return ONLY valid JSON with this structure:
{{
  "insights": [
    {{
      "title": "Short insight title (max 10 words)",
      "description": "Detailed explanation with specific evidence from feedback (2-3 sentences)",
      "category": "pain_point" | "feature_request" | "positive_trend" | "churn_risk" | "opportunity",
      "priority": "high" | "medium" | "low"
    }}
  ]
}}"""


def generate_insights(
    feedback_texts: list[str],
    org_api_key: str | None = None,
) -> list[dict] | None:
    """
    Use GPT to generate weekly insights from a batch of feedback items.

    Args:
        feedback_texts: List of feedback text strings to analyze.
        org_api_key: Optional BYOK API key for this organization.

    Returns:
        List of insight dicts, or None on failure.
    """
    client = _get_client(org_api_key)
    if not client:
        logger.warning("No OpenAI API key configured, skipping insights generation")
        return None

    # Format feedback items with numbering
    formatted = "\n".join(f"{i+1}. \"{text[:500]}\"" for i, text in enumerate(feedback_texts[:50]))

    prompt = INSIGHTS_PROMPT.format(feedback_items=formatted)

    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1000,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        if not content:
            logger.error("OpenAI returned empty content for insights")
            return None

        result = json.loads(content)
        insights = result.get("insights", [])

        # Validate structure
        validated = []
        for insight in insights[:5]:
            if isinstance(insight, dict) and "title" in insight and "description" in insight:
                validated.append({
                    "title": str(insight.get("title", ""))[:100],
                    "description": str(insight.get("description", ""))[:500],
                    "category": insight.get("category", "opportunity"),
                    "priority": insight.get("priority", "medium"),
                })

        return validated if validated else None

    except (APIError, RateLimitError, APITimeoutError) as e:
        logger.error(f"OpenAI API error generating insights: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OpenAI insights response: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error generating insights: {e}")
        return None
