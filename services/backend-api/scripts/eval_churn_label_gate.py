"""
Offline churn label-gate study harness (M5.3, aspect 2 — churn-label-gate-study).

Re-derives the per-org churn-label activation gate (CHURN_LABEL_TARGET, currently
500 in src/config/readiness_thresholds.py) by simulating per-org churn datasets at
increasing label volumes and measuring when a per-org logistic challenger reliably
beats the incumbent heuristic on a leakage-free holdout.

DISCLOSURE, NOT A GATE (eval harness convention, see scripts/eval_sentiment.py):
this script always exits 0. The numbers are reported honestly, never hidden, never
used to fail a build. The verdict in the artifact is computed by a deterministic
rule from the measured curves (see determine_verdict), not hand-fudged.

STATUS: The planned ML core (analysis-engine churn_classifier) does NOT exist yet.
The challenger here is a minimal inline stand-in — sklearn LogisticRegression, the
same model family the core will ship (churn-classifier-core/spec.md) — and the
feature vector is the core spec's fixed vector in stand-in form. This harness must
never import analyzer.churn_classifier (it does not exist) and must never touch a
database: simulation only, zero DB access.

Data-generating process (documented, seeded):
- Label volumes: [20, 50, 100, 200, 300, 500, 800, 1200].
- Each simulated org draws `volume` labeled customers. A customer's label is
  "churned within the 180-day observation window" (per-org churn semantics of
  _LABEL_WINDOW_DAYS=180, services/worker-service/src/services/calibration_refit.py).
  Churn rates are 10-20% by scenario family — the 15-25% band the PRD states.
- Two independent latent drivers per customer:
    w_feedback ~ N(0,1): feedback-visible health (drives the sentiment/resolution/
      frequency components, feedback_count, urgency_share, and — with only a small
      usage leak — churn_risk_component, which the service computes from
      feedback-derived signals);
    w_usage ~ N(0,1): product-usage engagement (drives usage_score,
      active_days_30d, login_count_30d, usage_trend_pct — telemetry the computed
      churn_risk_component does NOT see).
  The segment slug is a rule-based classification of a noisy blend of both
  drivers, exactly as production classifies customer_health_scores.segment.
- Hidden ground truth: churn log-odds = beta_feedback * w_feedback +
  beta_usage * w_usage + segment base rate + N(0, family_noise); family-level
  intercept is bisected so the cohort's mean churn rate hits the family target;
  y ~ Bernoulli(p). The harness never exposes the drivers or p to either model —
  both see only the noisy feature observations.
- This structure is the crux of the study: the incumbent sees only
  churn_risk_component (a partial, noisy observation of the drivers), while the
  challenger sees the full vector including usage telemetry and segment — so the
  challenger has a real asymptotic advantage, as the feature's premise assumes,
  and the learning curve shows where that advantage becomes measurable.
- Scenario families (vary signal strength and class balance):
    balanced-clean  : churn 20%, strong signal (beta scale 1.0, noise 0.6)
    balanced-noisy  : churn 20%, weak signal (beta scale 0.5, noise 1.2)
    imbalanced      : churn 10%, moderate signal (beta scale 0.75, noise 0.9)
- Challenger stand-in: sklearn LogisticRegression (L2, lbfgs) on a StandardScaler
  pipeline fit on the TRAIN split only; leakage-free stratified 30% holdout.
- Incumbent stand-in: the calibrated-heuristic shape — isotonic calibration of
  churn_risk_component fit on the SAME train split (the post-fix per-org
  calibration family; per PRD R5 both sides are scored on the same leakage-free
  holdout), with the identity shape (p = component/100) as the degenerate-fit
  fallback; label iff calibrated p >= 0.5, matching the M5.2 binary A/B rule.
- Reported per volume: mean challenger/incumbent macro-F1, mean delta
  (challenger - incumbent), empirical 2.5/97.5 percentiles of the pooled
  (family, simulation) deltas, and the M5.2 promotion rate (fraction of pooled
  runs where delta >= +0.02).
- Crossover: smallest volume where mean delta >= +0.02 AND promotion rate >= 0.5.
- R3 fidelity dimension: re-run the challenger with `--missing-fraction` of rows
  having no snapshots at label time (features reconstructed via the documented
  defaults the core feature builder uses: components -> 50, usage -> 0/50,
  trend -> 0, feedback -> 0, urgency -> 0, segment -> unsegmented) and report how
  the crossover moves. The gate must clear the harder of the two crossovers.

Usage:
    python scripts/eval_churn_label_gate.py \
        [--simulations 50] [--seed 20260814] [--missing-fraction 0.25] \
        [--output eval_results/churn_label_gate.json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Constants (kept at module level so the core is importable + unit-testable)
# ---------------------------------------------------------------------------

ARTIFACT_VERSION = "1"

# Label volumes studied (log-spaced across the plausible per-org range).
LABEL_VOLUMES = [20, 50, 100, 200, 300, 500, 800, 1200]

# M5.2 auto-promotion rule: challenger macro-F1 >= incumbent + 0.02.
PROMOTION_DELTA = 0.02

# Label window semantics for a churn label (calibration_refit._LABEL_WINDOW_DAYS).
LABEL_WINDOW_DAYS = 180

# The gate currently being re-derived (readiness_thresholds.CHURN_LABEL_TARGET).
CURRENT_TARGET = 500

# Default fraction of rows missing snapshots for the R3 fidelity dimension.
DEFAULT_MISSING_FRACTION = 0.25

# Segment slugs in the customer_health_scores column, minus the reference
# (happy_advocate) dropped to avoid the one-hot dummy trap.
SEGMENTS = ["dormant", "silent_churner", "at_risk", "new", "power_user"]
SEGMENT_DUMMY_COLUMNS = [f"segment_{s}" for s in SEGMENTS]

# Feature vector order — the stand-in for the planned core's fixed vector
# (churn-classifier-core/spec.md): 10 numeric snapshot features + 5 segment
# dummies. Column 0 is churn_risk_component, the only feature the incumbent uses.
FEATURE_COLUMNS = [
    "churn_risk_component",
    "sentiment_component",
    "resolution_component",
    "frequency_component",
    "usage_score",
    "active_days_30d",
    "login_count_30d",
    "usage_trend_pct",
    "feedback_count",
    "urgency_share",
] + SEGMENT_DUMMY_COLUMNS

N_FEATURES = len(FEATURE_COLUMNS)

# Base log-odds coefficients on the two latent drivers (scaled per family).
# feedback-weight and usage-weight: the hidden ground truth runs on the drivers;
# the models see only noisy feature observations of them.
_BETA_LATENT = {"feedback": 1.1, "usage": 0.9}

# How much of each latent driver leaks into the computed churn_risk_component:
# the component is built from feedback-derived signals with only a small usage
# leak (production's _compute_churn_component sees feedback, not usage telemetry).
_COMPONENT_LEAK = {"feedback": 0.55, "usage": 0.25}

# Documented reconstruction defaults for rows with no snapshots at label time
# (R3 fidelity dimension — mirrors the core feature builder's missing defaults).
_MISSING_DEFAULTS: Dict[str, float] = {
    "churn_risk_component": 50.0,
    "sentiment_component": 50.0,
    "resolution_component": 50.0,
    "frequency_component": 50.0,
    "usage_score": 50.0,
    "active_days_30d": 0.0,
    "login_count_30d": 0.0,
    "usage_trend_pct": 0.0,
    "feedback_count": 0.0,
    "urgency_share": 0.0,
}


@dataclass
class FamilySpec:
    """One scenario family: signal strength and class balance for the DGP."""

    name: str
    churn_rate: float
    signal_scale: float
    noise_std: float


FAMILIES = [
    FamilySpec("balanced-clean", churn_rate=0.20, signal_scale=1.0, noise_std=0.6),
    FamilySpec("balanced-noisy", churn_rate=0.20, signal_scale=0.45, noise_std=1.2),
    FamilySpec("imbalanced", churn_rate=0.10, signal_scale=0.75, noise_std=0.9),
]


@dataclass
class CurvePoint:
    """Aggregated learning-curve step at one label volume."""

    label_volume: int
    challenger_macro_f1: float
    incumbent_macro_f1: float
    macro_f1_delta: float
    delta_ci_low: float
    delta_ci_high: float
    promotion_rate: float

    def to_dict(self) -> dict:
        return {
            "label_volume": self.label_volume,
            "challenger_macro_f1": round(self.challenger_macro_f1, 4),
            "incumbent_macro_f1": round(self.incumbent_macro_f1, 4),
            "macro_f1_delta": round(self.macro_f1_delta, 4),
            "delta_ci_low": round(self.delta_ci_low, 4),
            "delta_ci_high": round(self.delta_ci_high, 4),
            "promotion_rate": round(self.promotion_rate, 4),
        }


# ---------------------------------------------------------------------------
# Data-generating process
# ---------------------------------------------------------------------------

def _seed_for(base_seed: int, volume_index: int, simulation_index: int, family_index: int) -> int:
    """Deterministic per-run seed. Layout keeps each volume's runs independent of
    the total simulation count, so changing --simulations never perturbs volumes
    already measured."""
    return base_seed + volume_index * 100_000 + simulation_index * 100 + family_index


def _segment_of(w_feedback: float, w_usage: float, rng: np.random.Generator) -> str:
    """Rule-based segment classification of a noisy blend of both latent drivers —
    production's customer_health_scores.segment is itself a rule-based
    classification of the health components, so the one-hot is partially redundant
    with the components, as in reality."""
    s = 0.6 * w_feedback + 0.4 * w_usage + rng.normal(0.0, 0.3)
    if s < -1.3:
        return "dormant"
    if s < -0.6:
        return "silent_churner"
    if s < -0.15:
        return "at_risk"
    if s < 0.4:
        return "new"
    if s < 1.0:
        return "power_user"
    return "happy_advocate"


def _tune_intercept(lin_pred: np.ndarray, target_rate: float, rng: np.random.Generator) -> float:
    """Bisect the family intercept so mean(sigmoid(lin_pred + b)) hits target_rate
    on the drawn cohort — the class balance is a family property, not a draw."""
    lo, hi = -10.0, 10.0
    for _ in range(50):
        mid = (lo + hi) / 2.0
        rate = float(np.mean(1.0 / (1.0 + np.exp(-(lin_pred + mid)))))
        if rate < target_rate:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def simulate_org_dataset(
    volume: int, family: FamilySpec, rng: np.random.Generator
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Draw one org's labeled cohort.

    Returns (X, y, churn_risk_component) where X is the volume x N_FEATURES matrix
    (column order = FEATURE_COLUMNS), y is the hidden 180-day-window churn label,
    and churn_risk_component is the incumbent's only input (column 0 of X).

    Feature distributions match the customer_health_scores / customer_usage
    ranges (components and usage_score 0-100, counts and days clipped to their
    column bounds, trend a signed percentage, urgency a share). Labels come from
    the latent drivers, never from the observed features.
    """
    n = volume
    w_feedback = rng.normal(0.0, 1.0, size=n)
    w_usage = rng.normal(0.0, 1.0, size=n)

    components = {
        # High churn risk = low feedback health + low usage engagement: the
        # component is a noisy, partially-informative observation of the drivers.
        "churn_risk_component": 100.0 / (1.0 + np.exp(
            0.55 * w_feedback + 0.25 * w_usage - 0.65 * rng.normal(size=n)
        )),
        "sentiment_component": np.clip(50.0 + 15.0 * w_feedback + 12.0 * rng.normal(size=n), 0, 100),
        "resolution_component": np.clip(50.0 + 12.0 * w_feedback + 12.0 * rng.normal(size=n), 0, 100),
        "frequency_component": np.clip(50.0 + 10.0 * w_feedback + 12.0 * rng.normal(size=n), 0, 100),
        "usage_score": np.clip(50.0 + 16.0 * w_usage + 10.0 * rng.normal(size=n), 0, 100),
    }
    active_days_30d = np.clip(np.round(10.0 + 6.0 * w_usage + 6.0 * rng.normal(size=n)), 0, 30)
    login_count_30d = np.clip(np.round(15.0 + 9.0 * w_usage + 9.0 * rng.normal(size=n)), 0, 60)
    usage_trend_pct = -5.0 + 12.0 * w_usage + 22.0 * rng.normal(size=n)
    feedback_count = np.clip(np.round(6.0 + 4.0 * w_feedback + 5.0 * rng.normal(size=n)), 0, 80)
    urgency_share = np.clip(1.0 / (1.0 + np.exp(0.8 - 0.9 * w_feedback + 0.7 * rng.normal(size=n))), 0.0, 1.0)

    segments = [_segment_of(float(wi), float(ui), rng) for wi, ui in zip(w_feedback, w_usage)]

    rows = {name: components[name] for name in components}
    rows.update(
        {
            "active_days_30d": active_days_30d,
            "login_count_30d": login_count_30d,
            "usage_trend_pct": usage_trend_pct,
            "feedback_count": feedback_count,
            "urgency_share": urgency_share,
        }
    )

    segment_base = {
        "dormant": 0.9,
        "silent_churner": 0.6,
        "at_risk": 0.35,
        "new": -0.1,
        "power_user": -0.5,
        "happy_advocate": 0.0,
    }

    # Negative on the drivers: unhealthy (low w_feedback / low w_usage) churns.
    lin_pred = (
        -_BETA_LATENT["feedback"] * family.signal_scale * w_feedback
        - _BETA_LATENT["usage"] * family.signal_scale * w_usage
        + np.array([segment_base[s] * family.signal_scale for s in segments])
        + rng.normal(0.0, family.noise_std, size=n)
    )

    intercept = _tune_intercept(lin_pred, family.churn_rate, rng)
    p_churn = 1.0 / (1.0 + np.exp(-(lin_pred + intercept)))
    y = rng.binomial(1, p_churn)

    X = np.column_stack(
        [
            rows[name] for name in FEATURE_COLUMNS[:10]
        ]
        + [
            (np.array([s == segment for s in segments]).astype(float))
            for segment in SEGMENTS
        ]
    )
    return X, y, np.asarray(rows["churn_risk_component"], dtype=float)


