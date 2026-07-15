"""
TDD tests for churn_backfill.run_backfill (historical-backfill aspect).

Strategy (mirrors test_churn_suggestion_harvester.py): file-local in-memory
SQLite engine (not conftest's) + a hand-written Fake client class — no
MagicMock, no `patch`. run_backfill MUST reuse
churn_suggestion_harvester._process_raw_record (AC-3 — no fork); this file
proves that structurally, by diffing persisted rows against a
harvest_org_suggestions run of the identical raw record.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from src.models import Base, ChurnLabelSuggestion, CustomerChurnEvent
from src.services.churn_backfill import (
    BACKFILL_SUGGESTION_CAP,
    DEFAULT_BACKFILL_MONTHS,
    MAX_BACKFILL_MONTHS,
    run_backfill,
)
from src.services.churn_harvest_adapters import _parse_close_date
from src.services.churn_suggestion_harvester import harvest_org_suggestions

# ---------------------------------------------------------------------------
# In-memory SQLite engine (isolated, file-local — not conftest's)
# ---------------------------------------------------------------------------

_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_ENGINE)


@pytest.fixture(autouse=True)
def _fresh_db():
    Base.metadata.create_all(bind=_ENGINE)
    yield
    Base.metadata.drop_all(bind=_ENGINE)


@pytest.fixture()
def db() -> Session:
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Hand-written Fake client (no MagicMock, no patch) — honors `since` like the
# real HubSpotClient/SalesforceClient accessors (Phase 2), so AC-2 window
# tests exercise realistic filtering without needing httpx.
# ---------------------------------------------------------------------------


class FakeCrmClient:
    def __init__(self, deals_by_company=None, opps_by_account=None, raises=False):
        self.deals_by_company = deals_by_company or {}
        self.opps_by_account = opps_by_account or {}
        self.raises = raises
        self.deal_calls: list[tuple[str, object]] = []
        self.opp_calls: list[tuple[str, object]] = []

    @staticmethod
    def _naive(dt):
        """Mirror HubSpotClient's naive-floor comparison (Phase 2)."""
        return dt.replace(tzinfo=None) if dt.tzinfo else dt

    def get_closed_lost_deals_for_company(self, company_id, *, since=None):
        if self.raises:
            raise RuntimeError("boom: hubspot fetch failed")
        self.deal_calls.append((company_id, since))
        deals = self.deals_by_company.get(company_id, [])
        if since is None:
            return deals
        return [
            d for d in deals
            if (dt := _parse_close_date(d.get("properties", {}).get("closedate")))
            and self._naive(dt) >= since
        ]

    def get_lost_opportunities(self, account_id, *, since=None):
        if self.raises:
            raise RuntimeError("boom: salesforce fetch failed")
        self.opp_calls.append((account_id, since))
        opps = self.opps_by_account.get(account_id, [])
        if since is None:
            return opps
        return [
            o for o in opps
            if (dt := _parse_close_date(o.get("CloseDate")))
            and self._naive(dt) >= since
        ]


def _hs_deal(deal_id: str, close_date: str, pipeline: str = "renewal") -> dict:
    return {
        "id": deal_id,
        "properties": {
            "dealname": f"Deal {deal_id}",
            "dealstage": "closedlost",
            "amount": "1000",
            "closedate": close_date,
            "pipeline": pipeline,
        },
    }


RENEWAL_SET = frozenset({"renewal"})
KNOWN_EMAILS = frozenset({"alice@example.com"})

_NOW = datetime.utcnow()
_INSIDE_WINDOW = (_NOW - timedelta(days=30)).strftime("%Y-%m-%dT00:00:00Z")
_OUTSIDE_WINDOW = (_NOW - timedelta(days=365 * 3)).strftime("%Y-%m-%dT00:00:00Z")


class TestConstants:
    def test_default_months_is_24(self):
        assert DEFAULT_BACKFILL_MONTHS == 24

    def test_max_months_is_60(self):
        assert MAX_BACKFILL_MONTHS == 60

    def test_cap_is_2000(self):
        assert BACKFILL_SUGGESTION_CAP == 2000


