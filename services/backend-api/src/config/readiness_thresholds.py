# Activation thresholds for M5.2 (per-org corrections flywheel) and M5.3 (per-org churn ML).
# See AI-TRACKING.md:313-317 (M5.0) and
# docs/planning/local-analyzer-sentiment-model/m5.0-readiness-report/spec.md.
#
# Plain module constants (not env-configurable) — these are planning heuristics, not
# billing/feature toggles. Mirrors services/churn_calibrator.py's MIN_LABELS style.

CHURN_LABEL_TARGET = 500          # AI-TRACKING.md:317 — M5.3 exit criterion, verbatim
CORRECTION_VOLUME_TARGET = 200    # v1 proposal for M5.2 — unvalidated, tune after a real training run
