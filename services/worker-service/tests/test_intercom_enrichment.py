"""Tests for the pull-enrichment merge helper (pull-enrichment aspect).

Phase 1 seam tests for `_enrich_conversation_replies(db, item, reply_parts,
rating)` in src/tasks/intercom_sync.py — the task glue that merges NEW reply
parts into an existing FeedbackItem's text, records replies + rating in
source_metadata, and reports whether the text actually changed.

Pinned semantics (plan pull-enrichment §1.1, §1.5, §1.6):

  * diff is by part_id membership against source_metadata["replies"];
  * merge block format is the adapter contract, verbatim:
    "\\n\\n--- Reply by {author_name} ({created_at}) ---\\n{body}";
  * True iff item.text changed; rating-only updates return False (metadata
    changed, no re-analysis);
  * rating/remark/rated_at are metadata-only, never in text;
  * customer_email is never written by the helper.

The helper's `db` parameter is part of the pinned signature — the caller owns
the transaction; the helper only mutates the item.
"""
from __future__ import annotations

from src.models import FeedbackItem
from src.tasks.intercom_sync import _enrich_conversation_replies

USER_AUTHOR = {"type": "user", "id": "user_1", "name": "Dana Okafor", "email": "dana@acme.com"}
ADMIN_AUTHOR = {"type": "admin", "id": "admin_1", "name": "Agent Ada"}
BOT_AUTHOR = {"type": "bot", "id": "bot_1", "name": "Intercom Bot"}


def _reply(part_id, body, author=USER_AUTHOR, created_at="2026-08-01T10:00:00Z"):
    return {"part_id": part_id, "author": author, "body": body, "created_at": created_at}


