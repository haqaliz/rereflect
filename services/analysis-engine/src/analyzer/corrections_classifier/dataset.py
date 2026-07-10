"""Sentiment corrections dataset builder — Phase 1 (M5.2 training-and-eval-core).

Split into a pure transform (`rows_to_dataset`) and a lazy-SQL fetch seam
(`fetch_sentiment_correction_rows`), mirroring the churn split (DB collection is a
thin driver; the math/transform is pure and fully unit-testable with plain dicts).

Gotcha (per plan): internal/frontend-originated sentiment corrections don't always
populate `AICorrection.feedback_text` directly — the resolver falls back to the
joined `FeedbackItem.text` via `entity_id` (scoped to the SAME organization_id, to
avoid a cross-org text leak through a stale/foreign entity_id).
"""
from __future__ import annotations

from typing import Any

from .labels import SENTIMENT_LABELS


def _normalize_label(raw: Any) -> str:
    """Strip whitespace defensively — corrected_value is stored lowercase already,
    but we normalize defensively rather than trust upstream data hygiene."""
    return (raw or "").strip()


def _resolve_text(row: dict) -> str:
    feedback_text = (row.get("feedback_text") or "").strip()
    if feedback_text:
        return feedback_text
    return (row.get("joined_text") or "").strip()


def rows_to_dataset(rows: list[dict]) -> list[tuple[str, str]]:
    """Pure transform: raw row dicts -> clean (text, label) pairs.

    Each row is a dict with keys {"feedback_text", "joined_text", "corrected_value"}.
    Drops rows with no resolvable text (both feedback_text and joined_text blank/None)
    and rows whose corrected_value is not one of SENTIMENT_LABELS.
    """
    dataset: list[tuple[str, str]] = []
    for row in rows:
        text = _resolve_text(row)
        if not text:
            continue
        label = _normalize_label(row.get("corrected_value"))
        if label not in SENTIMENT_LABELS:
            continue
        dataset.append((text, label))
    return dataset


def fetch_sentiment_correction_rows(org_id: int, db) -> list[dict]:
    """DB seam: fetch raw sentiment-correction rows for org_id from AICorrection,
    left-joined to FeedbackItem (same org only) for the text fallback.

    Lazy `sqlalchemy` import so this module (and the package as a whole) stays
    importable without sqlalchemy installed — only this one function needs it.
    """
    from sqlalchemy import text

    query = text(
        """
        SELECT ac.feedback_text                       AS feedback_text,
               fi.text                                AS joined_text,
               ac.corrected_value                     AS corrected_value
        FROM ai_corrections ac
        LEFT JOIN feedback_items fi
          ON fi.id = ac.entity_id
         AND fi.organization_id = ac.organization_id
        WHERE ac.organization_id = :org_id
          AND ac.correction_type = 'sentiment'
          AND ac.signal = 'correction'
          AND ac.corrected_value IS NOT NULL
        """
    )
    result = db.execute(query, {"org_id": org_id})
    return [
        {
            "feedback_text": row.feedback_text,
            "joined_text": row.joined_text,
            "corrected_value": row.corrected_value,
        }
        for row in result
    ]


def build_sentiment_dataset(org_id: int, db) -> list[tuple[str, str]]:
    """Composition: fetch + transform. The one DB-touching public entry point."""
    return rows_to_dataset(fetch_sentiment_correction_rows(org_id, db))
