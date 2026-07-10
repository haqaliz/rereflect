"""Tests for corrections_classifier.dataset — Phase 1 (M5.2 training-and-eval-core).

`rows_to_dataset` is pure (plain dicts in, no DB). `fetch_sentiment_correction_rows` /
`build_sentiment_dataset` need sqlalchemy — guarded with `pytest.importorskip` so they
skip gracefully (not fail) where sqlalchemy is unavailable, matching the disclosure/
graceful-skip ethos used throughout this codebase (eval_sentiment.py, calibration_refit.py).
"""
from __future__ import annotations

import pytest

from src.analyzer.corrections_classifier.dataset import rows_to_dataset
from src.analyzer.corrections_classifier.labels import SENTIMENT_LABELS


# ---------------------------------------------------------------------------
# rows_to_dataset — pure transform
# ---------------------------------------------------------------------------

def test_uses_feedback_text_when_present():
    rows = [{"feedback_text": "great job", "joined_text": "other text", "corrected_value": "positive"}]
    assert rows_to_dataset(rows) == [("great job", "positive")]


def test_falls_back_to_joined_feedback_item_text_when_feedback_text_blank():
    rows = [
        {"feedback_text": "", "joined_text": "joined one", "corrected_value": "neutral"},
        {"feedback_text": None, "joined_text": "joined two", "corrected_value": "negative"},
    ]
    assert rows_to_dataset(rows) == [
        ("joined one", "neutral"),
        ("joined two", "negative"),
    ]


def test_drops_row_when_no_resolvable_text():
    rows = [
        {"feedback_text": "", "joined_text": None, "corrected_value": "positive"},
        {"feedback_text": None, "joined_text": "", "corrected_value": "negative"},
        {"feedback_text": "kept", "joined_text": None, "corrected_value": "positive"},
    ]
    assert rows_to_dataset(rows) == [("kept", "positive")]


def test_drops_out_of_vocab_label():
    rows = [
        {"feedback_text": "a", "joined_text": None, "corrected_value": "mixed"},
        {"feedback_text": "b", "joined_text": None, "corrected_value": "positive"},
        {"feedback_text": "c", "joined_text": None, "corrected_value": "neutral"},
        {"feedback_text": "d", "joined_text": None, "corrected_value": "negative"},
    ]
    assert rows_to_dataset(rows) == [
        ("b", "positive"),
        ("c", "neutral"),
        ("d", "negative"),
    ]


def test_label_vocabulary_is_exactly_three():
    rows = [
        {"feedback_text": "a", "joined_text": None, "corrected_value": label}
        for label in ("positive", "neutral", "negative")
    ]
    result = rows_to_dataset(rows)
    assert {label for _, label in result} == set(SENTIMENT_LABELS)
    assert len(SENTIMENT_LABELS) == 3


def test_strips_whitespace_and_preserves_order():
    rows = [
        {"feedback_text": "  first  ", "joined_text": None, "corrected_value": "  positive  "},
        {"feedback_text": " second ", "joined_text": None, "corrected_value": "neutral"},
    ]
    assert rows_to_dataset(rows) == [
        ("first", "positive"),
        ("second", "neutral"),
    ]


def test_empty_input_returns_empty_list():
    assert rows_to_dataset([]) == []


# ---------------------------------------------------------------------------
# DB seam — fetch_sentiment_correction_rows / build_sentiment_dataset
# ---------------------------------------------------------------------------

sa = pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from src.analyzer.corrections_classifier.dataset import (  # noqa: E402
    build_sentiment_dataset,
    fetch_sentiment_correction_rows,
)

_DDL = """
CREATE TABLE feedback_items (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL,
    text TEXT NOT NULL
);

CREATE TABLE ai_corrections (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL,
    correction_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    signal TEXT NOT NULL,
    original_value TEXT,
    corrected_value TEXT,
    feedback_text TEXT
);
"""


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        for stmt in _DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _seed(session, org_id: int = 1, other_org_id: int = 2):
    # feedback item for the join path (org 1)
    session.execute(
        text(
            "INSERT INTO feedback_items (id, organization_id, text) "
            "VALUES (:id, :org, :text)"
        ),
        {"id": 100, "org": org_id, "text": "joined feedback text"},
    )
    # feedback item belonging to ANOTHER org, sharing the same id namespace collision risk
    session.execute(
        text(
            "INSERT INTO feedback_items (id, organization_id, text) "
            "VALUES (:id, :org, :text)"
        ),
        {"id": 200, "org": other_org_id, "text": "other org text — must not leak"},
    )

    corrections = [
        # 1. valid — feedback_text set directly
        dict(
            id=1, org=org_id, correction_type="sentiment", entity_type="feedback_item",
            entity_id=None, signal="correction", original_value="neutral",
            corrected_value="positive", feedback_text="directly set text",
        ),
        # 2. valid — feedback_text blank, resolves via FeedbackItem join (same org)
        dict(
            id=2, org=org_id, correction_type="sentiment", entity_type="feedback_item",
            entity_id=100, signal="correction", original_value="neutral",
            corrected_value="negative", feedback_text=None,
        ),
        # 3. excluded — wrong correction_type
        dict(
            id=3, org=org_id, correction_type="category", entity_type="feedback_item",
            entity_id=100, signal="correction", original_value="bug",
            corrected_value="feature", feedback_text=None,
        ),
        # 4. excluded — wrong signal
        dict(
            id=4, org=org_id, correction_type="sentiment", entity_type="feedback_item",
            entity_id=100, signal="thumbs_down", original_value="neutral",
            corrected_value="negative", feedback_text=None,
        ),
        # 5. excluded — corrected_value IS NULL
        dict(
            id=5, org=org_id, correction_type="sentiment", entity_type="feedback_item",
            entity_id=100, signal="correction", original_value="neutral",
            corrected_value=None, feedback_text=None,
        ),
        # 6. cross-org join leak guard — entity_id points at ANOTHER org's feedback item;
        #    must NOT resolve text (join is scoped to same organization_id) -> dropped
        #    because text is unresolved.
        dict(
            id=6, org=org_id, correction_type="sentiment", entity_type="feedback_item",
            entity_id=200, signal="correction", original_value="neutral",
            corrected_value="positive", feedback_text=None,
        ),
    ]
    for c in corrections:
        session.execute(
            text(
                "INSERT INTO ai_corrections "
                "(id, organization_id, correction_type, entity_type, entity_id, signal, "
                " original_value, corrected_value, feedback_text) "
                "VALUES (:id, :org, :correction_type, :entity_type, :entity_id, :signal, "
                " :original_value, :corrected_value, :feedback_text)"
            ),
            c,
        )
    session.commit()


def test_fetch_query_filters_and_joins(db):
    _seed(db, org_id=1, other_org_id=2)
    dataset = build_sentiment_dataset(1, db)
    assert dataset == [
        ("directly set text", "positive"),
        ("joined feedback text", "negative"),
    ]


def test_fetch_returns_raw_rows_with_expected_keys(db):
    _seed(db, org_id=1, other_org_id=2)
    rows = fetch_sentiment_correction_rows(1, db)
    assert len(rows) == 3  # rows 1, 2, and 6 pass the SQL filter; row 6's text won't resolve
    for row in rows:
        assert set(row.keys()) == {"feedback_text", "joined_text", "corrected_value"}
