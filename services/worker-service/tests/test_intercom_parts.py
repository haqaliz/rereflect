"""Tests for the conversation-object reply/rating extraction (adapter-reply-rating-extraction).

The webhook adapter (adapters/intercom.py) parses event-shaped payloads; the
pull path works from the full conversation object the client returns
(conversation_parts + conversation_rating). This file pins the pure extraction
functions in src/adapters/intercom_parts.py:

  * extract_reply_parts  -- reply-family parts only ({part_id, author, body,
    created_at}), HTML-stripped bodies, author object retained, first message
    never included;
  * extract_rating       -- {rating, remark?, rated_at?}, None when absent;
  * format_reply_merge   -- the exact pinned merge string;
  * new_reply_parts      -- idempotent diff by part_id membership.

The _contact_email rule is exercised through the new path (parts shape, not the
webhook item shape): user/contact/lead -> email, admin/bot -> None.

See docs/planning/intercom-pull-replies-and-ratings/adapter-reply-rating-extraction/.
"""
from __future__ import annotations

from src.adapters.intercom import _contact_email
from src.adapters.intercom_parts import (
    extract_rating,
    extract_reply_parts,
    format_reply_merge,
    new_reply_parts,
)

USER_AUTHOR = {"type": "user", "id": "user_1", "name": "Dana Okafor", "email": "dana@acme.com"}
CONTACT_AUTHOR = {"type": "contact", "id": "cont_1", "name": "Sam Rivers", "email": "sam@acme.com"}
LEAD_AUTHOR = {"type": "lead", "id": "lead_1", "name": "Noah West", "email": "noah@acme.com"}
ADMIN_AUTHOR = {"type": "admin", "id": "admin_1", "name": "Agent Ada"}
BOT_AUTHOR = {"type": "bot", "id": "bot_1", "name": "Intercom Bot"}


def _author(type_, name, email):
    author = {"type": type_, "id": f"{type_}_1", "name": name}
    if email is not None:
        author["email"] = email
    return author


def _part(part_id, part_type="comment", body="<p>hi</p>", author=USER_AUTHOR, created_at=1785400000):
    part = {
        "type": "conversation_part",
        "id": part_id,
        "part_type": part_type,
        "body": body,
        "author": author,
        "created_at": created_at,
    }
    if part_id is None:
        del part["id"]
    return part


def _conversation(parts, rating=None, **extra):
    return {
        "type": "conversation",
        "id": "conv_1",
        "conversation_message": {
            "type": "conversation",
            "id": "msg_1",
            "body": "<p>Billing is broken</p>",
            "author": USER_AUTHOR,
            "created_at": 1785390000,
        },
        "conversation_parts": {"conversation_parts": parts},
        "conversation_rating": rating,
        **extra,
    }


class TestExtractReplyParts:
    def test_returns_comment_parts_only_in_original_order(self):
        conv = _conversation(
            [
                _part("p1", body="<p>First reply</p>", author=USER_AUTHOR),
                _part("p2", part_type="note", body="<p>Internal note</p>", author=ADMIN_AUTHOR),
                _part("p3", body="<p>Customer follow-up</p>", author=CONTACT_AUTHOR),
                _part("p4", part_type="assignment", author=ADMIN_AUTHOR),
                _part("p5", body="<p>Agent reply</p>", author=ADMIN_AUTHOR),
            ]
        )
        parts = extract_reply_parts(conv)
        assert [p["part_id"] for p in parts] == ["p1", "p3", "p5"]
        for p in parts:
            assert {"part_id", "author", "body", "created_at"} <= set(p)

    def test_first_message_never_included(self):
        conv = _conversation(
            [_part("p1", body="<p>First reply</p>", author=CONTACT_AUTHOR)]
        )
        parts = extract_reply_parts(conv)
        assert all("Billing is broken" not in p["body"] for p in parts)
        assert [p["part_id"] for p in parts] == ["p1"]

    def test_strips_html_from_bodies(self):
        conv = _conversation(
            [_part("p1", body="<p>Hello <b>world</b></p><br/><p>Second line</p>")]
        )
        parts = extract_reply_parts(conv)
        # the shared strip_html primitive removes tags without inserting
        # separators, so <br/> does not become a space here
        assert parts[0]["body"] == "Hello worldSecond line"

    def test_missing_body_and_author_graceful(self):
        part = _part("p1")
        del part["body"]
        part["author"] = None
        conv = _conversation([part])
        parts = extract_reply_parts(conv)
        assert parts[0]["body"] == ""
        assert parts[0]["author"] == {}

    def test_skips_parts_without_id(self):
        conv = _conversation(
            [
                _part(None, body="<p>No id</p>"),
                _part("p2", body="<p>Has id</p>"),
            ]
        )
        parts = extract_reply_parts(conv)
        assert [p["part_id"] for p in parts] == ["p2"]

    def test_empty_or_missing_conversation_parts_returns_empty_list(self):
        assert extract_reply_parts({}) == []
        assert extract_reply_parts({"conversation_parts": {"conversation_parts": []}}) == []
        assert extract_reply_parts({"conversation_parts": "not-a-list"}) == []

    def test_bare_list_wrapper_parsed(self):
        wrapped = _conversation([_part("p1"), _part("p2")])
        bare = dict(wrapped)
        bare["conversation_parts"] = wrapped["conversation_parts"]["conversation_parts"]
        assert extract_reply_parts(bare) == extract_reply_parts(wrapped)


