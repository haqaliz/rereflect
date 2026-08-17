"""Contract tests for the Intercom webhook -> adapter envelope seam.

WHY THIS FILE EXISTS
--------------------
Intercom ingestion produced no feedback item in any release up to 1.0.0. The
backend route queued `payload["data"]` (the unwrapped inner object) while
`IntercomAdapter` reads `topic` and `data.item` off the FULL envelope. Both
sides were tested, both suites were green, and they disagreed with each other:

  * `tests/test_intercom_adapter.py` feeds the adapter the full envelope
    (see its `{"topic": ..., "data": {"item": ...}}` literals) and passes.
  * `services/backend-api/tests/test_intercom.py` asserted the stripped shape
    and passed.

Neither could catch the defect, because the two halves live in different
services -- worker-service cannot import backend-api, the suites run from
different working directories, and no single test could see both ends. That is
the whole reason the seam went unguarded, and it is why adding another
one-sided test would have left it exactly as exposed.

THE CONTRACT
------------
`tests/fixtures/intercom_webhook_envelope.json` is the golden envelope. It is
read by BOTH suites:

  * here, asserting "given this envelope, the adapter produces a feedback item";
  * in `services/backend-api/tests/test_intercom.py`, asserting "the payload I
    hand to the queue IS this envelope".

Either side drifting from the shape breaks its own assertion against the shared
file. Keep those two halves in agreement.

The envelope's shape is derived from the literals already encoded in the
passing `tests/test_intercom_adapter.py::TestCheckTriggers` cases, so the
fixture does not invent a shape -- it promotes the one the adapter was always
written against.

See docs/planning/intercom-selfhost-ingestion/envelope-seam-fix/.
"""

import copy
import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.adapters.intercom import IntercomAdapter
from src.adapters.intercom_parts import extract_rating, extract_reply_parts
from src.models import FeedbackSource, Integration, Organization

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "intercom_webhook_envelope.json"


def load_golden_envelope() -> dict:
    """Load the shared contract fixture.

    Deliberately raises rather than skipping when the file is missing. A
    `pytest.skip` here would recreate precisely the silent-gap failure this
    file exists to close: a green suite that proves nothing.
    """
    if not FIXTURE_PATH.exists():
        raise AssertionError(
            f"Golden Intercom envelope fixture missing at {FIXTURE_PATH}. "
            "It is a shared contract also read by "
            "services/backend-api/tests/test_intercom.py -- restore it rather "
            "than skipping this test."
        )
    return json.loads(FIXTURE_PATH.read_text())


REPLY_FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "intercom_webhook_reply_envelope.json"
)

RATING_FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "intercom_webhook_rating_envelope.json"
)


def load_golden_reply_envelope() -> dict:
    """Load the shared reply contract fixture.

    Deliberately raises rather than skipping when the file is missing. A
    `pytest.skip` here would recreate precisely the silent-gap failure this
    file exists to close: a green suite that proves nothing.
    """
    if not REPLY_FIXTURE_PATH.exists():
        raise AssertionError(
            f"Golden Intercom reply envelope fixture missing at {REPLY_FIXTURE_PATH}. "
            "It is a shared contract also read by "
            "services/backend-api/tests/test_intercom.py -- restore it rather "
            "than skipping this test."
        )
    return json.loads(REPLY_FIXTURE_PATH.read_text())


def load_golden_rating_envelope() -> dict:
    """Load the shared rating contract fixture.

    Deliberately raises rather than skipping when the file is missing. A
    `pytest.skip` here would recreate precisely the silent-gap failure this
    file exists to close: a green suite that proves nothing.
    """
    if not RATING_FIXTURE_PATH.exists():
        raise AssertionError(
            f"Golden Intercom rating envelope fixture missing at {RATING_FIXTURE_PATH}. "
            "It is a shared contract also read by "
            "services/backend-api/tests/test_intercom.py -- restore it rather "
            "than skipping this test."
        )
    return json.loads(RATING_FIXTURE_PATH.read_text())


def _with_conv_id(envelope: dict, conv_id: str) -> dict:
    """Deep-copy the envelope and force the conversation id.

    Used so the sequence/out-of-order tests can pin one conversation id
    regardless of the fixtures' own ids (`conv_golden_100/200/300`).
    """
    envelope = copy.deepcopy(envelope)
    envelope["data"]["item"]["id"] = conv_id
    return envelope


@pytest.fixture
def golden_envelope() -> dict:
    return load_golden_envelope()


@pytest.fixture
def adapter() -> IntercomAdapter:
    return IntercomAdapter()


