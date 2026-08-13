"""
Pydantic schemas for GET /api/v1/settings/ai/churn/label-gate
(churn-label-gate-study aspect 2, M5.3 disclosure layer).

Mirrors the eval_churn_label_gate.py script's committed JSON artifact
(services/backend-api/eval_results/churn_label_gate.json) 1:1 so the
route's parse-or-degrade handler is a thin pass-through.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class GateCurvePoint(BaseModel):
    """One label-volume step of the challenger-vs-incumbent learning curve.

    macro_f1_delta is challenger minus incumbent macro-F1 on a leakage-free
    stratified holdout, averaged over the pooled (scenario family, simulation)
    draws at that volume; delta_ci_low/high are the empirical 2.5/97.5
    percentiles across those draws; promotion_rate is the fraction of draws
    where the challenger cleared the +0.02 macro-F1 promotion bar (M5.2 rule).
    """

    label_volume: int
    challenger_macro_f1: float
    incumbent_macro_f1: float
    macro_f1_delta: float
    delta_ci_low: float
    delta_ci_high: float
    promotion_rate: float


class FidelitySensitivity(BaseModel):
    """R3 dimension: how the learning curve moves when `missing_fraction` of
    feature rows have no snapshots at label time and are reconstructed via the
    documented defaults (the sparse-history case). crossover_label_volume is
    the crossover under that degradation (None if it never crosses)."""

    missing_fraction: float
    crossover_label_volume: Optional[int] = None
    curves: List[GateCurvePoint] = []


class ChurnLabelGateResponse(BaseModel):
    """Response for GET /api/v1/settings/ai/churn/label-gate.

    has_results=False (with every other field null/absent) is the honest
    "study not run yet" state — never a 404/500 (mirrors sentiment_accuracy's
    never-raises contract). No organization_id scoping: the artifact is a
    single, global, offline, reproducible snapshot, not a per-org metric.
    """

    has_results: bool
    artifact_version: Optional[str] = None
    generated_at: Optional[datetime] = None
    verdict: Optional[str] = None
    target: Optional[int] = None
    method: Optional[str] = None
    n_simulations: Optional[int] = None
    crossover_label_volume: Optional[int] = None
    fidelity_sensitivity: Optional[FidelitySensitivity] = None
    honest_limits: Optional[List[str]] = None
    curves: Optional[List[GateCurvePoint]] = None
