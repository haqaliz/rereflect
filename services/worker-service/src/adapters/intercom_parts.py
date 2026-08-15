"""Reply/rating extraction from Intercom *conversation* objects (pull path).

The webhook adapter (adapters/intercom.py) parses event-shaped payloads;
this module parses the conversation object the pull client returns
(conversation_parts + conversation_rating). It reuses strip_html and
_contact_email from adapters/intercom.py — importing the underscore names
is deliberate: they are the shared parsing primitives, and intercom.py is
deliberately untouched so webhook behavior never moves.

The merge format is pinned by tests in test_intercom_parts.py:
  "\n\n--- Reply by {author_name} ({created_at}) ---\n{body}"
Idempotency is by part_id membership (see new_reply_parts).

Stored shape (written to FeedbackItem.source_metadata by pull-enrichment):

  source_metadata["replies"] = extract_reply_parts output verbatim — an
  array of {"part_id", "author", "body", "created_at"} objects; merge
  membership is read from "part_id".
  source_metadata["rating"] / ["remark"] / ["rated_at"] = extract_rating
  output — keys omitted when absent, so "rating" is present iff a rating
  was found.
"""

from typing import Any, Dict, List, Optional

from .intercom import _contact_email, strip_html

# Reply-family part types. Intercom conversation parts carry part_type
# "comment" for replies; notes, assignments, opens/closes, tags and the
# rating part are system events and are excluded here (rating comes from
# conversation_rating, never from a part).
REPLY_PART_TYPES = {"comment"}


def _parts_of(conversation: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The conversation's parts array, tolerant of the wrapper shape.

    The detail GET returns the wrapped object
    {"conversation_parts": [...]} (the parse proven at intercom.py:221);
    some search display shapes return a bare array. Anything else —
    missing key, wrong type — yields [].
    """
    parts = conversation.get("conversation_parts", [])
    if isinstance(parts, dict):
        parts = parts.get("conversation_parts", [])
    return parts if isinstance(parts, list) else []


def extract_reply_parts(conversation: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Reply-family parts of a conversation, in original order.

    Each result is {"part_id", "author", "body", "created_at"}:
    part_id is the part's "id" (the idempotency key; a part without one
    is skipped — it could never be deduped, and the caller logs if it
    cares), body is HTML-stripped, author is the raw author object
    retained for attribution decisions, created_at is passed through via
    str() (Unix seconds in practice; "" when missing).

    The top-level conversation_message (the first message) lives outside
    conversation_parts and is therefore never included.
    """
    results = []
    for part in _parts_of(conversation):
        if part.get("type") != "conversation_part":
            continue
        if part.get("part_type") not in REPLY_PART_TYPES:
            continue
        part_id = part.get("id")
        if not part_id:
            continue
        results.append(
            {
                "part_id": part_id,
                "author": part.get("author") or {},
                "body": strip_html(part.get("body") or ""),
                "created_at": (
                    str(part.get("created_at"))
                    if part.get("created_at") is not None
                    else ""
                ),
            }
        )
    return results


def extract_rating(conversation: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The conversation's rating, or None when there is none.

    Returns {"rating": int} plus "remark" (when non-empty) and "rated_at"
    (when the rating carries a created_at timestamp, passed through via
    str()). Absent keys are omitted — never None/"" stored in metadata.
    """
    rating_obj = conversation.get("conversation_rating")
    if not isinstance(rating_obj, dict) or rating_obj.get("rating") is None:
        return None
    result = {"rating": rating_obj["rating"]}
    if rating_obj.get("remark"):
        result["remark"] = rating_obj["remark"]
    if rating_obj.get("created_at") is not None:
        result["rated_at"] = str(rating_obj["created_at"])
    return result


def format_reply_merge(reply: Dict[str, Any]) -> str:
    """The pinned merge string for one extracted reply part.

    Exactly "\n\n--- Reply by {author_name} ({created_at}) ---\n{body}".
    author_name falls back to "unknown" so a nameless author never
    renders a double-space attribution line.
    """
    author_name = (reply.get("author") or {}).get("name") or "unknown"
    return (
        f"\n\n--- Reply by {author_name} ({reply.get('created_at', '')}) ---\n"
        f"{reply.get('body', '')}"
    )


def new_reply_parts(
    parts: List[Dict[str, Any]], merged_part_ids: Optional[List[str]]
) -> List[Dict[str, Any]]:
    """Parts whose part_id is not yet merged — the idempotent diff.

    Pure: the caller computes the merged id set from
    source_metadata["replies"] and passes it here, so re-merging the same
    conversation is a no-op by construction. Order is preserved.
    """
    merged = set(merged_part_ids or [])
    return [p for p in parts if p["part_id"] not in merged]