def apply_missing_snapshots(
    X: np.ndarray, y: np.ndarray, component: np.ndarray, missing_fraction: float, rng: np.random.Generator
) -> Tuple[np.ndarray, np.ndarray]:
    """Reconstruct `missing_fraction` of rows via the documented defaults (R3).

    A row missing its snapshot keeps its label (the churn event is known) but its
    feature vector becomes the documented default vector — components neutral 50,
    usage counts 0, trend 0, no feedback, unsegmented. Mirrors the core feature
    builder's missing-snapshot behavior for old labels.
    """
    X = X.copy()
    component = component.copy()
    n_missing = int(round(len(X) * missing_fraction))
    if n_missing == 0:
        return X, component
    missing_idx = rng.permutation(len(X))[:n_missing]
    for name in FEATURE_COLUMNS[:10]:
        X[missing_idx, FEATURE_COLUMNS.index(name)] = _MISSING_DEFAULTS[name]
    for segment in SEGMENTS:
        X[missing_idx, FEATURE_COLUMNS.index(f"segment_{segment}")] = 0.0
    component[missing_idx] = _MISSING_DEFAULTS["churn_risk_component"]
    return X, component


# ---------------------------------------------------------------------------
# Challenger vs incumbent evaluation (single simulated org)
# ---------------------------------------------------------------------------