class TestWindowFloor:
    def test_default_months_close_date_before_floor_yields_no_suggestion(self, db):
        client = FakeCrmClient(
            deals_by_company={"co1": [_hs_deal("d-old", _OUTSIDE_WINDOW)]}
        )

        result = run_backfill(
            1, db, client,
            provider="hubspot",
            renewal_set=RENEWAL_SET,
            known_emails=KNOWN_EMAILS,
            company_ids={"alice@example.com": "co1"},
        )

        assert result["suggested"] == 0
        assert db.query(ChurnLabelSuggestion).count() == 0
        assert db.query(CustomerChurnEvent).count() == 0

    def test_close_date_inside_floor_yields_exactly_one_suggestion(self, db):
        client = FakeCrmClient(
            deals_by_company={"co1": [_hs_deal("d-new", _INSIDE_WINDOW)]}
        )

        result = run_backfill(
            1, db, client,
            provider="hubspot",
            renewal_set=RENEWAL_SET,
            known_emails=KNOWN_EMAILS,
            company_ids={"alice@example.com": "co1"},
        )

        assert result["suggested"] == 1
        assert db.query(ChurnLabelSuggestion).count() == 1
        assert db.query(CustomerChurnEvent).count() == 0

    def test_custom_months_widens_floor_to_include_older_deal(self, db):
        client = FakeCrmClient(
            deals_by_company={"co1": [_hs_deal("d-old", _OUTSIDE_WINDOW)]}
        )

        result = run_backfill(
            1, db, client,
            provider="hubspot",
            renewal_set=RENEWAL_SET,
            known_emails=KNOWN_EMAILS,
            company_ids={"alice@example.com": "co1"},
            months=60,
        )

        assert result["suggested"] == 1
        assert db.query(CustomerChurnEvent).count() == 0


class TestNoFork:
    """AC-3 — byte-identical suggestion row + zero-suggestion agreement
    between run_backfill and harvest_org_suggestions for the same raw record.
    """

    def test_same_record_produces_byte_identical_suggestion_via_both_paths(self, db):
        deal = _hs_deal("d1", _INSIDE_WINDOW)

        backfill_client = FakeCrmClient(deals_by_company={"co1": [deal]})
        run_backfill(
            101, db, backfill_client,
            provider="hubspot",
            renewal_set=RENEWAL_SET,
            known_emails=KNOWN_EMAILS,
            company_ids={"alice@example.com": "co1"},
        )
        backfill_row = (
            db.query(ChurnLabelSuggestion)
            .filter_by(organization_id=101)
            .one()
        )

        harvest_client = FakeCrmClient(deals_by_company={"co1": [deal]})
        harvest_org_suggestions(
            102, db, harvest_client,
            provider="hubspot",
            renewal_set=RENEWAL_SET,
            known_emails=KNOWN_EMAILS,
            company_ids={"alice@example.com": "co1"},
        )
        harvest_row = (
            db.query(ChurnLabelSuggestion)
            .filter_by(organization_id=102)
            .one()
        )

        assert (
            backfill_row.customer_email,
            backfill_row.provider,
            backfill_row.external_opportunity_id,
            backfill_row.suggested_churned_at,
            backfill_row.evidence,
            backfill_row.status,
        ) == (
            harvest_row.customer_email,
            harvest_row.provider,
            harvest_row.external_opportunity_id,
            harvest_row.suggested_churned_at,
            harvest_row.evidence,
            harvest_row.status,
        )
        assert db.query(CustomerChurnEvent).count() == 0

    def test_null_discriminator_yields_zero_suggestions_in_both_paths(self, db):
        deal = _hs_deal("d-nodisc", _INSIDE_WINDOW, pipeline=None)

        backfill_client = FakeCrmClient(deals_by_company={"co1": [deal]})
        backfill_result = run_backfill(
            201, db, backfill_client,
            provider="hubspot",
            renewal_set=RENEWAL_SET,
            known_emails=KNOWN_EMAILS,
            company_ids={"alice@example.com": "co1"},
        )

        harvest_client = FakeCrmClient(deals_by_company={"co1": [deal]})
        harvest_result = harvest_org_suggestions(
            202, db, harvest_client,
            provider="hubspot",
            renewal_set=RENEWAL_SET,
            known_emails=KNOWN_EMAILS,
            company_ids={"alice@example.com": "co1"},
        )

        assert backfill_result["suggested"] == 0
        assert harvest_result["suggested"] == 0
        assert db.query(ChurnLabelSuggestion).count() == 0
        assert db.query(CustomerChurnEvent).count() == 0

    def test_unconfigured_renewal_set_yields_zero_suggestions_in_both_paths(self, db):
        deal = _hs_deal("d-unconf", _INSIDE_WINDOW, pipeline="renewal")

        backfill_client = FakeCrmClient(deals_by_company={"co1": [deal]})
        backfill_result = run_backfill(
            301, db, backfill_client,
            provider="hubspot",
            renewal_set=frozenset(),
            known_emails=KNOWN_EMAILS,
            company_ids={"alice@example.com": "co1"},
        )

        harvest_client = FakeCrmClient(deals_by_company={"co1": [deal]})
        harvest_result = harvest_org_suggestions(
            302, db, harvest_client,
            provider="hubspot",
            renewal_set=frozenset(),
            known_emails=KNOWN_EMAILS,
            company_ids={"alice@example.com": "co1"},
        )

        assert backfill_result["suggested"] == 0
        assert harvest_result["suggested"] == 0
        assert db.query(ChurnLabelSuggestion).count() == 0
        assert db.query(CustomerChurnEvent).count() == 0

    def test_unknown_customer_yields_zero_suggestions_in_both_paths(self, db):
        deal = _hs_deal("d-unknown", _INSIDE_WINDOW)

        backfill_client = FakeCrmClient(deals_by_company={"co1": [deal]})
        backfill_result = run_backfill(
            401, db, backfill_client,
            provider="hubspot",
            renewal_set=RENEWAL_SET,
            known_emails=frozenset(),  # alice is not known
            company_ids={"alice@example.com": "co1"},
        )

        harvest_client = FakeCrmClient(deals_by_company={"co1": [deal]})
        harvest_result = harvest_org_suggestions(
            402, db, harvest_client,
            provider="hubspot",
            renewal_set=RENEWAL_SET,
            known_emails=frozenset(),
            company_ids={"alice@example.com": "co1"},
        )

        assert backfill_result["suggested"] == 0
        assert harvest_result["suggested"] == 0
        assert db.query(CustomerChurnEvent).count() == 0


