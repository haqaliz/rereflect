"""
Offline sentiment eval harness — runs VaderSentimentProvider and
TransformerSentimentProvider (analysis-engine) over labeled CSVs, computes
per-class + macro precision/recall/F1/confusion, and writes a committed
results artifact for the Settings -> AI -> Accuracy disclosure card.

DISCLOSURE, NOT A GATE (see PRD prd.md:163-168): this script always exits 0,
even when the transformer loses to VADER in-domain, or when the transformer
half can't run at all (torch/transformers not importable). The eval numbers
are reported honestly, never hidden, never used to fail a build.

Usage:
    python scripts/eval_sentiment.py \
        --public-csv tests/fixtures/sentiment_eval/public_eval.csv \
        --in-domain-csv tests/fixtures/sentiment_eval/in_domain_eval.csv \
        --output eval_results/sentiment_accuracy.json
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 3-class sentiment label contract — matches SentimentAnalyzer._classify_label's output
# values exactly (analysis-engine/src/analyzer/sentiment.py), no remapping needed when
# comparing predicted vs gold.
SENTIMENT_LABELS = ["positive", "neutral", "negative"]

# In-domain success target per PRD goal: transformer macro-F1 >= VADER + 0.05.
IN_DOMAIN_TARGET_DELTA = 0.05

_MODEL_ID = "cardiffnlp/twitter-roberta-base-sentiment-latest"
_MODEL_REVISION = "main"


# ---------------------------------------------------------------------------
# Metrics core (Phase 1) — copied tp/fp/fn/tn -> precision/recall/f1/accuracy
# math from src/api/routes/admin_backtest.py:56 (_safe_precision_recall_f1_accuracy),
# per the existing precedent that this helper is independently defined per
# script/route rather than shared via a common module (see backtest_churn.py's
# own copy).
# ---------------------------------------------------------------------------

def _safe_precision_recall_f1_accuracy(
    tp: int, fp: int, fn: int, tn: int
) -> Tuple[float, float, float, float]:
    """Compute precision, recall, F1, and accuracy from confusion matrix counts."""
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    total = tp + fp + fn + tn
    accuracy = (tp + tn) / total if total > 0 else 0.0
    return precision, recall, f1, accuracy


def confusion_to_binary_counts(
    confusion: Dict[str, Dict[str, int]], label: str, labels: List[str]
) -> Tuple[int, int, int, int]:
    """One-vs-rest slice of a multiclass confusion matrix for a single label.

    confusion[true_label][predicted_label] = count.
    """
    tp = confusion[label][label]
    fp = sum(confusion[other][label] for other in labels if other != label)
    fn = sum(confusion[label][other] for other in labels if other != label)
    total = sum(confusion[t][p] for t in labels for p in labels)
    tn = total - tp - fp - fn
    return tp, fp, fn, tn


def compute_multiclass_metrics(confusion: Dict[str, Dict[str, int]], labels: List[str]) -> dict:
    """Per-class precision/recall/F1/support + macro-averages + overall accuracy.

    Never raises on empty/degenerate confusion matrices (all-zero, single-class-only) —
    _safe_precision_recall_f1_accuracy already guards every division.
    """
    per_class = {}
    for label in labels:
        tp, fp, fn, tn = confusion_to_binary_counts(confusion, label, labels)
        precision, recall, f1, _ = _safe_precision_recall_f1_accuracy(tp, fp, fn, tn)
        support = tp + fn  # true count for this label (row sum)
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
        }

    macro_precision = sum(per_class[l]["precision"] for l in labels) / len(labels)
    macro_recall = sum(per_class[l]["recall"] for l in labels) / len(labels)
    macro_f1 = sum(per_class[l]["f1"] for l in labels) / len(labels)

    total = sum(confusion[t][p] for t in labels for p in labels)
    trace = sum(confusion[l][l] for l in labels)
    accuracy = trace / total if total > 0 else 0.0

    return {
        "per_class": per_class,
        "macro_precision": macro_precision,
        "macro_recall": macro_recall,
        "macro_f1": macro_f1,
        "accuracy": accuracy,
    }


# ---------------------------------------------------------------------------
# CSV loading (Phase 2)
# ---------------------------------------------------------------------------

def load_eval_csv(path: str) -> List[Tuple[str, str]]:
    """Load a `text,label` eval CSV into a list of (text, label) tuples.

    Validates every row (not fail-fast): collects all problems and raises one
    ValueError listing every bad row if any exist. label must be one of
    SENTIMENT_LABELS; text must be non-empty.
    """
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        missing = [h for h in ("text", "label") if h not in fieldnames]
        if missing:
            raise ValueError(
                f"{path}: missing required header(s) {missing} — found {fieldnames}"
            )

        rows: List[Tuple[str, str]] = []
        errors: List[str] = []
        # DictReader row 1 is the first data row, which is CSV file line 2 (line 1 is
        # the header) — report 1-indexed *file* line numbers so they match what a
        # human sees when opening the CSV.
        for i, row in enumerate(reader, start=2):
            text = (row.get("text") or "").strip()
            label = (row.get("label") or "").strip()
            if not text:
                errors.append(f"row {i}: empty text")
                continue
            if label not in SENTIMENT_LABELS:
                errors.append(
                    f"row {i}: invalid label {label!r} (must be one of {SENTIMENT_LABELS})"
                )
                continue
            rows.append((text, label))

        if errors:
            raise ValueError(f"{path}: {len(errors)} invalid row(s):\n" + "\n".join(errors))

        return rows


# ---------------------------------------------------------------------------
# run_provider / run_eval_set (Phase 3) — provider is injected, tests never
# need a real transformer/VADER to prove the wiring is correct.
# ---------------------------------------------------------------------------

@dataclass
class ProviderEvalResult:
    provider: str
    n: int
    macro_precision: float
    macro_recall: float
    macro_f1: float
    accuracy: float
    per_class: dict
    confusion_matrix: Dict[str, Dict[str, int]]


@dataclass
class EvalSetResult:
    set_name: str
    n: int
    vader: Optional[ProviderEvalResult]
    transformer: Optional[ProviderEvalResult]
    macro_f1_delta: Optional[float]
    meets_target: Optional[bool]


def _classify_label(compound: float) -> str:
    """Same ±0.05 thresholds as SentimentAnalyzer._classify_label (sentiment.py) — kept
    identical so predicted labels here mean exactly what they mean in production."""
    if compound >= 0.05:
        return "positive"
    elif compound <= -0.05:
        return "negative"
    return "neutral"


def _predict_label(provider, text: str) -> str:
    """Adapter isolating the provider call shape — the ONE function to touch if
    sentiment-provider-core's interface ever changes (spec.md R1). Calls
    provider.score(text) -> {compound, pos, neu, neg} (SentimentProvider contract,
    analysis-engine/src/analyzer/sentiment_providers/base.py) and classifies the
    compound score with the same thresholds SentimentAnalyzer uses, so eval labels
    match production label semantics exactly."""
    scores = provider.score(text)
    return _classify_label(scores["compound"])


def _empty_confusion(labels: List[str]) -> Dict[str, Dict[str, int]]:
    return {true: {pred: 0 for pred in labels} for true in labels}


def run_provider(
    provider, rows: List[Tuple[str, str]], provider_name: str
) -> ProviderEvalResult:
    """Run `provider` over every (text, label) row, build the confusion matrix, and
    compute per-class + macro metrics."""
    confusion = _empty_confusion(SENTIMENT_LABELS)
    for text, true_label in rows:
        predicted_label = _predict_label(provider, text)
        confusion[true_label][predicted_label] += 1

    metrics = compute_multiclass_metrics(confusion, SENTIMENT_LABELS)
    return ProviderEvalResult(
        provider=provider_name,
        n=len(rows),
        macro_precision=metrics["macro_precision"],
        macro_recall=metrics["macro_recall"],
        macro_f1=metrics["macro_f1"],
        accuracy=metrics["accuracy"],
        per_class=metrics["per_class"],
        confusion_matrix=confusion,
    )


def run_eval_set(
    set_name: str,
    csv_path: str,
    vader_provider,
    transformer_provider=None,
) -> EvalSetResult:
    """Run both providers over csv_path and compute the transformer-vs-VADER delta.

    transformer_provider=None short-circuits before running the transformer half at
    all — the graceful-skip path exercised when model-packaging hasn't landed (or the
    model failed to load): transformer/macro_f1_delta/meets_target are all None, no
    error raised.

    meets_target (delta >= IN_DOMAIN_TARGET_DELTA) is only computed for set_name ==
    "in_domain" — the public set is a CI baseline, not the honest claim (PRD goal).
    """
    rows = load_eval_csv(csv_path)
    vader_result = run_provider(vader_provider, rows, provider_name="vader")

    transformer_result: Optional[ProviderEvalResult] = None
    macro_f1_delta: Optional[float] = None
    if transformer_provider is not None:
        transformer_result = run_provider(transformer_provider, rows, provider_name="transformer")
        macro_f1_delta = transformer_result.macro_f1 - vader_result.macro_f1

    meets_target: Optional[bool] = None
    if set_name == "in_domain" and macro_f1_delta is not None:
        meets_target = macro_f1_delta >= IN_DOMAIN_TARGET_DELTA

    return EvalSetResult(
        set_name=set_name,
        n=len(rows),
        vader=vader_result,
        transformer=transformer_result,
        macro_f1_delta=macro_f1_delta,
        meets_target=meets_target,
    )


# ---------------------------------------------------------------------------
# CLI entrypoint (Phase 5)
# ---------------------------------------------------------------------------

def _default_csv_path(name: str) -> str:
    return os.path.join(
        os.path.dirname(__file__), "..", "tests", "fixtures", "sentiment_eval", name
    )


def _build_providers():
    """Lazily import + construct the real VaderSentimentProvider and (if importable)
    TransformerSentimentProvider from analysis-engine, via the sys.path.insert cross-
    service pattern already established at src/api/routes/feedback.py:24-31.

    Returns (vader_provider, transformer_provider_or_none). Never raises — a missing
    torch/transformers install degrades to transformer_provider=None (graceful-skip,
    soft-dependency on model-packaging per spec.md)."""
    analysis_engine_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "analysis-engine", "src")
    )
    if analysis_engine_path not in sys.path:
        sys.path.insert(0, analysis_engine_path)

    from analyzer.sentiment_providers.providers.vader import VaderSentimentProvider

    vader_provider = VaderSentimentProvider()

    transformer_provider = None
    try:
        from analyzer.sentiment_providers.providers.transformer import (
            TransformerSentimentProvider,
        )

        transformer_provider = TransformerSentimentProvider()
    except ImportError as exc:
        logger.warning(
            "TransformerSentimentProvider not importable (torch/transformers missing) — "
            "eval will run VADER-only, transformer results will be null: %s", exc,
        )

    return vader_provider, transformer_provider


def _print_set_summary(result: EvalSetResult) -> None:
    print(f"\n--- {result.set_name} (n={result.n}) ---")
    print(
        f"  VADER:       macro-P={result.vader.macro_precision:.4f} "
        f"macro-R={result.vader.macro_recall:.4f} macro-F1={result.vader.macro_f1:.4f}"
    )
    if result.transformer is not None:
        print(
            f"  Transformer: macro-P={result.transformer.macro_precision:.4f} "
            f"macro-R={result.transformer.macro_recall:.4f} macro-F1={result.transformer.macro_f1:.4f}"
        )
        print(f"  Delta (transformer - vader): {result.macro_f1_delta:+.4f}")
        if result.meets_target is not None:
            verdict = "MEETS" if result.meets_target else "does NOT meet"
            print(f"  {verdict} the >= {IN_DOMAIN_TARGET_DELTA} in-domain target")
    else:
        print("  Transformer: not evaluated (deps unavailable — see warning above)")


def main(argv: Optional[List[str]] = None) -> int:
    """Runs both eval sets, writes the committed results artifact, prints a human
    summary. Always returns 0 — this script is a disclosure tool, never a CI gate
    (spec.md OQ1: manual refresh + committed, not a build-failing drift check)."""
    parser = argparse.ArgumentParser(description="Sentiment provider eval harness (VADER vs transformer)")
    parser.add_argument("--public-csv", type=str, default=_default_csv_path("public_eval.csv"))
    parser.add_argument("--in-domain-csv", type=str, default=_default_csv_path("in_domain_eval.csv"))
    parser.add_argument(
        "--output", type=str,
        default=os.path.join(os.path.dirname(__file__), "..", "eval_results", "sentiment_accuracy.json"),
    )
    args = parser.parse_args(argv)

    vader_provider, transformer_provider = _build_providers()

    public_result = run_eval_set(
        "public", args.public_csv, vader_provider=vader_provider, transformer_provider=transformer_provider
    )
    in_domain_result = run_eval_set(
        "in_domain", args.in_domain_csv, vader_provider=vader_provider, transformer_provider=transformer_provider
    )

    _print_set_summary(public_result)
    _print_set_summary(in_domain_result)
    print(
        "\nDISCLOSURE ONLY — does not block merge. The transformer ships opt-in/OFF by "
        "default regardless of these numbers (see PRD prd.md:163-168)."
    )

    artifact = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_id": _MODEL_ID,
        "model_revision": _MODEL_REVISION,
        "public": asdict(public_result),
        "in_domain": asdict(in_domain_result),
    }

    output_path = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(artifact, f, indent=2)
    print(f"\nResults written to: {output_path}")

    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
