"""
TDD tests for the pure churn-suggestion decision core (harvester-core aspect).

Pure asserts only — no I/O, no fixtures, no DB, no mocks, no `patch`.
"""

from __future__ import annotations

import os

from src.services.churn_harvest_core import (
    SUGGESTION_DENY_REASONS,
    decide_suggestion,
)


class TestDenyReasonOrder:
    def test_deny_reasons_tuple_is_fixed_and_ordered(self):
        assert SUGGESTION_DENY_REASONS == (
            "not_closed",
            "won",
            "discriminator_not_configured",
            "no_discriminator",
            "unknown_customer",
        )

    def test_record_tripping_all_four_denies_not_closed_first(self):
        # is_closed=False AND is_won=True AND no renewal_set AND no discriminator
        # AND unknown email — the fixed order asserts not_closed wins.
        suggest, reason = decide_suggestion(
            is_closed=False,
            is_won=True,
            discriminator=None,
            renewal_set=None,
            customer_email=None,
            known_emails=frozenset(),
        )
        assert (suggest, reason) == (False, "not_closed")


class TestDenyPaths:
    def test_not_closed_denies(self):
        suggest, reason = decide_suggestion(
            is_closed=False,
            is_won=False,
            discriminator="Renewal",
            renewal_set=frozenset({"Renewal"}),
            customer_email="a@example.com",
            known_emails=frozenset({"a@example.com"}),
        )
        assert (suggest, reason) == (False, "not_closed")

    def test_won_denies(self):
        suggest, reason = decide_suggestion(
            is_closed=True,
            is_won=True,
            discriminator="Renewal",
            renewal_set=frozenset({"Renewal"}),
            customer_email="a@example.com",
            known_emails=frozenset({"a@example.com"}),
        )
        assert (suggest, reason) == (False, "won")

    def test_renewal_set_none_denies_discriminator_not_configured(self):
        suggest, reason = decide_suggestion(
            is_closed=True,
            is_won=False,
            discriminator="Renewal",
            renewal_set=None,
            customer_email="a@example.com",
            known_emails=frozenset({"a@example.com"}),
        )
        assert (suggest, reason) == (False, "discriminator_not_configured")

    def test_renewal_set_empty_denies_discriminator_not_configured(self):
        suggest, reason = decide_suggestion(
            is_closed=True,
            is_won=False,
            discriminator="Renewal",
            renewal_set=frozenset(),
            customer_email="a@example.com",
            known_emails=frozenset({"a@example.com"}),
        )
        assert (suggest, reason) == (False, "discriminator_not_configured")

    def test_discriminator_none_denies_no_discriminator(self):
        suggest, reason = decide_suggestion(
            is_closed=True,
            is_won=False,
            discriminator=None,
            renewal_set=frozenset({"Renewal"}),
            customer_email="a@example.com",
            known_emails=frozenset({"a@example.com"}),
        )
        assert (suggest, reason) == (False, "no_discriminator")

    def test_discriminator_blank_denies_no_discriminator(self):
        suggest, reason = decide_suggestion(
            is_closed=True,
            is_won=False,
            discriminator="",
            renewal_set=frozenset({"Renewal"}),
            customer_email="a@example.com",
            known_emails=frozenset({"a@example.com"}),
        )
        assert (suggest, reason) == (False, "no_discriminator")

    def test_unknown_email_denies_unknown_customer(self):
        suggest, reason = decide_suggestion(
            is_closed=True,
            is_won=False,
            discriminator="Renewal",
            renewal_set=frozenset({"Renewal"}),
            customer_email="unknown@example.com",
            known_emails=frozenset({"a@example.com"}),
        )
        assert (suggest, reason) == (False, "unknown_customer")

    def test_customer_email_none_denies_unknown_customer(self):
        suggest, reason = decide_suggestion(
            is_closed=True,
            is_won=False,
            discriminator="Renewal",
            renewal_set=frozenset({"Renewal"}),
            customer_email=None,
            known_emails=frozenset({"a@example.com"}),
        )
        assert (suggest, reason) == (False, "unknown_customer")

    def test_near_match_lowercase_denies_exact_match_only(self):
        # renewal_set has "Renewal"; a lowercase near-match must NOT match —
        # no regex/normalization/prefix matching (M2).
        suggest, reason = decide_suggestion(
            is_closed=True,
            is_won=False,
            discriminator="renewal",
            renewal_set=frozenset({"Renewal"}),
            customer_email="a@example.com",
            known_emails=frozenset({"a@example.com"}),
        )
        assert suggest is False

    def test_near_match_trailing_space_denies(self):
        suggest, reason = decide_suggestion(
            is_closed=True,
            is_won=False,
            discriminator="Renewal ",
            renewal_set=frozenset({"Renewal"}),
            customer_email="a@example.com",
            known_emails=frozenset({"a@example.com"}),
        )
        assert suggest is False

    def test_near_match_prefix_denies(self):
        suggest, reason = decide_suggestion(
            is_closed=True,
            is_won=False,
            discriminator="Renew",
            renewal_set=frozenset({"Renewal"}),
            customer_email="a@example.com",
            known_emails=frozenset({"a@example.com"}),
        )
        assert suggest is False


class TestSuggestPath:
    def test_suggests_when_all_conditions_met(self):
        suggest, reason = decide_suggestion(
            is_closed=True,
            is_won=False,
            discriminator="Renewal",
            renewal_set=frozenset({"Renewal"}),
            customer_email="a@example.com",
            known_emails=frozenset({"a@example.com"}),
        )
        assert (suggest, reason) == (True, None)


class TestPurityGuard:
    """Source-level drift guard (AC 9): the two pure modules must never grow
    a Celery/SQLAlchemy/FastAPI/httpx/client import. Mirrors the purity
    contract asserted by status_sync_core.py's docstring."""

    FORBIDDEN_TOKENS = ("celery", "sqlalchemy", "fastapi", "httpx", "client")

    def _source_lines(self, relative_path: str) -> list[str]:
        here = os.path.dirname(os.path.abspath(__file__))
        full_path = os.path.join(here, "..", relative_path)
        with open(full_path, "r", encoding="utf-8") as fh:
            return fh.readlines()

    def _assert_no_forbidden_imports(self, relative_path: str) -> None:
        for line in self._source_lines(relative_path):
            stripped = line.strip()
            if not (stripped.startswith("import ") or stripped.startswith("from ")):
                continue
            lowered = stripped.lower()
            for token in self.FORBIDDEN_TOKENS:
                assert token not in lowered, (
                    f"{relative_path} imports forbidden token {token!r}: {stripped!r}"
                )

    def test_churn_harvest_core_has_no_forbidden_imports(self):
        self._assert_no_forbidden_imports("src/services/churn_harvest_core.py")

    def test_churn_harvest_adapters_has_no_forbidden_imports(self):
        self._assert_no_forbidden_imports("src/services/churn_harvest_adapters.py")