class TestExtractRating:
    def test_rating_with_remark_and_rated_at(self):
        conv = _conversation(
            [],
            rating={"type": "conversation_rating", "rating": 5, "remark": "Great support!", "created_at": 1785400000},
        )
        assert extract_rating(conv) == {"rating": 5, "remark": "Great support!", "rated_at": "1785400000"}

    def test_rating_omits_missing_remark_and_rated_at(self):
        conv = _conversation([], rating={"type": "conversation_rating", "rating": 3})
        assert extract_rating(conv) == {"rating": 3}

    def test_rating_none_when_absent(self):
        conv = _conversation([], rating=None)
        assert extract_rating(conv) is None

    def test_rating_none_when_rating_value_missing(self):
        conv = _conversation([], rating={"type": "conversation_rating", "remark": "x"})
        assert extract_rating(conv) is None


class TestContactEmailThroughParts:
    def test_contact_email_for_user_contact_lead(self):
        for author in (USER_AUTHOR, CONTACT_AUTHOR, LEAD_AUTHOR):
            conv = _conversation([_part("p1", author=author)])
            extracted_author = extract_reply_parts(conv)[0]["author"]
            assert _contact_email(extracted_author) == author["email"]

    def test_contact_email_none_for_admin_and_bot(self):
        for author in (ADMIN_AUTHOR, BOT_AUTHOR):
            conv = _conversation([_part("p1", body="<p>Teammate reply</p>", author=author)])
            parts = extract_reply_parts(conv)
            assert parts[0]["body"] == "Teammate reply"
            assert _contact_email(parts[0]["author"]) is None

    def test_contact_email_none_for_missing_author(self):
        part = _part("p1")
        part["author"] = None
        conv = _conversation([part])
        assert _contact_email(extract_reply_parts(conv)[0]["author"]) is None


class TestFormatReplyMerge:
    def test_format_reply_merge_exact_string(self):
        reply = {
            "part_id": "p1",
            "author": {"type": "user", "name": "Dana Okafor"},
            "body": "Billing is broken",
            "created_at": "1785400000",
        }
        assert format_reply_merge(reply) == "\n\n--- Reply by Dana Okafor (1785400000) ---\nBilling is broken"

    def test_format_reply_merge_unknown_author(self):
        reply = {
            "part_id": "p1",
            "author": {"type": "bot"},
            "body": "Billing is broken",
            "created_at": "1785400000",
        }
        assert format_reply_merge(reply) == "\n\n--- Reply by unknown (1785400000) ---\nBilling is broken"


class TestNewReplyParts:
    @staticmethod
    def _extracted(*parts):
        return extract_reply_parts(_conversation(list(parts)))

    def test_new_reply_parts_returns_only_unmerged(self):
        parts = self._extracted(_part("p1"), _part("p2"), _part("p3"))
        assert [p["part_id"] for p in new_reply_parts(parts, ["p1"])] == ["p2", "p3"]

    def test_new_reply_parts_all_merged_is_noop(self):
        parts = self._extracted(_part("p1"), _part("p2"))
        assert new_reply_parts(parts, ["p1", "p2", "p3"]) == []

    def test_new_reply_parts_empty_merged_returns_all(self):
        parts = self._extracted(_part("p1"), _part("p2"))
        assert new_reply_parts(parts, None) == parts
        assert new_reply_parts(parts, []) == parts


class TestMergeIdempotency:
    def test_remerge_roundtrip_is_noop(self):
        parts = extract_reply_parts(
            _conversation(
                [
                    _part("p1", body="<p>First reply</p>", author=USER_AUTHOR),
                    _part("p2", body="<p>Second reply</p>", author=CONTACT_AUTHOR),
                ]
            )
        )
        merged = []
        text = ""
        for p in new_reply_parts(parts, merged):
            text += format_reply_merge(p)
            merged.append(p["part_id"])

        appended = new_reply_parts(parts, merged)
        text_after_second_pass = text + "".join(format_reply_merge(p) for p in appended)
        assert appended == []
        assert text_after_second_pass == text
