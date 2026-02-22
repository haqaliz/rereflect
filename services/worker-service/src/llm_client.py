"""
LLM client — provider-agnostic replacement for openai_client.py.

Provides the same function signatures as openai_client.py but routes calls
through the LLM factory with per-org configuration, BYOK key support,
fallback chains, and usage logging.
"""

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from src.llm.prompts import (
    CATEGORIZATION_PROMPT,
    CHURN_ANALYSIS_PROMPT,
    RETENTION_ANALYSIS_PROMPT,
    GROWTH_ANALYSIS_PROMPT,
    INSIGHTS_PROMPT,
    PAIN_POINT_CATEGORIES,
    FEATURE_REQUEST_CATEGORIES,
    URGENT_CATEGORIES,
)
from src.llm.types import LLMRequest
from src.llm.org_resolver import call_llm_for_org

logger = logging.getLogger(__name__)

# Analysis prompt map for multi-tier customer analysis
_ANALYSIS_PROMPTS = {
    "churn_risk": CHURN_ANALYSIS_PROMPT,
    "retention": RETENTION_ANALYSIS_PROMPT,
    "growth_opportunity": GROWTH_ANALYSIS_PROMPT,
}


def categorize_feedback(
    text: str,
    custom_categories: Optional[list] = None,
    org_id: Optional[int] = None,
    db: Optional[Session] = None,
    # Legacy compat params (ignored — use org_id + db instead)
    org_api_key: Optional[str] = None,
) -> Optional[dict]:
    """
    Categorize a feedback item using the org's configured LLM provider.

    Args:
        text: The feedback text to analyze.
        custom_categories: List of custom category dicts with {name, category_type}.
        org_id: Organization ID (needed to look up org AI config).
        db: Database session (needed to look up org AI config and BYOK key).
        org_api_key: Deprecated — ignored. Use org_id + db.

    Returns:
        Parsed JSON dict with categorization results, or None on failure.
    """
    if org_id is None or db is None:
        logger.warning("categorize_feedback called without org_id/db — LLM categorization skipped")
        return None

    from src.models import OrgAIConfig

    config = db.query(OrgAIConfig).filter_by(organization_id=org_id).first()
    provider = config.default_provider if config else "openai"
    model = config.model_categorization if config else "gpt-4o-mini"

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
        feedback_text=text[:2000],
    )

    request = LLMRequest(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=500,
        json_mode=True,
    )

    try:
        response = call_llm_for_org(
            org_id=org_id,
            task_type="categorization",
            request=request,
            provider=provider,
            model=model,
            db=db,
        )

        if response is None:
            return None

        result = json.loads(response.content)

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

        # Store the LLM provider/model used
        result["_llm_provider"] = response.provider
        result["_llm_model"] = response.model

        return result

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM categorization response as JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in LLM categorization: {e}")
        return None


def generate_insights(
    feedback_texts: list,
    org_id: Optional[int] = None,
    db: Optional[Session] = None,
    # Legacy compat param (ignored)
    org_api_key: Optional[str] = None,
) -> Optional[list]:
    """
    Generate weekly insights from a batch of feedback items.

    Args:
        feedback_texts: List of feedback text strings to analyze.
        org_id: Organization ID (needed to look up org AI config).
        db: Database session.
        org_api_key: Deprecated — ignored.

    Returns:
        List of insight dicts, or None on failure.
    """
    if org_id is None or db is None:
        logger.warning("generate_insights called without org_id/db — skipped")
        return None

    from src.models import OrgAIConfig

    config = db.query(OrgAIConfig).filter_by(organization_id=org_id).first()
    provider = config.default_provider if config else "openai"
    model = config.model_insights if config else "gpt-4o-mini"

    formatted = "\n".join(f'{i+1}. "{text[:500]}"' for i, text in enumerate(feedback_texts[:50]))
    prompt = INSIGHTS_PROMPT.format(feedback_items=formatted)

    request = LLMRequest(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=1000,
        json_mode=True,
    )

    try:
        response = call_llm_for_org(
            org_id=org_id,
            task_type="insights",
            request=request,
            provider=provider,
            model=model,
            db=db,
        )

        if response is None:
            return None

        result = json.loads(response.content)
        insights = result.get("insights", [])

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

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM insights response as JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error generating insights: {e}")
        return None


