"""
Deterministic action proposer for the AI Copilot (M2.2).

Pure, synchronous proposal logic: inspects a SQL result's columns to decide
which registry actions apply and builds the `actions` structured_data item
with a frozen customer cohort. No LLM is ever consulted here -- proposal is
result-shape inspection only.

See docs/planning/copilot-suggested-actions/deterministic-proposer/plan_20260909.md
and the action-contract spec for the emitted envelope.
"""

import hashlib
from typing import Any, Dict, List

# A result larger than this offers no action rather than a silently truncated
# cohort. Deliberately under MAX_TABLE_ROWS (1000) in response_formatter.py:
# the cap is its own, lower constant.
ACTION_EMAIL_CAP = 200

_EMAIL_COLUMN_NAMES = ("customer_email", "email")


def extract_customer_emails(columns: List[str], rows: List[List[Any]]) -> List[str]:
    """Return the non-empty email values of the result's customer-email column.

    The column is identified by name: the first column whose lowercased name
    is ``customer_email`` or ``email``. Values are collected in row order,
    non-empty strings only, deduped while preserving first-seen order.
    """
    column_index = next(
        (
            i
            for i, name in enumerate(columns)
            if str(name).lower() in _EMAIL_COLUMN_NAMES
        ),
        None,
    )
    if column_index is None:
        return []

    emails: List[str] = []
    for row in rows:
        value = row[column_index]
        if isinstance(value, str) and value:
            if value not in emails:
                emails.append(value)
    return emails


def propose_actions(message_id: str, customer_emails: List[str]) -> Dict[str, Any]:
    """Build the ``actions`` structured_data item for a frozen cohort.

    The ``proposal_id`` is deterministic for a given message + cohort so the
    execute route's one-shot guard keys stably on it. The item carries only
    server-derived org data (the emails); ``requires_input`` names the params
    the user must supply at click-time.
    """
    emails = list(dict.fromkeys(customer_emails))
    n = len(emails)
    cohort_hash = hashlib.sha1("|".join(emails).encode()).hexdigest()[:6]
    proposal_id = f"{message_id}:tag_customers:{cohort_hash}"

    return {
        "data_type": "actions",
        "data": {
            "proposal_id": proposal_id,
            "actions": [
                {
                    "action": "tag_customers",
                    "label": f"Tag these {n} customers…",
                    "params": {"emails": emails},
                    "requires_input": ["tag"],
                }
            ],
        },
    }
