"""
Validation tests for the held-out retrieval-eval fixtures (local-embedding-quality,
aspect retrieval-eval-card, Task 1).

These fixtures back an eval of embedding retrieval quality: given a user query, does
the matcher retrieve the correct copilot system template (or correctly abstain via
`expected: null`)?  For the eval to be meaningful, the fixture queries must NOT be
copies of the seeded `question_patterns` in SYSTEM_TEMPLATES — that would make the
eval tautological (querying with the exact string that was embedded at seed time is
not a real retrieval test).

RED (before fixtures exist): every test below fails because queries.jsonl /
queries_tiny.jsonl are missing.
GREEN (after authoring fixtures): all six acceptance criteria pass.
"""

import json
from pathlib import Path

import pytest

from src.services.copilot.template_saver import SYSTEM_TEMPLATES

FIXTURES_DIR = Path(__file__).parent
QUERIES_PATH = FIXTURES_DIR / "queries.jsonl"
QUERIES_TINY_PATH = FIXTURES_DIR / "queries_tiny.jsonl"

MIN_TOTAL_ROWS = 60
MIN_NEGATIVE_ROWS = 15
MIN_COVERAGE_PER_TEMPLATE = 2


def _load_jsonl(path: Path) -> list[dict]:
    assert path.exists(), f"fixture file missing: {path}"
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                pytest.fail(f"{path.name}:{line_no}: invalid JSON ({e}): {raw_line!r}")
            rows.append(obj)
    return rows


@pytest.fixture(scope="module")
def all_descriptions() -> set:
    return {t["description"] for t in SYSTEM_TEMPLATES}


@pytest.fixture(scope="module")
def all_question_patterns() -> set:
    """Union of every seeded question_pattern across all 15 templates, normalized
    the same way the fixtures must be checked (case-insensitive, stripped)."""
    patterns = set()
    for t in SYSTEM_TEMPLATES:
        for p in t["question_patterns"]:
            patterns.add(p.strip().lower())
    return patterns


@pytest.fixture(scope="module")
def queries_rows() -> list[dict]:
    return _load_jsonl(QUERIES_PATH)


@pytest.fixture(scope="module")
def queries_tiny_rows() -> list[dict]:
    return _load_jsonl(QUERIES_TINY_PATH)


class TestQueriesJsonlShape:
    """Criterion 1: queries.jsonl parses; every row has query: str, expected: str|None."""

    def test_every_row_has_required_fields_with_correct_types(self, queries_rows):
        assert len(queries_rows) > 0, "queries.jsonl is empty"
        for i, row in enumerate(queries_rows):
            assert "query" in row, f"row {i} missing 'query': {row}"
            assert "expected" in row, f"row {i} missing 'expected': {row}"
            assert isinstance(row["query"], str) and row["query"].strip(), (
                f"row {i} 'query' must be a non-empty string: {row}"
            )
            assert row["expected"] is None or isinstance(row["expected"], str), (
                f"row {i} 'expected' must be str or null: {row}"
            )


class TestRowCounts:
    """Criterion 2: >= 60 rows total; >= 15 rows with expected is None."""

    def test_at_least_60_rows(self, queries_rows):
        assert len(queries_rows) >= MIN_TOTAL_ROWS, (
            f"expected >= {MIN_TOTAL_ROWS} rows, got {len(queries_rows)}"
        )

    def test_at_least_15_negatives(self, queries_rows):
        negatives = [r for r in queries_rows if r["expected"] is None]
        assert len(negatives) >= MIN_NEGATIVE_ROWS, (
            f"expected >= {MIN_NEGATIVE_ROWS} rows with expected=null, got {len(negatives)}"
        )


class TestExpectedIsRealDescription:
    """Criterion 3: every non-null expected is exactly one of the 15 real
    SYSTEM_TEMPLATES descriptions (guards typos/drift)."""

    def test_positive_expected_values_are_real_template_descriptions(
        self, queries_rows, all_descriptions
    ):
        assert len(all_descriptions) == 15, (
            f"sanity check failed: SYSTEM_TEMPLATES should have 15 descriptions, "
            f"got {len(all_descriptions)} — brief/source may have drifted"
        )
        for i, row in enumerate(queries_rows):
            if row["expected"] is not None:
                assert row["expected"] in all_descriptions, (
                    f"row {i} expected={row['expected']!r} is not one of the 15 "
                    f"real SYSTEM_TEMPLATES descriptions: {row}"
                )


class TestNonTautology:
    """Criterion 4: no query (case-insensitive, stripped) equals any seeded
    question_pattern across all 15 templates. Verbatim reuse would embed to
    ~1.0 similarity trivially, making the eval meaningless."""

    def test_queries_disjoint_from_seeded_question_patterns(
        self, queries_rows, all_question_patterns
    ):
        collisions = []
        for i, row in enumerate(queries_rows):
            normalized = row["query"].strip().lower()
            if normalized in all_question_patterns:
                collisions.append((i, row["query"]))
        assert not collisions, (
            f"fixture queries must not verbatim-reuse seeded question_patterns "
            f"(tautological eval): {collisions}"
        )


class TestCoverage:
    """Criterion 5: every template description appears as the expected of at
    least 2 positive rows."""

    def test_every_template_has_at_least_two_positive_rows(
        self, queries_rows, all_descriptions
    ):
        counts = {}
        for row in queries_rows:
            if row["expected"] is not None:
                counts[row["expected"]] = counts.get(row["expected"], 0) + 1

        under_covered = {
            desc: counts.get(desc, 0)
            for desc in all_descriptions
            if counts.get(desc, 0) < MIN_COVERAGE_PER_TEMPLATE
        }
        assert not under_covered, (
            f"every template description needs >= {MIN_COVERAGE_PER_TEMPLATE} "
            f"positive rows; under-covered: {under_covered}"
        )


class TestQueriesTinyJsonl:
    """Criterion 6: queries_tiny.jsonl parses and has >= 1 negative."""

    def test_queries_tiny_parses_and_has_shape(self, queries_tiny_rows):
        assert len(queries_tiny_rows) > 0, "queries_tiny.jsonl is empty"
        for i, row in enumerate(queries_tiny_rows):
            assert "query" in row and "expected" in row, f"row {i}: {row}"
            assert isinstance(row["query"], str) and row["query"].strip()
            assert row["expected"] is None or isinstance(row["expected"], str)

    def test_queries_tiny_has_at_least_one_negative(self, queries_tiny_rows):
        negatives = [r for r in queries_tiny_rows if r["expected"] is None]
        assert len(negatives) >= 1, "queries_tiny.jsonl must have >= 1 negative row"