def generate_customer_analysis(
    analysis_type: str,
    customer_email: str,
    health_score: int,
    risk_level: str,
    churn_risk_component: int,
    sentiment_component: int,
    resolution_component: int,
    frequency_component: int,
    feedback_texts: list,
    org_id: Optional[int] = None,
    db: Optional[Session] = None,
    # Legacy compat param (ignored)
    org_api_key: Optional[str] = None,
) -> Optional[dict]:
    """
    Run customer analysis (churn_risk, retention, or growth_opportunity).

    Args:
        analysis_type: "churn_risk", "retention", or "growth_opportunity"
        org_id: Organization ID.
        db: Database session.
        org_api_key: Deprecated — ignored.

    Returns:
        Dict with analysis, recommended_actions, risk_drivers, estimated_urgency.
    """
    if org_id is None or db is None:
        logger.warning("generate_customer_analysis called without org_id/db — skipped")
        return None

    prompt_template = _ANALYSIS_PROMPTS.get(analysis_type)
    if not prompt_template:
        logger.error(f"Unknown analysis type: {analysis_type}")
        return None

    from src.models import OrgAIConfig

    config = db.query(OrgAIConfig).filter_by(organization_id=org_id).first()
    provider = config.default_provider if config else "openai"
    model = config.model_analysis if config else "gpt-4o-mini"

    formatted = "\n".join(f'{i+1}. "{text[:400]}"' for i, text in enumerate(feedback_texts[:20]))

    prompt = prompt_template.format(
        customer_email=customer_email,
        health_score=health_score,
        risk_level=risk_level,
        churn_risk_component=churn_risk_component,
        sentiment_component=sentiment_component,
        resolution_component=resolution_component,
        frequency_component=frequency_component,
        feedback_items=formatted,
    )

    request = LLMRequest(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=500,
        json_mode=True,
    )

    try:
        response = call_llm_for_org(
            org_id=org_id,
            task_type="analysis",
            request=request,
            provider=provider,
            model=model,
            db=db,
        )

        if response is None:
            return None

        result = json.loads(response.content)

        structured = {
            "analysis": str(result.get("analysis", ""))[:500],
            "recommended_actions": [str(a)[:200] for a in result.get("recommended_actions", [])[:5]],
            "risk_drivers": [str(d)[:200] for d in result.get("risk_drivers", [])[:5]],
            "estimated_urgency": result.get("estimated_urgency", "this_month"),
            "analysis_type": analysis_type,
        }

        raw_response = {
            "model": response.model,
            "provider": response.provider,
            "raw_content": response.content,
            "usage": {
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
            },
        }

        return {**structured, "_raw_response": raw_response}

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM {analysis_type} response as JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in {analysis_type} analysis: {e}")
        return None


# Legacy function aliases for backward compatibility during transition
def generate_churn_analysis(
    customer_email: str,
    health_score: int,
    risk_level: str,
    churn_risk_component: int,
    sentiment_component: int,
    resolution_component: int,
    frequency_component: int,
    feedback_texts: list,
    org_id: Optional[int] = None,
    db: Optional[Session] = None,
    org_api_key: Optional[str] = None,
) -> Optional[dict]:
    """Backward-compatible wrapper around generate_customer_analysis."""
    return generate_customer_analysis(
        analysis_type="churn_risk",
        customer_email=customer_email,
        health_score=health_score,
        risk_level=risk_level,
        churn_risk_component=churn_risk_component,
        sentiment_component=sentiment_component,
        resolution_component=resolution_component,
        frequency_component=frequency_component,
        feedback_texts=feedback_texts,
        org_id=org_id,
        db=db,
    )
