"""Corrections dataset builder — task-generic (sentiment + category), Phase 1
(M5.2 training-and-eval-core).

Split into a pure transform (`rows_to_dataset`) and a lazy-SQL fetch seam
(`fetch_correction_rows`), mirroring the churn split (DB collection is a
thin driver; the math/transform is pure and fully unit-testable with plain dicts).

Gotcha (per plan): internal/frontend-originated corrections don't always populate
`AICorrection.feedback_text` directly — the resolver falls back to the joined
`FeedbackItem.text` via `entity_id` (scoped to the SAME organization_id, to avoid a
cross-org text leak through a stale/foreign entity_id). This applies to both the
sentiment and category correction types.
"""
from __future__ import annotations

from typing import Any

from .labels import SENTIMENT_LABELS, URGENCY_LABELS


def _normalize_label(raw: Any) -> str:
    """Strip whitespace defensively — corrected_value is stored lowercase already,
    but we normalize defensively rather than trust upstream data hygiene."""
    return (raw or "").strip()


def _resolve_text(row: dict) -> str:
    feedback_text = (row.get("feedback_text") or "").strip()
    if feedback_text:
        return feedback_text
    return (row.get("joined_text") or "").strip()


def rows_to_dataset(
    rows: list[dict], allowed_labels: tuple[str, ...] | None = SENTIMENT_LABELS
) -> list[tuple[str, str]]:
    """Pure transform: raw row dicts -> clean (text, label) pairs.

    Each row is a dict with keys {"feedback_text", "joined_text", "corrected_value"}.
    Drops rows with no resolvable text. Label filtering:
      - allowed_labels is a tuple -> drop any row whose corrected_value is not a member
        (sentiment default: SENTIMENT_LABELS — byte-stable pre-change behavior).
      - allowed_labels is None -> dynamic vocab: accept every non-empty corrected_value
        (used by build_category_dataset; the org's own corrections ARE the label space).
    """
    dataset: list[tuple[str, str]] = []
    for row in rows:
        text = _resolve_text(row)
        if not text:
            continue
        label = _normalize_label(row.get("corrected_value"))
        if not label:
            continue
        if allowed_labels is not None and label not in allowed_labels:
            continue
        dataset.append((text, label))
    return dataset


def fetch_correction_rows(org_id: int, db, *, correction_type: str) -> list[dict]:
    """DB seam: fetch raw correction rows of `correction_type` for org_id from AICorrection,
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
          AND ac.correction_type = :correction_type
          AND ac.signal = 'correction'
          AND ac.corrected_value IS NOT NULL
        """
    )
    result = db.execute(query, {"org_id": org_id, "correction_type": correction_type})
    return [
        {
            "feedback_text": row.feedback_text,
            "joined_text": row.joined_text,
            "corrected_value": row.corrected_value,
        }
        for row in result
    ]


def fetch_sentiment_correction_rows(org_id: int, db) -> list[dict]:
    """Thin alias — byte-stable pre-change behavior/name preserved for existing callers."""
    return fetch_correction_rows(org_id, db, correction_type="sentiment")


def build_sentiment_dataset(org_id: int, db) -> list[tuple[str, str]]:
    """Composition: fetch + transform, sentiment-scoped (fixed 3-class vocab)."""
    return rows_to_dataset(fetch_sentiment_correction_rows(org_id, db))


def build_category_dataset(org_id: int, db) -> list[tuple[str, str]]:
    """Composition: fetch + transform, category-scoped (dynamic vocab — allowed_labels=None
    so every distinct corrected_value the org has ever corrected TO becomes a class)."""
    return rows_to_dataset(
        fetch_correction_rows(org_id, db, correction_type="category"), allowed_labels=None
    )


def build_urgency_dataset(org_id: int, db) -> list[tuple[str, str]]:
    """Composition: fetch + transform, urgency-scoped (fixed binary vocab URGENCY_LABELS —
    unlike category's dynamic vocab; junk corrected_values dropped)."""
    return rows_to_dataset(
        fetch_correction_rows(org_id, db, correction_type="urgency"),
        allowed_labels=URGENCY_LABELS,
    )


def derive_labels(dataset: list[tuple[str, str]]) -> tuple[str, ...]:
    """Sorted unique labels present in a (text, label) dataset — the full dynamic label
    set for a category dataset. NOTE (fair-A/B contract, PRD critique #3): this returns the
    FULL set. Callers that need to score an incumbent fairly (e.g. the keyword categorizer,
    which can only emit its own built-in vocab) MUST intersect this result with that
    incumbent's emittable label set before passing it to evaluate(labels=...) — see
    worker-trainer aspect. Passing the unintersected full set to evaluate() when the
    incumbent cannot emit some of those labels structurally depresses the incumbent's
    macro-F1 and over-credits the challenger."""
    return tuple(sorted({label for _, label in dataset}))
