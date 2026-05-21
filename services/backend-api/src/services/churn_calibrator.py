"""
Churn probability calibration service.
Maps 0–100 heuristic churn risk scores to calibrated 30-day churn probabilities
using isotonic regression with bootstrap confidence intervals.

No I/O, no database, no Celery — pure computation.
"""

import random
from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np
from sklearn.isotonic import IsotonicRegression

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_LABELS = 20  # Minimum labels required to fit a per-org model

DEFAULT_THRESHOLD_BANDS: dict = {
    "low": 0.30,
    "medium": 0.50,
    "high": 0.70,
    "critical": 0.85,
}

# Default bootstrap seed — kept fixed so same inputs always return same CI.
_DEFAULT_BOOTSTRAP_SEED = 0


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class InsufficientLabelsError(ValueError):
    """Raised when fewer than MIN_LABELS labels are provided to fit()."""

    def __init__(self, n: int) -> None:
        super().__init__(
            f"At least {MIN_LABELS} labels are required to fit a calibration model; "
            f"got {n}. Callers should fall back to the global model."
        )
        self.n = n


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CalibrationModel:
    """Fitted isotonic calibration model stored as breakpoint arrays."""

    breakpoints: list  # X values (scores), monotonically increasing
    probabilities: list  # Y values (probabilities), monotonically increasing
    label_count: int
    positive_count: int
    threshold_bands: dict  # {"low": 0.30, "medium": 0.50, "high": 0.70, "critical": 0.85}
    # Raw training data retained for bootstrap resampling (not serialised to DB)
    _training_scores: tuple = field(default=(), compare=False, hash=False)
    _training_labels: tuple = field(default=(), compare=False, hash=False)


@dataclass(frozen=True)
class Metrics:
    """Backtest evaluation metrics."""

    precision: float
    recall: float
    f1: float
    auc: float
    optimal_threshold: float


# ---------------------------------------------------------------------------
# Core service
# ---------------------------------------------------------------------------


