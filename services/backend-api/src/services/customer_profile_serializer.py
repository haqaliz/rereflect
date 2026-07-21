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

    Usage trend (trend-detection-and-health aspect)
        usage_trend_state, usage_trend_pct — both None when no
        customer_usage row exists for this customer.

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
        # ── Usage trend (trend-detection-and-health aspect) ──────────────────
        **_read_usage_trend_fields(record, db),
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


def _read_usage_trend_fields(record: CustomerHealth, db) -> dict:
    """Read usage-trend fields (trend-detection-and-health aspect) for this
    customer; both None when unavailable.

    Contract: this function NEVER raises. Same SAVEPOINT pattern as
    _read_crm_fields — a missing customer_usage table/row (or a raising
    query) cannot abort the outer transaction and must not 500 the endpoint
    (AC 16).

    Stated choice (AC 16's "or NULL, per the tech-plan's stated choice"): a
    customer with NO customer_usage row returns usage_trend_state = None
    (not the string "insufficient_history") — mirroring how usage_component
    is already None (not 50) when uncollected, rather than the neutral
    fallback value used elsewhere. A row that exists always carries a real
    state string (server_default 'insufficient_history'), so None here
    unambiguously means "no rollup at all", distinct from "rollup exists but
    hasn't warmed up yet".
    """
    trend_state = None
    trend_pct = None

    if db is not None:
        from sqlalchemy import text
        sp = db.begin_nested()  # SAVEPOINT — isolates this read from the outer transaction
        try:
            row = db.execute(
                text(
                    "SELECT usage_trend_state, usage_trend_pct FROM customer_usage "
                    "WHERE organization_id = :org_id AND customer_email = :email "
                    "ORDER BY updated_at DESC LIMIT 1"
                ),
                {"org_id": record.organization_id, "email": record.customer_email},
            ).fetchone()
            sp.commit()
            if row is not None:
                trend_state, trend_pct = row[0], row[1]
        except Exception:
            # Table does not exist yet or any other DB error — roll back only
            # the SAVEPOINT so the outer transaction remains usable (avoids
            # PendingRollbackError on the next query in the same request).
            try:
                sp.rollback()
            except Exception:
                pass
            trend_state, trend_pct = None, None

    return {
        "usage_trend_state": trend_state,
        "usage_trend_pct": float(trend_pct) if trend_pct is not None else None,
    }
