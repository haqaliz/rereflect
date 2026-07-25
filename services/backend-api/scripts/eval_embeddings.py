"""
Offline retrieval eval harness — runs one or more embedding providers over the
held-out template-matching fixtures and computes recall@1, MRR, and false-match
rate at the production TemplateMatcher threshold (0.85), then writes a committed
results artifact comparing a candidate provider against a baseline.

Part of local-embedding-quality (M5.4), aspect retrieval-eval-card (Task 2 of 5).
Mirrors the M5.1 conventions in scripts/eval_sentiment.py: importable core, thin
CLI, always exits 0, honest reporting (this is a disclosure tool, not a CI gate).

Usage:
    python scripts/eval_embeddings.py \
        --fixtures tests/fixtures/embedding_eval/queries.jsonl \
        --output eval_results/retrieval_accuracy.json \
        --baseline-provider ollama --baseline-model nomic-embed-text \
        --candidate-provider local --candidate-model BAAI/bge-small-en-v1.5
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

# Make `src.*` importable when this script is run standalone (python
# scripts/eval_embeddings.py) rather than under pytest (where pytest.ini's
# `pythonpath = .` already puts the backend-api root on sys.path). Mirrors the
# existing scripts/backfill_customer_email.py pattern.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logger = logging.getLogger(__name__)

# Production matcher threshold (TemplateMatcher._DEFAULT_THRESHOLD) — kept identical
# so eval numbers describe the exact production matching behaviour.
MATCHER_THRESHOLD = 0.85

# Success target: candidate must beat baseline recall@1 by at least this much
# AND not regress false_match_rate (see compare()).
RECALL_TARGET_DELTA = 0.05


# ---------------------------------------------------------------------------
# Fixture loading (mirrors eval_sentiment.load_eval_csv: collect all errors,
# raise one ValueError with 1-indexed line numbers)
# ---------------------------------------------------------------------------

def load_fixtures(path: str) -> List[dict]:
    """Load a `{"query": str, "expected": str|None}` jsonl eval fixture file.

    Validates every row (not fail-fast): collects all problems and raises one
    ValueError listing every bad row if any exist. `query` must be a non-empty
    string; `expected` must be a string or null (None => a negative fixture —
    no template should match).
    """
    rows: List[dict] = []
    errors: List[str] = []

    with open(path, encoding="utf-8") as f:
        for i, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"line {i}: invalid JSON ({exc})")
                continue

            if not isinstance(obj, dict):
                errors.append(f"line {i}: expected a JSON object, got {type(obj).__name__}")
                continue

            query = obj.get("query")
            if not isinstance(query, str) or not query.strip():
                errors.append(f"line {i}: 'query' must be a non-empty string")
                continue

            if "expected" not in obj:
                errors.append(f"line {i}: missing 'expected' key")
                continue

            expected = obj["expected"]
            if expected is not None and not isinstance(expected, str):
                errors.append(f"line {i}: 'expected' must be a string or null")
                continue

            rows.append({"query": query, "expected": expected})

    if errors:
        raise ValueError(f"{path}: {len(errors)} invalid row(s):\n" + "\n".join(errors))

    return rows


# ---------------------------------------------------------------------------
# Provider construction — build a ResolvedEmbedder without an OrgAIConfig row,
# so the harness can run a provider standalone (Task brief R1).
# ---------------------------------------------------------------------------

def build_resolved_embedder(
    provider: str,
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
):
    """Build a ResolvedEmbedder for `provider` directly via the factory (no DB /
    OrgAIConfig lookup — that's resolve_embedding_provider's job, not this harness's).

    Raises whatever EmbeddingProviderFactory.create raises (e.g. ValueError for an
    unknown provider) — callers (the CLI) are responsible for catching construction
    errors and degrading that provider's side of the comparison to null.
    """
    from src.services.embeddings.defaults import default_model_for_provider
    from src.services.embeddings.factory import EmbeddingProviderFactory
    from src.services.embeddings.resolver import ResolvedEmbedder

    inst = EmbeddingProviderFactory.create(provider, api_key=api_key, base_url=base_url, model=model)
    return ResolvedEmbedder(
        provider=provider,
        embedder=inst,
        dimension_hint=inst.dimension,
        model=model or default_model_for_provider(provider),
    )


# ---------------------------------------------------------------------------
# MRR ranking helper — a self-contained replica of TemplateMatcher.find_match's
# embed + skip-filter + cosine-similarity logic, extended to return the FULL
# ranking of templates rather than just the single best match. Deliberately
# does NOT touch TemplateMatcher internals (per the Task brief's escalation
# guidance) — it only calls its two public, side-effect-free helpers
# (normalize_question, cosine_similarity) and re-reads query_template_mappings
# the same way find_match does.
# ---------------------------------------------------------------------------

def _best_similarity_per_template(query: str, resolved, db) -> Dict[int, float]:
    """Return {template_id: best cosine similarity across that template's mapped
    question patterns} for `query`, restricted to mappings tagged with the SAME
    (provider, dimension, model) as `resolved` — the identical skip-filter
    TemplateMatcher.find_match applies, so ranking here means exactly what it
    means in production."""
    from sqlalchemy import text

    from src.services.copilot.template_matcher import TemplateMatcher

    matcher = TemplateMatcher()
    normalized = matcher.normalize_question(query)
    query_embedding = resolved.embedder.embed(normalized)

    active_provider = resolved.provider
    active_dim = len(query_embedding)
    active_model = resolved.model

    mappings = db.execute(
        text(
            "SELECT template_id, question_embedding, embedding_provider, "
            "embedding_dimension, embedding_model FROM query_template_mappings"
        )
    ).fetchall()

    best_per_template: Dict[int, float] = {}
    for mapping in mappings:
        stored_embedding = mapping.question_embedding
        if not stored_embedding:
            continue
        if (
            mapping.embedding_provider != active_provider
            or mapping.embedding_dimension != active_dim
            or mapping.embedding_model != active_model
        ):
            continue

        if isinstance(stored_embedding, str):
            stored_embedding = json.loads(stored_embedding)

        similarity = matcher.cosine_similarity(query_embedding, stored_embedding)
        template_id = mapping.template_id
        if template_id not in best_per_template or similarity > best_per_template[template_id]:
            best_per_template[template_id] = similarity

    return best_per_template


def _reciprocal_rank(best_per_template: Dict[int, float], gold_template_id) -> float:
    """1/rank of gold_template_id in best_per_template sorted by similarity desc.
    Returns 0.0 if the gold template has no similarity entry at all (should not
    happen for a correctly-seeded fixture, but never raises)."""
    if gold_template_id not in best_per_template:
        return 0.0

    ranked = sorted(best_per_template.items(), key=lambda kv: kv[1], reverse=True)
    for rank, (template_id, _similarity) in enumerate(ranked, start=1):
        if template_id == gold_template_id:
            return 1.0 / rank
    return 0.0


# ---------------------------------------------------------------------------
# run_provider / run_eval — core, provider-injected, unit-testable with a stub
# embedder (no real model/network needed).
# ---------------------------------------------------------------------------

@dataclass
class ProviderRetrievalResult:
    provider: str
    model: Optional[str]
    n: int
    n_pos: int
    n_neg: int
    recall_at_1: float
    mrr: float
    false_match_rate: float


def run_provider(resolved, fixtures: List[dict], db, org_id: int = 1) -> dict:
    """Seed system templates for `resolved`, then run every fixture through
    TemplateMatcher.find_match, computing recall@1 / MRR / false_match_rate.

    - recall@1: over positives (expected is not None), the fraction where
      find_match's returned match (if any) has description == expected.
    - MRR: over positives, the FULL ranking of all seeded templates by cosine
      similarity (see _best_similarity_per_template/_reciprocal_rank above) —
      NOT gated by MATCHER_THRESHOLD, so a correct-but-below-threshold top rank
      still contributes reciprocal rank 1.0 even though find_match itself would
      have returned None for that query.
    - false_match_rate: over negatives (expected is None), the fraction where
      find_match returned a non-None match (a wrong >= threshold hit).

    Never raises on an empty fixtures list (all rates default to 0.0).
    """
    from src.models.query_template import QueryTemplate
    from src.services.copilot.template_matcher import TemplateMatcher
    from src.services.copilot.template_saver import TemplateSaver

    TemplateSaver().seed_system_templates(db, embedder=resolved)

    templates = db.query(QueryTemplate).filter(QueryTemplate.organization_id.is_(None)).all()
    description_to_id = {t.description: t.id for t in templates}

    matcher = TemplateMatcher()

    n_pos = 0
    n_neg = 0
    recall_hits = 0
    false_matches = 0
    reciprocal_ranks: List[float] = []

    for row in fixtures:
        query = row["query"]
        expected = row["expected"]

        match = matcher.find_match(query, org_id, db, embedder=resolved, threshold=MATCHER_THRESHOLD)

        if expected is not None:
            n_pos += 1
            if match is not None and match["description"] == expected:
                recall_hits += 1

            gold_template_id = description_to_id.get(expected)
            if gold_template_id is not None:
                best_per_template = _best_similarity_per_template(query, resolved, db)
                reciprocal_ranks.append(_reciprocal_rank(best_per_template, gold_template_id))
            else:
                # Fixture's expected description doesn't correspond to any seeded
                # template — treat as an unreachable gold (reciprocal rank 0),
                # never raise.
                reciprocal_ranks.append(0.0)
        else:
            n_neg += 1
            if match is not None:
                false_matches += 1

    recall_at_1 = (recall_hits / n_pos) if n_pos > 0 else 0.0
    mrr = (sum(reciprocal_ranks) / len(reciprocal_ranks)) if reciprocal_ranks else 0.0
    false_match_rate = (false_matches / n_neg) if n_neg > 0 else 0.0

    result = ProviderRetrievalResult(
        provider=resolved.provider,
        model=resolved.model,
        n=len(fixtures),
        n_pos=n_pos,
        n_neg=n_neg,
        recall_at_1=recall_at_1,
        mrr=mrr,
        false_match_rate=false_match_rate,
    )
    return asdict(result)


def compare(baseline: Optional[dict], candidate: Optional[dict]) -> dict:
    """Compare candidate against baseline provider results.

    meets_target: candidate.recall_at_1 - baseline.recall_at_1 >= RECALL_TARGET_DELTA
    AND candidate.false_match_rate <= baseline.false_match_rate (no false-match
    regression allowed even when the recall delta passes).

    If either input is None (provider unavailable at run time), both
    recall_at_1_delta and meets_target are None — there is nothing honest to
    report when one side never ran.
    """
    if baseline is None or candidate is None:
        return {"recall_at_1_delta": None, "meets_target": None}

    delta = candidate["recall_at_1"] - baseline["recall_at_1"]
    meets_target = delta >= RECALL_TARGET_DELTA and candidate["false_match_rate"] <= baseline["false_match_rate"]
    return {"recall_at_1_delta": delta, "meets_target": meets_target}


def run_eval(fixtures: List[dict], providers: Dict[str, Optional[object]], db, org_id: int = 1) -> dict:
    """Run baseline + candidate providers over `fixtures` and assemble the
    committed-artifact-shaped dict (eval_results/retrieval_accuracy.json schema).

    `providers` is keyed "baseline" and "candidate"; either value may already be
    None (provider unavailable at build time — the CLI's job). A run_provider
    failure during the run itself (e.g. a real network error mid-eval) is also
    caught here and degrades that side to null, so run_eval never raises on a
    provider going away mid-run — mirroring eval_sentiment.py's
    transformer_provider=None graceful-skip path.

    Never raises on an empty fixtures list.
    """
    n = len(fixtures)
    n_positives = sum(1 for row in fixtures if row.get("expected") is not None)
    n_negatives = n - n_positives

    results: Dict[str, Optional[dict]] = {}
    for key in ("baseline", "candidate"):
        resolved = providers.get(key)
        if resolved is None:
            results[key] = None
            continue
        try:
            results[key] = run_provider(resolved, fixtures, db, org_id=org_id)
        except Exception as exc:
            logger.warning("run_eval: provider %r failed during run: %s", key, exc)
            results[key] = None

    comparison = compare(results["baseline"], results["candidate"])

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "threshold": MATCHER_THRESHOLD,
        "n": n,
        "n_positives": n_positives,
        "n_negatives": n_negatives,
        "baseline": results["baseline"],
        "candidate": results["candidate"],
        "recall_at_1_delta": comparison["recall_at_1_delta"],
        "meets_target": comparison["meets_target"],
    }


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def _default_fixtures_path() -> str:
    return os.path.join(
        os.path.dirname(__file__), "..", "tests", "fixtures", "embedding_eval", "queries.jsonl"
    )


def _default_output_path() -> str:
    return os.path.join(os.path.dirname(__file__), "..", "eval_results", "retrieval_accuracy.json")


def _build_scratch_db():
    """Build a fresh, throwaway SQLite DB for a real eval run — never touches the
    app's configured database. Seeds a single Organization(id=1) row: system
    templates are org-less (organization_id=None) and find_match's raw-SQL mapping
    query doesn't filter by org_id either, so no FK actually requires this row —
    but it costs nothing and keeps the scratch schema consistent with what the ORM
    models expect a real org-scoped caller to have."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # Import model modules so Base.metadata is fully populated even when this
    # script is run standalone (without src.api.main having imported every route).
    import src.models.organization  # noqa: F401
    import src.models.query_template  # noqa: F401
    import src.models.query_template_mapping  # noqa: F401
    from src.models.base import Base
    from src.models.organization import Organization

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)

    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = session_local()
    db.add(Organization(id=1, name="eval-embeddings scratch org"))
    db.commit()
    return db


def _print_summary(artifact: dict) -> None:
    print(
        f"\n--- Retrieval eval (n={artifact['n']}, pos={artifact['n_positives']}, "
        f"neg={artifact['n_negatives']}, threshold={artifact['threshold']}) ---"
    )
    for key in ("baseline", "candidate"):
        result = artifact[key]
        if result is None:
            print(f"  {key}: not evaluated (provider unavailable — see warning above)")
            continue
        print(
            f"  {key} ({result['provider']}/{result['model']}): "
            f"recall@1={result['recall_at_1']:.4f} MRR={result['mrr']:.4f} "
            f"false_match_rate={result['false_match_rate']:.4f}"
        )

    if artifact["recall_at_1_delta"] is not None:
        print(f"  recall@1 delta (candidate - baseline): {artifact['recall_at_1_delta']:+.4f}")
        verdict = "MEETS" if artifact["meets_target"] else "does NOT meet"
        print(
            f"  {verdict} the >= {RECALL_TARGET_DELTA} recall@1 improvement "
            "(with no false-match regression) target"
        )
    else:
        print("  comparison not available (one or both providers unavailable)")


def main(argv: Optional[List[str]] = None) -> int:
    """Runs the baseline vs candidate comparison, writes the committed results
    artifact, prints a human summary. Always returns 0 — this script is a
    disclosure tool, not a CI gate (mirrors eval_sentiment.py's convention)."""
    parser = argparse.ArgumentParser(
        description="Retrieval eval harness (recall@1 / MRR / false-match rate at the 0.85 matcher threshold)"
    )
    parser.add_argument("--fixtures", type=str, default=_default_fixtures_path())
    parser.add_argument("--output", type=str, default=_default_output_path())
    parser.add_argument("--baseline-provider", type=str, default="ollama")
    parser.add_argument("--baseline-base-url", type=str, default="http://localhost:11434/v1")
    parser.add_argument("--baseline-model", type=str, default="nomic-embed-text")
    parser.add_argument("--candidate-provider", type=str, default="local")
    parser.add_argument("--candidate-model", type=str, default="BAAI/bge-small-en-v1.5")
    args = parser.parse_args(argv)

    fixtures = load_fixtures(args.fixtures)

    db = _build_scratch_db()

    providers: Dict[str, Optional[object]] = {}

    try:
        providers["baseline"] = build_resolved_embedder(
            args.baseline_provider, base_url=args.baseline_base_url, model=args.baseline_model
        )
    except Exception as exc:
        logger.warning(
            "baseline provider %r unavailable — baseline side will be null: %s",
            args.baseline_provider, exc,
        )
        providers["baseline"] = None

    try:
        providers["candidate"] = build_resolved_embedder(
            args.candidate_provider, model=args.candidate_model
        )
    except Exception as exc:
        logger.warning(
            "candidate provider %r unavailable — candidate side will be null: %s",
            args.candidate_provider, exc,
        )
        providers["candidate"] = None

    artifact = run_eval(fixtures, providers, db, org_id=1)

    _print_summary(artifact)
    print(
        "\nDISCLOSURE ONLY — does not block merge. Always exits 0, even if a "
        "provider is unavailable or the target isn't met."
    )

    output_path = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(artifact, f, indent=2)
    print(f"\nResults written to: {output_path}")

    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