class ChurnCalibrator:
    """Calibrates heuristic churn risk scores into probabilities."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fit(self, scores: list, labels: list) -> CalibrationModel:
        """Fit an isotonic regression model mapping scores → probabilities."""
        n = len(scores)
        if n < MIN_LABELS:
            raise InsufficientLabelsError(n)

        scores_arr = np.array(scores, dtype=float)
        labels_arr = np.array(labels, dtype=float)

        # If only one class present, fall back to identity model
        if labels_arr.sum() == 0 or labels_arr.sum() == n:
            return self.identity_model()

        ir = IsotonicRegression(out_of_bounds="clip", increasing=True)
        ir.fit(scores_arr, labels_arr)

        bps = ir.X_thresholds_.tolist()
        probs = ir.y_thresholds_.tolist()

        return CalibrationModel(
            breakpoints=bps,
            probabilities=probs,
            label_count=n,
            positive_count=int(labels_arr.sum()),
            threshold_bands=dict(DEFAULT_THRESHOLD_BANDS),
            _training_scores=tuple(int(s) for s in scores),
            _training_labels=tuple(bool(l) for l in labels),
        )

    def predict(self, score: int, model: CalibrationModel) -> float:
        """Return calibrated churn probability for a single score."""
        return self._interpolate(float(score), model.breakpoints, model.probabilities)

    def predict_with_interval(
        self,
        score: int,
        model: CalibrationModel,
        n_bootstrap: int = 200,
        ci: float = 0.90,
    ) -> tuple:
        """Return (point_estimate, lower_bound, upper_bound) via bootstrap."""
        p = self.predict(score, model)
        lower, upper = self._bootstrap_predict(
            score=score,
            model=model,
            n_bootstrap=n_bootstrap,
            ci=ci,
        )
        return (p, lower, upper)

    def derive_risk_level(self, p: float, bands: dict) -> str:
        """Map probability to a risk level string using the provided bands."""
        if p >= bands["critical"]:
            return "critical"
        if p >= bands["high"]:
            return "high"
        if p >= bands["medium"]:
            return "medium"
        return "low"

    def derive_timeline_bucket(self, p: float, sentiment_trend: float) -> str:
        """Classify time-to-churn into one of five buckets."""
        if p >= 0.85 or (p >= 0.70 and sentiment_trend <= -0.4):
            return "immediate"
        if p >= 0.70:
            return "2w"
        if p >= 0.50:
            return "2-4w"
        if p >= 0.30:
            return "1-3m"
        return "low"

    def backtest(
        self, scores: list, labels: list, model: CalibrationModel
    ) -> Metrics:
        """Evaluate the model on a labelled dataset and return metrics."""
        return self._compute_metrics(scores, labels, model)

    def identity_model(self) -> CalibrationModel:
        """Return a linear fallback model mapping score/100 → probability."""
        breakpoints = list(range(0, 101, 1))
        probabilities = [bp / 100.0 for bp in breakpoints]
        return CalibrationModel(
            breakpoints=breakpoints,
            probabilities=probabilities,
            label_count=0,
            positive_count=0,
            threshold_bands=dict(DEFAULT_THRESHOLD_BANDS),
            _training_scores=tuple(range(101)),
            _training_labels=tuple(False for _ in range(101)),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _interpolate(
        self, score: float, breakpoints: list, probabilities: list
    ) -> float:
        """Linear interpolation between breakpoints; clamp outside range."""
        bps = breakpoints
        probs = probabilities

        if score <= bps[0]:
            return float(probs[0])
        if score >= bps[-1]:
            return float(probs[-1])

        # Binary search for the interval
        lo, hi = 0, len(bps) - 1
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            if bps[mid] <= score:
                lo = mid
            else:
                hi = mid

        x0, x1 = bps[lo], bps[hi]
        y0, y1 = probs[lo], probs[hi]
        if x1 == x0:
            return float(y0)
        t = (score - x0) / (x1 - x0)
        return float(y0 + t * (y1 - y0))

    def _bootstrap_predict(
        self,
        score: int,
        model: CalibrationModel,
        n_bootstrap: int,
        ci: float,
    ) -> tuple:
        """Resample from original training labels to build a CI via bootstrap."""
        rng = np.random.default_rng(seed=_DEFAULT_BOOTSTRAP_SEED)

        # Use stored training data when available; fall back to breakpoints
        if model._training_scores and model._training_labels:
            scores_arr = np.array(model._training_scores, dtype=float)
            labels_arr = np.array(model._training_labels, dtype=float)
        else:
            scores_arr = np.array(model.breakpoints, dtype=float)
            labels_arr = np.array(model.probabilities, dtype=float)

        n = len(scores_arr)
        boot_preds: list = []

        for _ in range(n_bootstrap):
            idx = rng.integers(0, n, size=n)
            s_boot = scores_arr[idx]
            l_boot = labels_arr[idx]

            # Degenerate bootstrap sample (all same label) — use point estimate
            if l_boot.sum() == 0 or l_boot.sum() == n:
                boot_preds.append(self.predict(score, model))
                continue

            ir = IsotonicRegression(out_of_bounds="clip", increasing=True)
            try:
                ir.fit(s_boot, l_boot)
                pred = float(ir.predict([float(score)])[0])
            except Exception:
                pred = self.predict(score, model)
            boot_preds.append(pred)

        alpha = 1.0 - ci
        lower = float(np.percentile(boot_preds, 100 * alpha / 2))
        upper = float(np.percentile(boot_preds, 100 * (1 - alpha / 2)))
        return (lower, upper)

    def _compute_metrics(
        self, scores: list, labels: list, model: CalibrationModel
    ) -> Metrics:
        """Compute precision, recall, F1, AUC, and optimal threshold."""
        labels_arr = np.array(labels, dtype=float)
        probs = np.array([self.predict(s, model) for s in scores])

        # All negative — undefined AUC, F1=0
        if labels_arr.sum() == 0:
            return Metrics(
                precision=0.0,
                recall=0.0,
                f1=0.0,
                auc=0.0,
                optimal_threshold=0.5,
            )

        # AUC via trapezoidal rule over sorted thresholds
        auc = self._compute_auc(probs, labels_arr)

        # Sweep thresholds to find one that maximises F1
        opt_threshold, best_f1, best_precision, best_recall = self._find_optimal_threshold(
            probs, labels_arr
        )

        return Metrics(
            precision=best_precision,
            recall=best_recall,
            f1=best_f1,
            auc=auc,
            optimal_threshold=opt_threshold,
        )

    def _compute_pr_curve(
        self, probs: np.ndarray, labels: np.ndarray
    ) -> tuple:
        """Compute precision-recall pairs at all unique thresholds."""
        thresholds = np.unique(probs)
        precisions = []
        recalls = []
        for t in thresholds:
            preds = (probs >= t).astype(float)
            tp = float((preds * labels).sum())
            fp = float((preds * (1 - labels)).sum())
            fn = float(((1 - preds) * labels).sum())
            precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            precisions.append(precision)
            recalls.append(recall)
        return np.array(precisions), np.array(recalls), thresholds

    def _compute_auc(self, probs: np.ndarray, labels: np.ndarray) -> float:
        """ROC-AUC via sklearn-style trapezoidal integration."""
        try:
            from sklearn.metrics import roc_auc_score
            return float(roc_auc_score(labels, probs))
        except Exception:
            return 0.0

    def _find_optimal_threshold(
        self, probs: np.ndarray, labels: np.ndarray
    ) -> tuple:
        """Return (threshold, f1, precision, recall) that maximises F1."""
        thresholds = np.unique(probs)
        best_f1 = -1.0
        best_threshold = 0.5
        best_precision = 0.0
        best_recall = 0.0

        for t in thresholds:
            preds = (probs >= t).astype(float)
            tp = float((preds * labels).sum())
            fp = float((preds * (1 - labels)).sum())
            fn = float(((1 - preds) * labels).sum())
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = (
                2 * precision * recall / (precision + recall)
                if (precision + recall) > 0
                else 0.0
            )
            if f1 > best_f1:
                best_f1 = f1
                best_threshold = float(t)
                best_precision = precision
                best_recall = recall

        return best_threshold, best_f1, best_precision, best_recall