class TestIdempotentAndResumable:
    def test_same_window_run_twice_creates_suggestion_once(self, db):
        kwargs = dict(
            provider="hubspot",
            renewal_set=RENEWAL_SET,
            known_emails=KNOWN_EMAILS,
            company_ids={"alice@example.com": "co1"},
        )
        client1 = FakeCrmClient(deals_by_company={"co1": [_hs_deal("d1", _INSIDE_WINDOW)]})
        first = run_backfill(1, db, client1, **kwargs)
        assert first["suggested"] == 1

        client2 = FakeCrmClient(deals_by_company={"co1": [_hs_deal("d1", _INSIDE_WINDOW)]})
        second = run_backfill(1, db, client2, **kwargs)

        assert second["suggested"] == 0
        assert second["skipped_existing"] == 1
        assert db.query(ChurnLabelSuggestion).count() == 1
        assert db.query(CustomerChurnEvent).count() == 0

    def test_abort_after_first_unit_then_rerun_completes_with_no_duplicates(self, db):
        kwargs = dict(
            provider="hubspot",
            renewal_set=RENEWAL_SET,
            known_emails=frozenset({"alice@example.com", "bob@example.com"}),
            company_ids={"alice@example.com": "co1", "bob@example.com": "co2"},
        )

        aborted_after_first = {"n": 0}

        def abort_after_one():
            aborted_after_first["n"] += 1
            return aborted_after_first["n"] > 1

        client1 = FakeCrmClient(
            deals_by_company={
                "co1": [_hs_deal("d1", _INSIDE_WINDOW)],
                "co2": [_hs_deal("d2", _INSIDE_WINDOW)],
            }
        )
        first = run_backfill(1, db, client1, should_abort=abort_after_one, **kwargs)
        assert first["status"] == "cancelled"
        assert db.query(ChurnLabelSuggestion).count() == 1  # only co1 processed

        client2 = FakeCrmClient(
            deals_by_company={
                "co1": [_hs_deal("d1", _INSIDE_WINDOW)],
                "co2": [_hs_deal("d2", _INSIDE_WINDOW)],
            }
        )
        second = run_backfill(1, db, client2, **kwargs)

        assert second["status"] == "success"
        rows = db.query(ChurnLabelSuggestion).all()
        assert len(rows) == 2
        ext_ids = {r.external_opportunity_id for r in rows}
        assert ext_ids == {"d1", "d2"}
        assert db.query(CustomerChurnEvent).count() == 0

    def test_rejected_suggestion_is_not_resurrected(self, db):
        rejected = ChurnLabelSuggestion(
            organization_id=1,
            customer_email="alice@example.com",
            provider="hubspot",
            external_opportunity_id="d1",
            suggested_churned_at=datetime(2024, 1, 1),
            evidence={},
            status="rejected",
        )
        db.add(rejected)
        db.commit()

        client = FakeCrmClient(deals_by_company={"co1": [_hs_deal("d1", _INSIDE_WINDOW)]})
        result = run_backfill(
            1, db, client,
            provider="hubspot",
            renewal_set=RENEWAL_SET,
            known_emails=KNOWN_EMAILS,
            company_ids={"alice@example.com": "co1"},
        )

        assert result["suggested"] == 0
        assert result["skipped_existing"] == 1
        row = db.query(ChurnLabelSuggestion).filter_by(external_opportunity_id="d1").one()
        assert row.status == "rejected"
        assert db.query(CustomerChurnEvent).count() == 0