def _make_item(db, text="First message", metadata=None, customer_email="dana@acme.com"):
    item = FeedbackItem(
        organization_id=1,
        text=text,
        source="intercom",
        source_external_id="conv_1",
        source_metadata=metadata,
        customer_email=customer_email,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


class TestEnrichConversationReplies:
    def test_happy_path_merges_new_reply_and_returns_true(self, db):
        item = _make_item(db, text="First message", metadata=None)

        changed = _enrich_conversation_replies(
            db, item, [_reply("p1", "I fixed it")], None
        )

        assert changed is True
        assert item.text == (
            "First message"
            "\n\n--- Reply by Dana Okafor (2026-08-01T10:00:00Z) ---\nI fixed it"
        )
        assert [r["part_id"] for r in item.source_metadata["replies"]] == ["p1"]
        assert item.source_metadata["replies"][0] == _reply("p1", "I fixed it")

    def test_multiple_replies_appended_in_order(self, db):
        item = _make_item(db, text="First message")

        changed = _enrich_conversation_replies(
            db,
            item,
            [
                _reply("p1", "First reply"),
                _reply("p2", "Second reply"),
            ],
            None,
        )

        assert changed is True
        assert item.text == (
            "First message"
            "\n\n--- Reply by Dana Okafor (2026-08-01T10:00:00Z) ---\nFirst reply"
            "\n\n--- Reply by Dana Okafor (2026-08-01T10:00:00Z) ---\nSecond reply"
        )
        assert item.text.index("First reply") < item.text.index("Second reply")

    def test_idempotent_remerge_is_a_noop(self, db):
        item = _make_item(db, text="First message")
        parts = [_reply("p1", "I fixed it"), _reply("p2", "All good now")]

        assert _enrich_conversation_replies(db, item, parts, None) is True
        text_after_first = item.text
        metadata_after_first = dict(item.source_metadata)

        assert _enrich_conversation_replies(db, item, parts, None) is False
        assert item.text == text_after_first
        assert item.source_metadata == metadata_after_first

    def test_mixed_known_and_new_merges_only_new(self, db):
        item = _make_item(db, text="First message")
        first = _reply("p1", "Already merged")
        second = _reply("p2", "Brand new")

        _enrich_conversation_replies(db, item, [first], None)

        changed = _enrich_conversation_replies(db, item, [first, second], None)

        assert changed is True
        assert item.text == (
            "First message"
            "\n\n--- Reply by Dana Okafor (2026-08-01T10:00:00Z) ---\nAlready merged"
            "\n\n--- Reply by Dana Okafor (2026-08-01T10:00:00Z) ---\nBrand new"
        )
        assert item.text.count("Already merged") == 1
        assert [r["part_id"] for r in item.source_metadata["replies"]] == ["p1", "p2"]

    def test_rating_stored_in_metadata_never_in_text(self, db):
        item = _make_item(db, text="First message")
        rating = {"rating": 5, "remark": "Great support!", "rated_at": "1785400000"}

        changed = _enrich_conversation_replies(db, item, [], rating)

        assert changed is False
        assert item.source_metadata["rating"] == 5
        assert item.source_metadata["remark"] == "Great support!"
        assert item.source_metadata["rated_at"] == "1785400000"
        assert item.text == "First message"
        assert "5" not in item.text and "Great support" not in item.text

    def test_rating_only_returns_false_even_with_prior_replies(self, db):
        item = _make_item(db, text="First message")
        parts = [_reply("p1", "I fixed it")]

        _enrich_conversation_replies(db, item, parts, None)

        changed = _enrich_conversation_replies(
            db, item, parts, {"rating": 4}
        )

        assert changed is False
        assert item.source_metadata["rating"] == 4
        assert item.text == (
            "First message"
            "\n\n--- Reply by Dana Okafor (2026-08-01T10:00:00Z) ---\nI fixed it"
        )

    def test_rating_absent_leaves_existing_rating_untouched(self, db):
        item = _make_item(
            db, metadata={"replies": [], "rating": 5, "remark": "old remark"}
        )

        changed = _enrich_conversation_replies(db, item, [], None)

        assert changed is False
        assert item.source_metadata["rating"] == 5
        assert item.source_metadata["remark"] == "old remark"

    def test_source_metadata_none_starts_fresh(self, db):
        item = _make_item(db, text="First message", metadata=None)

        changed = _enrich_conversation_replies(
            db, item, [_reply("p1", "I fixed it")], {"rating": 3}
        )

        assert changed is True
        assert item.source_metadata["replies"][0]["part_id"] == "p1"
        assert item.source_metadata["rating"] == 3

    def test_admin_author_merged_but_customer_email_never_written(self, db):
        item = _make_item(db, text="First message", customer_email="dana@acme.com")
        before = item.customer_email

        changed = _enrich_conversation_replies(
            db, item, [_reply("p1", "Teammate reply", author=ADMIN_AUTHOR)], None
        )

        assert changed is True
        assert "Teammate reply" in item.text
        assert item.customer_email == before

    def test_bot_author_merged_but_customer_email_never_written(self, db):
        item = _make_item(db, text="First message", customer_email="dana@acme.com")
        before = item.customer_email

        changed = _enrich_conversation_replies(
            db, item, [_reply("p1", "Automated reply", author=BOT_AUTHOR)], None
        )

        assert changed is True
        assert "Automated reply" in item.text
        assert item.customer_email == before

    def test_empty_reply_parts_is_a_noop(self, db):
        item = _make_item(db, text="First message", metadata={"replies": []})
        text_before = item.text
        metadata_before = dict(item.source_metadata)

        changed = _enrich_conversation_replies(db, item, [], None)

        assert changed is False
        assert item.text == text_before
        assert item.source_metadata == metadata_before

    def test_duplicate_part_id_within_one_payload_merged_once(self, db):
        item = _make_item(db, text="First message")
        dup = _reply("p1", "I fixed it")

        changed = _enrich_conversation_replies(db, item, [dup, dup], None)

        assert changed is True
        assert item.text.count("I fixed it") == 1
        assert [r["part_id"] for r in item.source_metadata["replies"]] == ["p1"]