# ---------------------------------------------------------------------------
# Harness (mirrors tests/test_zendesk_adapter.py's helpers)
# ---------------------------------------------------------------------------


def _make_org(db, name="Acme Co") -> Organization:
    org = Organization(name=name, plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_intercom_integration(db, org_id, workspace_id="abc123") -> Integration:
    """The OAuth-shaped Integration row the intercom tenancy branch matches on.

    `_find_matching_sources` keys Intercom off `Integration.config["workspace_id"]`
    (source_events.py), so a source is only reachable when this row exists and
    its workspace_id equals the payload's `app_id`.
    """
    integration = Integration(
        organization_id=org_id,
        type="intercom",
        is_active=True,
        config={"workspace_id": workspace_id},
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return integration


def _make_intercom_source(
    db, org_id, integration_id, triggers=None, auto_import=True
) -> FeedbackSource:
    source = FeedbackSource(
        organization_id=org_id,
        integration_id=integration_id,
        source_type="intercom",
        is_active=True,
        auto_import=auto_import,
        triggers=triggers if triggers is not None else {"new_conversations": True},
        field_mapping={},
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def _patch_db_session(monkeypatch, db):
    import src.tasks.source_events as task_mod

    @contextmanager
    def fake_get_db():
        yield db

    monkeypatch.setattr(task_mod, "get_db_session", fake_get_db)


@pytest.fixture
def _no_op_side_effects(monkeypatch):
    """Neutralize the Celery/Redis side effects of the auto_import path."""
    import src.cache as cache_mod
    import src.tasks.analysis as analysis_mod

    monkeypatch.setattr(analysis_mod.analyze_single_feedback, "delay", MagicMock())
    monkeypatch.setattr(analysis_mod, "reanalyze_feedback", MagicMock())
    monkeypatch.setattr(cache_mod, "cache_invalidate", MagicMock())


# ---------------------------------------------------------------------------
# Adapter-side contract (these already hold -- they pin the correct side)
# ---------------------------------------------------------------------------


class TestAdapterAcceptsGoldenEnvelope:
    def test_extracts_body_text(self, adapter, golden_envelope):
        content = adapter.extract_content(golden_envelope, {})
        assert content["text"] == (
            "The billing page times out when I try to download an invoice."
        )

    def test_extracts_author_metadata(self, adapter, golden_envelope):
        content = adapter.extract_content(golden_envelope, {})
        assert content["metadata"]["conversation_id"] == "conv_golden_100"
        assert content["metadata"]["author_email"] == "dana@example.com"

    def test_yields_nonempty_dedup_id(self, adapter, golden_envelope):
        external_id, message_id = adapter.get_external_ids(golden_envelope)
        assert external_id == "conv_golden_100"
        assert message_id == "conv_golden_100"

    def test_keyword_trigger_matches_body(self, adapter, golden_envelope):
        matched = adapter.check_triggers(
            golden_envelope["topic"], golden_envelope, {"keywords": ["billing"]}
        )
        assert matched == "keyword:billing"

    def test_stripped_envelope_yields_nothing(self, adapter, golden_envelope):
        """Pins the defect itself, so it cannot silently return.

        This is what the route used to queue. If someone reintroduces the
        strip, the seam tests below fail -- and this test documents exactly
        why they fail.
        """
        content = adapter.extract_content(golden_envelope["data"], {})
        assert content["text"] == ""
        assert adapter.get_external_ids(golden_envelope["data"]) == ("", "")


# ---------------------------------------------------------------------------
# The seam: what the route actually queues, driven through the shared core
# ---------------------------------------------------------------------------


class TestQueuedPayloadProducesFeedback:
    def test_full_envelope_creates_feedback_item(
        self, db, monkeypatch, _no_op_side_effects, golden_envelope
    ):
        """THE regression test for the defect.

        Before the fix the route passed `envelope["data"]` here and this
        returned {"status": "empty_text"} with no FeedbackItem, on every
        delivery, in every release.
        """
        from src.models import FeedbackItem
        from src.tasks.source_events import process_source_event

        org = _make_org(db)
        integration = _make_intercom_integration(db, org.id, workspace_id="abc123")
        _make_intercom_source(db, org.id, integration.id)
        _patch_db_session(monkeypatch, db)

        process_source_event(
            source_type="intercom",
            external_event_id=golden_envelope["data"]["item"]["id"],
            event_type=golden_envelope["topic"],
            event_data=golden_envelope,
            provider_context={
                "conversation_id": golden_envelope["data"]["item"]["id"],
                "workspace_id": golden_envelope["app_id"],
            },
        )

        items = db.query(FeedbackItem).all()
        assert len(items) == 1, (
            "Expected exactly one FeedbackItem from a conversation.user.created "
            "delivery. Zero means the envelope was stripped before the adapter "
            "saw it -- the defect this aspect fixes."
        )
        item = items[0]
        assert item.source == "intercom"
        assert item.source_external_id == "conv_golden_100"
        assert item.text == (
            "The billing page times out when I try to download an invoice."
        )
        assert item.source_metadata["author_email"] == "dana@example.com"

    def test_redelivery_is_deduplicated(
        self, db, monkeypatch, _no_op_side_effects, golden_envelope
    ):
        """A non-empty dedup id is what makes 'one item per conversation' hold.

        Under the stripped shape get_external_ids returned ("", ""), so this
        guarantee was unreachable.
        """
        from src.models import FeedbackItem
        from src.tasks.source_events import process_source_event

        org = _make_org(db)
        integration = _make_intercom_integration(db, org.id, workspace_id="abc123")
        _make_intercom_source(db, org.id, integration.id)
        _patch_db_session(monkeypatch, db)

        kwargs = dict(
            source_type="intercom",
            event_type=golden_envelope["topic"],
            event_data=golden_envelope,
            provider_context={
                "conversation_id": golden_envelope["data"]["item"]["id"],
                "workspace_id": golden_envelope["app_id"],
            },
        )
        process_source_event(external_event_id="notif_1", **kwargs)
        process_source_event(external_event_id="notif_2", **kwargs)

        assert db.query(FeedbackItem).count() == 1

    def test_missing_workspace_id_matches_nothing(
        self, db, monkeypatch, _no_op_side_effects, golden_envelope
    ):
        """The P0 tenancy guard, re-asserted from this seam.

        A payload without app_id must never fan out to every org's Intercom
        source. Pinned here because this aspect changes what flows through
        that path, and a later aspect widens the discriminator itself.
        """
        from src.models import FeedbackItem
        from src.tasks.source_events import process_source_event

        org = _make_org(db)
        integration = _make_intercom_integration(db, org.id, workspace_id="abc123")
        _make_intercom_source(db, org.id, integration.id)
        _patch_db_session(monkeypatch, db)

        result = process_source_event(
            source_type="intercom",
            external_event_id="notif_1",
            event_type=golden_envelope["topic"],
            event_data=golden_envelope,
            provider_context={"conversation_id": "conv_golden_100", "workspace_id": None},
        )

        assert result["status"] == "no_sources"
        assert db.query(FeedbackItem).count() == 0


# ---------------------------------------------------------------------------
# Reply/rating feed-enrichment seam (the webhook-enrich-module's inputs)
# ---------------------------------------------------------------------------


class TestReplyRatingEnvelopesFeedEnrichmentSeam:
    """Pins the exact key path and parsed shape the enrichment module consumes.

    The webhook-enrich-module aspect builds `src/services/intercom_webhook_enrich.py`
    against this contract: conversation id from `event_data["data"]["item"]["id"]`,
    replies from `extract_reply_parts` (conversation_parts.conversation_parts[]),
    rating from `extract_rating` (conversation_rating). The fixtures are
    conversation-wrapped exactly like the pull path's real API shape, so the same
    seams that parse the pull parse these envelopes unchanged.

    See docs/planning/intercom-webhook-reply-rating/webhook-enrich-module/spec.md.
    """

    def test_reply_envelope_yields_conversation_id_and_reply_part(self):
        envelope = load_golden_reply_envelope()
        item = envelope["data"]["item"]
        assert item["id"] == "conv_golden_200"

        parts = extract_reply_parts(item)
        assert len(parts) == 1
        assert parts[0]["part_id"] == "part_golden_210"
        assert parts[0]["author"]["email"] == "sam@example.com"
        assert parts[0]["body"] == (
            "Still broken after the latest update. The download button does nothing."
        )
        assert parts[0]["created_at"] == "1785400100"

        assert extract_rating(item) is None

    def test_rating_envelope_yields_rating_and_no_parts(self):
        envelope = load_golden_rating_envelope()
        item = envelope["data"]["item"]
        assert item["id"] == "conv_golden_300"

        assert extract_reply_parts(item) == []
        assert extract_rating(item) == {
            "rating": 5,
            "remark": "Quick fix, great support!",
            "rated_at": "1785400200",
        }


# ---------------------------------------------------------------------------
# Webhook enrichment branch (core-branch-dispatch, PRD R1/R3/R4)
# ---------------------------------------------------------------------------


class TestWebhookEnrichmentBranch:
    """Phase 1 — intercom replied/rating events bypass trigger + dedup and
    route straight into the webhook enrichment module: log `enriched`
    (or `ignored`/`failed`), never create items, never block a later
    `created` delivery.
    """

    def _setup(self, db, monkeypatch):
        org = _make_org(db)
        integration = _make_intercom_integration(db, org.id, workspace_id="abc123")
        _make_intercom_source(db, org.id, integration.id)
        _patch_db_session(monkeypatch, db)
        return org

    def _deliver(self, envelope, external_event_id=None):
        from src.tasks.source_events import process_source_event

        return process_source_event(
            source_type="intercom",
            external_event_id=external_event_id or envelope["id"],
            event_type=envelope["topic"],
            event_data=envelope,
            provider_context={
                "conversation_id": envelope["data"]["item"]["id"],
                "workspace_id": envelope["app_id"],
            },
        )

    def test_created_replied_rating_enrich_one_item(
        self, db, monkeypatch, _no_op_side_effects
    ):
        from src.models import FeedbackItem, FeedbackSourceEvent

        self._setup(db, monkeypatch)

        conv_id = "conv_seq_100"
        created = _with_conv_id(load_golden_envelope(), conv_id)
        replied = _with_conv_id(load_golden_reply_envelope(), conv_id)
        rating = _with_conv_id(load_golden_rating_envelope(), conv_id)

        self._deliver(created)
        self._deliver(replied)
        self._deliver(rating)

        items = db.query(FeedbackItem).all()
        assert len(items) == 1, (
            "expected exactly one FeedbackItem: created delivers, replied/rating "
            "must enrich it in place, never create a second"
        )
        item = items[0]
        assert item.source_external_id == conv_id
        assert (
            "\n\n--- Reply by Sam Rivers (1785400100) ---\n"
            "Still broken after the latest update. The download button does nothing."
        ) in item.text
        assert item.source_metadata["replies"][0]["part_id"] == "part_golden_210"
        assert item.source_metadata["rating"] == 5

        rows = db.query(FeedbackSourceEvent).all()
        assert [r.status for r in rows] == ["processed", "enriched", "enriched"]
        assert all(r.external_message_id == conv_id for r in rows)
        assert all(r.feedback_id == item.id for r in rows)
        # Phase 1 pin: terminal enrichment outcomes carry processed_at.
        assert all(r.processed_at is not None for r in rows)

    def test_reply_before_created_is_ignored_then_created_works(
        self, db, monkeypatch, _no_op_side_effects
    ):
        from src.models import FeedbackItem, FeedbackSourceEvent

        self._setup(db, monkeypatch)

        conv_id = "conv_seq_200"
        replied = _with_conv_id(load_golden_reply_envelope(), conv_id)

        self._deliver(replied)
        assert db.query(FeedbackItem).count() == 0
        rows = db.query(FeedbackSourceEvent).all()
        assert len(rows) == 1
        assert rows[0].status == "ignored"
        assert rows[0].external_message_id == conv_id

        created = _with_conv_id(load_golden_envelope(), conv_id)
        self._deliver(created)
        items = db.query(FeedbackItem).all()
        assert len(items) == 1, (
            "the ignored reply row must NOT dedup the later created delivery "
            "(ignored is outside the dedup filter's processed/pending set)"
        )
        assert items[0].source_external_id == conv_id

    def test_auth_error_logs_failed_without_retry(
        self, db, monkeypatch, _no_op_side_effects
    ):
        import src.services.intercom_webhook_enrich as enrich_mod
        from src.models import FeedbackItem, FeedbackSourceEvent

        self._setup(db, monkeypatch)
        monkeypatch.setattr(
            enrich_mod,
            "enrich_webhook_item",
            MagicMock(
                return_value={
                    "status": "error/auth_error",
                    "changed": False,
                    "feedback_id": None,
                }
            ),
        )

        conv_id = "conv_seq_300"
        replied = _with_conv_id(load_golden_reply_envelope(), conv_id)
        result = self._deliver(replied)

        assert result["status"] == "error/auth_error"
        assert db.query(FeedbackItem).count() == 0
        rows = db.query(FeedbackSourceEvent).all()
        assert len(rows) == 1
        assert rows[0].status == "failed"
        assert rows[0].error_message == "error/auth_error"
        assert rows[0].external_message_id == conv_id
        assert rows[0].processed_at is not None

