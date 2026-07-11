"""
Pure unit tests for src.services.status_sync_core (worker mirror).

No I/O, no DB, no Celery. This module is a verbatim copy of
services/backend-api/src/services/status_sync_core.py (see that module's
docstring) — these test cases are reused from
services/backend-api/tests/test_status_sync_core.py to lock the copy.
"""
import pytest

from src.services.status_sync_core import (
    CATEGORY_RANK,
    DEFAULT_CATEGORY_MAP,
    VALID_STATUSES,
    decide_link_update,
    is_seed,
    most_advanced,
    resolve_target_status,
)


class TestConstants:
    def test_valid_statuses(self):
        assert VALID_STATUSES == ("new", "in_review", "resolved", "closed")

    def test_default_category_map(self):
        assert DEFAULT_CATEGORY_MAP == {
            "done": "resolved",
            "indeterminate": "in_review",
            "new": "new",
        }

    def test_category_rank(self):
        assert CATEGORY_RANK == {"new": 0, "indeterminate": 1, "done": 2}


class TestResolveTargetStatus:
    @pytest.mark.parametrize(
        "category,expected",
        [
            ("done", "resolved"),
            ("indeterminate", "in_review"),
            ("new", "new"),
        ],
    )
    def test_default_map_no_mapping(self, category, expected):
        assert resolve_target_status(category, None) == expected

    @pytest.mark.parametrize(
        "category,expected",
        [
            ("done", "resolved"),
            ("indeterminate", "in_review"),
            ("new", "new"),
        ],
    )
    def test_default_map_empty_mapping(self, category, expected):
        assert resolve_target_status(category, {}) == expected

    def test_json_override_full(self):
        mapping = {"done": "closed", "indeterminate": "new", "new": "new"}
        assert resolve_target_status("done", mapping) == "closed"
        assert resolve_target_status("indeterminate", mapping) == "new"

    def test_partial_mapping_falls_back_to_default(self):
        mapping = {"done": "closed"}
        assert resolve_target_status("done", mapping) == "closed"
        assert resolve_target_status("indeterminate", mapping) == "in_review"
        assert resolve_target_status("new", mapping) == "new"

    def test_unknown_category_returns_none(self):
        assert resolve_target_status("bogus", None) is None
        assert resolve_target_status("bogus", {"bogus": "resolved"}) is None

    def test_mapped_value_outside_valid_statuses_returns_none(self):
        mapping = {"done": "archived"}  # not in VALID_STATUSES
        assert resolve_target_status("done", mapping) is None

    def test_mapping_does_not_mutate_default_map(self):
        mapping = {"done": "closed"}
        resolve_target_status("done", mapping)
        assert DEFAULT_CATEGORY_MAP["done"] == "resolved"


class TestIsSeed:
    def test_none_is_seed(self):
        assert is_seed(None) is True

    def test_non_none_is_not_seed(self):
        assert is_seed("done") is False
        assert is_seed("new") is False
        assert is_seed("indeterminate") is False


class TestMostAdvanced:
    def test_mixed_categories_returns_highest_rank(self):
        assert most_advanced(["new", "done", "indeterminate"]) == "done"

    def test_empty_list_returns_none(self):
        assert most_advanced([]) is None

    def test_all_unknown_categories_returns_none(self):
        assert most_advanced(["bogus", "also_bogus"]) is None

    def test_unknown_category_ignored_among_known(self):
        assert most_advanced(["new", "bogus"]) == "new"

    def test_single_category(self):
        assert most_advanced(["indeterminate"]) == "indeterminate"

    def test_ties_return_the_shared_rank_category(self):
        assert most_advanced(["done", "done"]) == "done"


class TestDecideLinkUpdate:
    def test_seed_when_stored_is_none(self):
        action, name, category = decide_link_update("new", "To Do", None)
        assert action == "seed"
        assert name == "To Do"
        assert category == "new"

    def test_noop_when_unchanged(self):
        action, name, category = decide_link_update("done", "Done", "done")
        assert action == "noop"
        assert name == "Done"
        assert category == "done"

    def test_changed_when_transitioning(self):
        action, name, category = decide_link_update("done", "Done", "new")
        assert action == "changed"
        assert name == "Done"
        assert category == "done"

    def test_changed_indeterminate_to_done(self):
        action, name, category = decide_link_update(
            "done", "Done", "indeterminate"
        )
        assert action == "changed"
        assert name == "Done"
        assert category == "done"