def run_simulation(
    volume: int, family: FamilySpec, seed: int, missing_fraction: float = 0.0
) -> Dict[str, float]:
    """Simulate one org, fit the challenger, score both sides on the same
    leakage-free holdout, and return per-run metrics. Never raises on degenerate
    tiny datasets (zero_division=0 guards; a single-class train simply predicts
    that class — the honest tiny-data behavior)."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import f1_score
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    rng = np.random.default_rng(seed)
    X, y, component = simulate_org_dataset(volume, family, rng)

    if missing_fraction > 0.0:
        X, component = apply_missing_snapshots(X, y, component, missing_fraction, rng)

    try:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.3, stratify=y, random_state=seed
        )
    except ValueError:
        # A class has a single member — stratification is impossible; fall back to
        # a plain random split (still leakage-free, still honest at extreme small n).
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.3, random_state=seed
        )

    challenger = Pipeline(
        [
            ("scale", StandardScaler()),
            ("clf", LogisticRegression(max_iter=2000)),
        ]
    )
    if len(np.unique(y_train)) < 2:
        # Train has a single class (honest tiny-data case): the challenger predicts
        # that class for every holdout row — no fit is possible, no exception.
        y_pred = np.full(y_test.shape[0], y_train[0], dtype=int)
    else:
        challenger.fit(X_train, y_train)
        y_pred = challenger.predict(X_test)
    challenger_f1 = f1_score(y_test, y_pred, average="macro", zero_division=0)

    # Incumbent stand-in: the calibrated-heuristic shape — isotonic calibration
    # of churn_risk_component fit on the SAME train split (the post-fix per-org
    # calibration family; per PRD R5 both sides are scored on the same
    # leakage-free holdout), falling back to the identity shape (p = component/100)
    # when the calibration fit is degenerate (single-class train). Binary label
    # iff calibrated p >= 0.5, matching the M5.2 A/B rule.
    component_train = X_train[:, FEATURE_COLUMNS.index("churn_risk_component")]
    component_test = X_test[:, FEATURE_COLUMNS.index("churn_risk_component")]
    if len(np.unique(y_train)) < 2:
        y_incumbent = np.full(y_test.shape[0], y_train[0], dtype=int)
    else:
        from sklearn.isotonic import IsotonicRegression

        calibrator = IsotonicRegression(out_of_bounds="clip")
        calibrator.fit(component_train, y_train)
        incumbent_proba = calibrator.predict(component_test)
        y_incumbent = (incumbent_proba >= 0.5).astype(int)
    incumbent_f1 = f1_score(y_test, y_incumbent, average="macro", zero_division=0)

    return {
        "challenger_macro_f1": challenger_f1,
        "incumbent_macro_f1": incumbent_f1,
        "macro_f1_delta": challenger_f1 - incumbent_f1,
    }


def run_learning_curve(
    base_seed: int, n_simulations: int, missing_fraction: float = 0.0
) -> List[CurvePoint]:
    """Run every (volume, simulation, family) draw and aggregate per-volume points.

    The per-volume distribution pools all families x simulations draws — the
    "average org" across the three scenario families.
    """
    curve: List[CurvePoint] = []
    for volume_index, volume in enumerate(LABEL_VOLUMES):
        deltas: List[float] = []
        challenger_f1s: List[float] = []
        incumbent_f1s: List[float] = []
        for simulation in range(n_simulations):
            for family_index, family in enumerate(FAMILIES):
                seed = _seed_for(base_seed, volume_index, simulation, family_index)
                result = run_simulation(volume, family, seed, missing_fraction)
                deltas.append(result["macro_f1_delta"])
                challenger_f1s.append(result["challenger_macro_f1"])
                incumbent_f1s.append(result["incumbent_macro_f1"])

        deltas_arr = np.asarray(deltas)
        curve.append(
            CurvePoint(
                label_volume=volume,
                challenger_macro_f1=float(np.mean(challenger_f1s)),
                incumbent_macro_f1=float(np.mean(incumbent_f1s)),
                macro_f1_delta=float(np.mean(deltas_arr)),
                delta_ci_low=float(np.quantile(deltas_arr, 0.025)),
                delta_ci_high=float(np.quantile(deltas_arr, 0.975)),
                promotion_rate=float(np.mean(deltas_arr >= PROMOTION_DELTA)),
            )
        )
    return curve


def crossover_of(curve: List[CurvePoint]) -> Optional[int]:
    """Smallest volume where the challenger clears the bar on average AND a
    majority of pooled orgs would auto-promote under the M5.2 single-run rule.
    Returns None when no volume qualifies (-> "no defensible gate")."""
    for point in curve:
        if point.macro_f1_delta >= PROMOTION_DELTA and point.promotion_rate >= 0.5:
            return point.label_volume
    return None


# ---------------------------------------------------------------------------
# Verdict + artifact assembly
# ---------------------------------------------------------------------------

def determine_verdict(
    full_crossover: Optional[int], fidelity_crossover: Optional[int]
) -> Tuple[str, Optional[int]]:
    """Deterministic verdict rule.

    The gate must clear the harder of the two measured crossovers (full-fidelity
    and R3-degraded), because production features include missing-snapshot rows.
    A crossover at or below the current 500 keeps the gate (conservative: the
    study only re-derives, it never fiat-lowers). A crossover above 500 moves the
    gate up. No crossover anywhere -> no defensible single-tenant threshold.
    """
    if full_crossover is None and fidelity_crossover is None:
        return "no_defensible_gate", None

    target = max(v for v in (full_crossover, fidelity_crossover) if v is not None)
    if target <= CURRENT_TARGET:
        return "keep_500", CURRENT_TARGET
    return f"raise_to_{target}", target


def _honest_limits(
    full_curve: List[CurvePoint],
    fidelity_curve: List[CurvePoint],
    full_crossover: Optional[int],
    fidelity_crossover: Optional[int],
    missing_fraction: float,
    n_simulations: int,
) -> List[str]:
    """Honest-limits lines, computed from the measured numbers where applicable."""
    limits = [
        "Simulation is a bound, not a measurement: no real org is at label volume, "
        "so these learning curves are synthetic; the gate is re-derived from the "
        "simulated crossover, not from live data (PRD R2).",
        "The incumbent stand-in is isotonic calibration of churn_risk_component fit "
        "per-org on the same leakage-free train split (the post-fix calibrated-"
        "heuristic family, PRD R5) — the delta here is what the spine's A/B would "
        "measure, modulo stand-in modeling detail.",
        "The curve pools three scenario families (balanced-clean, balanced-noisy, "
        "imbalanced, churn 10-20% per the 180-day label window); the target must "
        "hold for the weakest plausible org, not just the cleanest.",
    ]

    if full_crossover is not None:
        target_point = next(p for p in full_curve if p.label_volume == full_crossover)
        promotion_note = (
            f"At the crossover volume of {full_crossover} labels, "
            f"{target_point.promotion_rate:.0%} of pooled simulated orgs cleared the "
            f"+0.02 macro-F1 promotion bar on a single run"
        )
        if target_point.promotion_rate < 0.8:
            promotion_note += (
                " — below 80%, so a consecutive-runs promotion rule rather than "
                "M5.2's single run is suggested (PRD OQ2)"
            )
        promotion_note += "."
        limits.append(promotion_note)

    if fidelity_crossover is not None:
        limits.append(
            f"Feature-reconstruction fidelity (PRD R3): with {missing_fraction:.0%} "
            f"of rows missing snapshots and reconstructed via documented defaults, "
            f"the crossover moves from {full_crossover if full_crossover is not None else 'never'} "
            f"to {fidelity_crossover} labels — the gate clears the harder reading."
        )

    limits.append(
        f"{n_simulations} simulations x 3 scenario families per volume; fixed seeds; "
        "rerun `python scripts/eval_churn_label_gate.py` to reproduce."
    )
    return limits


def build_artifact(
    *,
    n_simulations: int,
    missing_fraction: float,
    full_curve: List[CurvePoint],
    fidelity_curve: List[CurvePoint],
    full_crossover: Optional[int],
    fidelity_crossover: Optional[int],
) -> dict:
    """Assemble the committed artifact (eval_results/churn_label_gate.json schema).

    Key set must stay exactly aligned with the readout route's
    ChurnLabelGateResponse (minus has_results) — extra keys would make the
    route's parse-or-degrade handler fall back to the empty state.
    """
    verdict, target = determine_verdict(full_crossover, fidelity_crossover)
    method = (
        f"simulated learning curves: per-org logistic challenger (sklearn, "
        f"standardized, L2) vs calibrated-heuristic incumbent (isotonic calibration "
        f"of churn_risk_component fit per-org, identity fallback); leakage-free "
        f"stratified 30% holdout; macro-F1 delta pooled over "
        f"{n_simulations} simulations x 3 scenario families per volume with "
        f"empirical 95% CI and M5.2 promotion rate (delta >= +0.02); labels follow "
        f"the {LABEL_WINDOW_DAYS}-day observation-window semantics; R3 fidelity "
        f"dimension re-runs the challenger with {missing_fraction:.0%} of rows "
        f"reconstructed via documented defaults."
    )

    return {
        "artifact_version": ARTIFACT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "target": target,
        "method": method,
        "n_simulations": n_simulations,
        "crossover_label_volume": full_crossover,
        "fidelity_sensitivity": {
            "missing_fraction": missing_fraction,
            "crossover_label_volume": fidelity_crossover,
            "curves": [p.to_dict() for p in fidelity_curve],
        },
        "honest_limits": _honest_limits(
            full_curve,
            fidelity_curve,
            full_crossover,
            fidelity_crossover,
            missing_fraction,
            n_simulations,
        ),
        "curves": [p.to_dict() for p in full_curve],
    }


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def _default_output_path() -> str:
    return os.path.join(os.path.dirname(__file__), "..", "eval_results", "churn_label_gate.json")


def _print_curve_table(title: str, curve: List[CurvePoint]) -> None:
    print(f"\n{title}")
    print(
        f"  {'labels':>7} | {'challenger F1':>13} | {'incumbent F1':>13} "
        f"| {'delta':>7} | {'95% CI':>18} | {'promo rate':>10}"
    )
    for point in curve:
        print(
            f"  {point.label_volume:>7} | {point.challenger_macro_f1:>13.4f} "
            f"| {point.incumbent_macro_f1:>13.4f} | {point.macro_f1_delta:>+7.4f} "
            f"| [{point.delta_ci_low:+.4f}, {point.delta_ci_high:+.4f}] "
            f"| {point.promotion_rate:>10.3f}"
        )


def main(argv: Optional[List[str]] = None) -> int:
    """Runs the full study (full-fidelity + R3-degraded curves), writes the
    committed artifact, prints a human summary. Always returns 0 — this script is
    a disclosure tool, never a CI gate (eval harness convention)."""
    import warnings

    # sklearn/scipy version mismatch noise (lbfgs solver options), not a failure.
    warnings.filterwarnings("ignore", message="Unknown solver options.*")

    parser = argparse.ArgumentParser(
        description="Churn label-gate re-derivation study (simulated learning curves, "
        "challenger vs incumbent, R3 fidelity dimension)"
    )
    parser.add_argument("--simulations", type=int, default=50, help="simulations per volume (default 50)")
    parser.add_argument("--seed", type=int, default=20260814, help="base seed (default 20260814)")
    parser.add_argument(
        "--missing-fraction", type=float, default=DEFAULT_MISSING_FRACTION,
        help="fraction of rows missing snapshots in the R3 fidelity dimension (default 0.25)",
    )
    parser.add_argument("--output", type=str, default=_default_output_path())
    args = parser.parse_args(argv)

    print(f"Churn label-gate study: {args.simulations} simulations x {len(FAMILIES)} families x "
          f"{len(LABEL_VOLUMES)} volumes, seed={args.seed}, "
          f"fidelity missing-fraction={args.missing_fraction}")

    full_curve = run_learning_curve(args.seed, args.simulations, missing_fraction=0.0)
    fidelity_curve = run_learning_curve(
        args.seed, args.simulations, missing_fraction=args.missing_fraction
    )

    full_crossover = crossover_of(full_curve)
    fidelity_crossover = crossover_of(fidelity_curve)
    verdict, target = determine_verdict(full_crossover, fidelity_crossover)

    _print_curve_table("Full-fidelity learning curve:", full_curve)
    _print_curve_table(
        f"R3 fidelity dimension ({args.missing_fraction:.0%} of rows missing snapshots):",
        fidelity_curve,
    )

    print(
        f"\nCrossover (full fidelity): {full_crossover if full_crossover is not None else 'never'}"
        f" | Crossover ({args.missing_fraction:.0%} missing): "
        f"{fidelity_crossover if fidelity_crossover is not None else 'never'}"
    )
    print(f"VERDICT: {verdict} (target={target})")

    artifact = build_artifact(
        n_simulations=args.simulations,
        missing_fraction=args.missing_fraction,
        full_curve=full_curve,
        fidelity_curve=fidelity_curve,
        full_crossover=full_crossover,
        fidelity_crossover=fidelity_crossover,
    )
    print("\nHonest limits:")
    for line in artifact["honest_limits"]:
        print(f"  - {line}")

    print(
        "\nDISCLOSURE ONLY — does not block merge. The verdict is the output of a "
        "seeded simulation study, never a build gate."
    )

    output_path = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(artifact, f, indent=2)
    print(f"\nResults written to: {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