class TestNoSilentCap:
    def test_cap_drops_remainder_and_logs_count_and_window(self, db, caplog):
        deals = [_hs_deal(f"d{i}", _INSIDE_WINDOW) for i in range(10)]
        client = FakeCrmClient(deals_by_company={"co1": deals})

        with caplog.at_level(logging.WARNING):
            result = run_backfill(
                1, db, client,
                provider="hubspot",
                renewal_set=RENEWAL_SET,
                known_emails=KNOWN_EMAILS,
                company_ids={"alice@example.com": "co1"},
                cap=5,
            )

        assert result["suggested"] == 5
        assert result["dropped_by_cap"] == 5
        assert db.query(ChurnLabelSuggestion).count() == 5
        assert db.query(CustomerChurnEvent).count() == 0

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warning_records, "expected a WARNING log for the cap"
        message = warning_records[0].getMessage()
        assert "5" in message
        assert "hubspot" in message
        # "covered window" — the log must name the floor actually used.
        assert "since" in message.lower() or "window" in message.lower()


class TestCancellationBeforeAnyFetch:
    def test_should_abort_true_before_first_unit_returns_cancelled_with_zero_counters(self, db):
        client = FakeCrmClient(deals_by_company={"co1": [_hs_deal("d1", _INSIDE_WINDOW)]})

        result = run_backfill(
            1, db, client,
            provider="hubspot",
            renewal_set=RENEWAL_SET,
            known_emails=KNOWN_EMAILS,
            company_ids={"alice@example.com": "co1"},
            should_abort=lambda: True,
        )

        assert result["status"] == "cancelled"
        assert result["scanned"] == 0
        assert client.deal_calls == []
        assert db.query(ChurnLabelSuggestion).count() == 0
        assert db.query(CustomerChurnEvent).count() == 0


class TestProgressCallback:
    def test_on_progress_called_after_each_fetch_unit(self, db):
        calls = []
        client = FakeCrmClient(
            deals_by_company={
                "co1": [_hs_deal("d1", _INSIDE_WINDOW)],
                "co2": [_hs_deal("d2", _INSIDE_WINDOW)],
            }
        )

        run_backfill(
            1, db, client,
            provider="hubspot",
            renewal_set=RENEWAL_SET,
            known_emails=frozenset({"alice@example.com", "bob@example.com"}),
            company_ids={"alice@example.com": "co1", "bob@example.com": "co2"},
            on_progress=lambda counters: calls.append(dict(counters)),
        )

        assert len(calls) == 2
        assert calls[-1]["suggested"] == 2
        assert db.query(CustomerChurnEvent).count() == 0


class TestThrottle:
    def test_throttle_called_between_fetch_units(self, db):
        sleep_calls = []
        client = FakeCrmClient(
            deals_by_company={
                "co1": [_hs_deal("d1", _INSIDE_WINDOW)],
                "co2": [_hs_deal("d2", _INSIDE_WINDOW)],
            }
        )

        run_backfill(
            1, db, client,
            provider="hubspot",
            renewal_set=RENEWAL_SET,
            known_emails=frozenset({"alice@example.com", "bob@example.com"}),
            company_ids={"alice@example.com": "co1", "bob@example.com": "co2"},
            throttle=lambda secs: sleep_calls.append(secs),
        )

        assert len(sleep_calls) >= 1
        assert db.query(CustomerChurnEvent).count() == 0
