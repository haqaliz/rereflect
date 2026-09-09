"""
Shared customer tag application — extracted from the `bulk/tags` handler
(`src/api/routes/customers.py`) so the copilot action registry can reuse the
exact same set-union/difference semantics without an internal HTTP request.

The route owns the single `db.commit()` (all-or-nothing per request); this
service only mutates `record.tags` on the in-memory ORM rows it is given and
returns the summary counts. Tag validation (trim/dedupe/50-char) stays in the
`BulkTagRequest` schema — the service starts from already-cleaned tags.

Note: `services/worker-service/src/services/playbook_engine.py` mirrors the
50/20 constants with its own copies — it cannot import this backend service.
That drift risk is documented in the repo CLAUDE.md and is intentionally not
fixed here.
"""
from typing import List, Literal, Tuple

from src.models.customer_health import CustomerHealth

TAG_MAX_LENGTH = 50
TAG_CAP_PER_CUSTOMER = 20


def apply_tags(
    rows: List[CustomerHealth],
    tags: List[str],
    mode: Literal["add", "remove"],
) -> Tuple[int, List[str]]:
    """Apply `tags` to each row by set union (`add`) or difference (`remove`).

    Verbatim port of the `bulk/tags` handler loop (`customers.py`). For every
    row: if the resulting tag set would exceed `TAG_CAP_PER_CUSTOMER`, the row
    is left unchanged and reported in `errors` (never silently truncated,
    never counted toward `updated`); otherwise `record.tags` is rewritten to
    the deterministic `sorted()` output. Returns `(updated, errors)`.
    """
    change_set = set(tags)
    updated = 0
    errors: List[str] = []

    for record in rows:
        existing = set(record.tags or [])
        new_tags = (existing | change_set) if mode == "add" else (existing - change_set)

        if len(new_tags) > TAG_CAP_PER_CUSTOMER:
            errors.append(
                f"{record.customer_email}: would exceed the {TAG_CAP_PER_CUSTOMER}-tag "
                f"limit ({len(new_tags)} after applying) — not updated"
            )
            continue

        record.tags = sorted(new_tags)
        updated += 1

    return updated, errors
