"""
Shared Customer 360 profile serializer.

Extracted from ``routes/customers.py:get_customer_profile`` so that the
v1 route and the public REST API surface share exactly one field-mapping
implementation.  Neither can drift from the other.

TODO: open question from PRD — redact LLM free-text in the public profile?
Default: NO (operator's own self-hosted data).  Revisit if a consumer objects.
"""
from __future__ import annotations

from typing import Optional

from src.models.customer_health import CustomerHealth


def serialize_customer_profile(record: CustomerHealth, db=None) -> dict:
    """Build a Customer 360 profile dict from a ``CustomerHealth`` ORM row.

    Returns all *non-plan-gated* profile fields.  The caller must inject
    plan-gated fields on top (e.g. ``llm_actions`` for Business+ plans via a
    separate DB query).

    Fields returned
    ---------------
    Core
        customer_email, customer_name, health_score, risk_level,
        confidence_level, feedback_count, last_feedback_at, is_archived,
        created_at, segment (rule-based, nullable — customer-segments feature)

    Components (5 including usage)
        churn_risk_component, sentiment_component, resolution_component,
        frequency_component, usage_component

    Churn prediction
        churn_probability, churn_probability_low, churn_probability_high,
        time_to_churn_bucket

    LLM analysis
        llm_analysis_summary, llm_recommended_actions, llm_risk_drivers,
        llm_urgency, llm_analysis_type, llm_analyzed_at, llm_analysis
    """
    analysis_data: dict = record.llm_analysis_data or {}

    llm_analysis_summary: Optional[str] = analysis_data.get("analysis")
    llm_recommended_actions = analysis_data.get("recommended_actions")
    llm_risk_drivers = analysis_data.get("risk_drivers")
    llm_urgency: Optional[str] = analysis_data.get("estimated_urgency")
    llm_analysis_type: Optional[str] = analysis_data.get("analysis_type")

    def _float_or_none(val) -> Optional[float]:
        """Coerce Decimal / Numeric column values to float safely."""
        return float(val) if val is not None else None

    return {
        # ── Core ──────────────────────────────────────────────────────────────
        "customer_email": record.customer_email,
        "customer_name": record.customer_name,
        "health_score": record.health_score,
        "risk_level": record.risk_level,
        "confidence_level": record.confidence_level or "low",
        "feedback_count": record.feedback_count,
        "last_feedback_at": record.last_feedback_at,
        "is_archived": record.is_archived or False,
        "created_at": record.created_at,
        "segment": record.segment,
        # ── Components ────────────────────────────────────────────────────────
        "churn_risk_component": record.churn_risk_component or 50,
        "sentiment_component": record.sentiment_component or 50,
        "resolution_component": record.resolution_component or 50,
        "frequency_component": record.frequency_component or 50,
        "usage_component": record.usage_component,          # nullable: None = not collected
        # ── Churn prediction ─────────────────────────────────────────────────
        "churn_probability": _float_or_none(record.churn_probability),
        "churn_probability_low": _float_or_none(record.churn_probability_low),
        "churn_probability_high": _float_or_none(record.churn_probability_high),
        "time_to_churn_bucket": record.time_to_churn_bucket,
        # ── LLM analysis ─────────────────────────────────────────────────────
        "llm_analysis_summary": llm_analysis_summary,
        "llm_recommended_actions": llm_recommended_actions,
        "llm_risk_drivers": llm_risk_drivers,
        "llm_urgency": llm_urgency,
        "llm_analysis_type": llm_analysis_type,
        "llm_analyzed_at": record.llm_analyzed_at,
        "llm_analysis": record.llm_analysis,        # legacy text field
        # ── CRM enrichment (HubSpot / Salesforce) ────────────────────────────
        **_read_crm_fields(record, db),
    }


def _read_crm_fields(record: CustomerHealth, db) -> dict:
    """Read CRM enrichment fields for this customer; all None when unavailable.

    Contract: this function NEVER raises. It uses a SAVEPOINT so a missing
    crm_enrichment table cannot abort the outer SQLAlchemy transaction and
    cause PendingRollbackError on subsequent queries (mirrors the SAVEPOINT
    pattern in _compute_crm_component in health_score_service.py).
    """
    crm = None
    if db is not None:
        sp = db.begin_nested()  # SAVEPOINT — isolates this read from the outer transaction
        try:
            from src.models.crm_enrichment import CrmEnrichment
            crm = db.query(CrmEnrichment).filter(
                CrmEnrichment.organization_id == record.organization_id,
                CrmEnrichment.customer_email == record.customer_email,
            ).first()
            sp.commit()
        except Exception:
            # Table does not exist yet or any other DB error — roll back only the
            # SAVEPOINT so the outer transaction remains usable (avoids
            # PendingRollbackError on the next query in the same request).
            try:
                sp.rollback()
            except Exception:
                pass
            crm = None

    def _f(val):
        return float(val) if val is not None else None

    return {
        "crm_company_name":    crm.company_name    if crm else None,
        "crm_lifecycle_stage": crm.lifecycle_stage if crm else None,
        "crm_arr":             _f(crm.arr)          if crm else None,
        "crm_renewal_date":    crm.renewal_date    if crm else None,
        "crm_deal_name":       crm.deal_name       if crm else None,
        "crm_deal_stage":      crm.deal_stage      if crm else None,
        "crm_deal_amount":     _f(crm.deal_amount)  if crm else None,
        "crm_provider":        crm.provider        if crm else None,
    }
