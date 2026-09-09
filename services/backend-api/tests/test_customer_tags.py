"""
Characterization tests for the shared customer tag-apply service.

Drives `src.services.customer_tags.apply_tags` directly, pinning exactly the
behaviours the existing `POST /api/v1/customers/bulk/tags` route pins in
`tests/test_customers_bulk.py` (which stays green untouched as the route-level
characterization net): set-union add, set-difference remove, deterministic
sorted() output, the 20-tag cap putting the row into `errors` (row unchanged,
not counted in `updated`), and de-duped/empty input handling.

Rows are plain in-memory `CustomerHealth` instances — `apply_tags` only reads
and rewrites `record.tags`, it never touches the DB (the route owns the single
`db.commit()`).
"""
import pytest

from src.models.customer_health import CustomerHealth
from src.services.customer_tags import (
    TAG_CAP_PER_CUSTOMER,
    TAG_MAX_LENGTH,
    apply_tags,
)


def _row(email: str, tags=None) -> CustomerHealth:
    return CustomerHealth(organization_id=1, customer_email=email, tags=tags)


class TestTagConstants:
    def test_max_length_is_50(self):
        assert TAG_MAX_LENGTH == 50

    def test_cap_per_customer_is_20(self):
        assert TAG_CAP_PER_CUSTOMER == 20


class TestApplyTagsAdd:
    def test_add_unions_existing_and_sorts_output(self):
        row = _row("a@example.com", tags=["existing"])
        updated, errors = apply_tags([row], ["vip", "existing"], "add")

        assert (updated, errors) == (1, [])
        assert row.tags == ["existing", "vip"]

    def test_add_dedupes_repeated_input_tags(self):
        row = _row("a@example.com", tags=[])
        updated, errors = apply_tags([row], ["vip", "vip", "vip"], "add")

        assert (updated, errors) == (1, [])
        assert row.tags == ["vip"]

    def test_add_with_empty_tag_list_is_a_sorted_rewrite_not_an_error(self):
        row = _row("a@example.com", tags=["b", "a"])
        updated, errors = apply_tags([row], [], "add")

        assert (updated, errors) == (1, [])
        assert row.tags == ["a", "b"]

    def test_exactly_20_tags_after_add_is_allowed(self):
        row = _row("a@example.com", tags=[f"tag{i}" for i in range(18)])
        updated, errors = apply_tags([row], ["new1", "new2"], "add")

        assert (updated, errors) == (1, [])
        assert len(row.tags) == 20

    def test_over_cap_row_goes_to_errors_unchanged_not_counted_updated(self):
        existing = [f"tag{i}" for i in range(19)]
        row = _row("a@example.com", tags=list(existing))
        updated, errors = apply_tags([row], ["new1", "new2"], "add")

        assert updated == 0
        assert errors == [
            "a@example.com: would exceed the 20-tag limit "
            "(21 after applying) — not updated"
        ]
        # Row unchanged (still 19 original tags, not truncated, no partial add)
        assert row.tags == existing

    def test_one_over_cap_row_in_errors_while_others_still_update(self):
        full = _row("full@example.com", tags=[f"tag{i}" for i in range(19)])
        room = _row("room@example.com", tags=["tag0"])
        updated, errors = apply_tags([full, room], ["new1", "new2"], "add")

        assert updated == 1
        assert len(errors) == 1
        assert "full@example.com" in errors[0]
        assert full.tags == [f"tag{i}" for i in range(19)]  # unchanged
        assert room.tags == ["new1", "new2", "tag0"]  # sorted union applied

    def test_case_sensitive_tags_are_distinct(self):
        row = _row("a@example.com", tags=["Churn"])
        updated, errors = apply_tags([row], ["churn"], "add")

        assert (updated, errors) == (1, [])
        assert row.tags == ["Churn", "churn"]


class TestApplyTagsRemove:
    def test_remove_difference_sorts_output(self):
        row = _row("a@example.com", tags=["vip", "expansion", "keep"])
        updated, errors = apply_tags([row], ["vip", "expansion"], "remove")

        assert (updated, errors) == (1, [])
        assert row.tags == ["keep"]

    def test_remove_nonexistent_tag_is_noop_not_error(self):
        row = _row("a@example.com", tags=["keep"])
        updated, errors = apply_tags([row], ["not-there"], "remove")

        assert (updated, errors) == (1, [])
        assert row.tags == ["keep"]

    def test_remove_from_row_with_null_tags(self):
        row = _row("a@example.com", tags=None)
        updated, errors = apply_tags([row], ["vip"], "remove")

        assert (updated, errors) == (1, [])
        assert row.tags == []
