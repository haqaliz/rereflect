"""
Pure unit tests for src.services.zendesk_status_core.

No I/O, no DB, no FastAPI. This module is later copied verbatim into the
worker service, so these tests must never import anything beyond the
module under test.
"""
import pytest

from src.services.zendesk_status_core import (
    DEFAULT_ZENDESK_MAP,
    ZENDESK_STATUSES,
    decide_update,
    resolve_target_status,
)
from src.services.status_sync_core import (
    CATEGORY_RANK,
    DEFAULT_CATEGORY_MAP,
    VALID_STATUSES,
)


class TestConstants:
    def test_zendesk_statuses(self):
        assert ZENDESK_STATUSES == ("new", "open", "pending", "hold", "solved", "closed")

    def test_default_zendesk_map(self):
        assert DEFAULT_ZENDESK_MAP == {
            "new": "new",
            "open": "in_review",
            "pending": "in_review",
            "hold": "in_review",
            "solved": "resolved",
            "closed": "closed",
        }


class TestJiraCharacterization:
    """Guard rail: status_sync_core.py (Jira) must remain byte-identical."""

    def test_valid_statuses_unchanged(self):
        assert VALID_STATUSES == ("new", "in_review", "resolved", "closed")

    def test_default_category_map_unchanged(self):
        assert DEFAULT_CATEGORY_MAP == {
            "done": "resolved",
            "indeterminate": "in_review",
            "new": "new",
        }

    def test_category_rank_unchanged(self):
        assert CATEGORY_RANK == {"new": 0, "indeterminate": 1, "done": 2}


class TestResolveTargetStatus:
    @pytest.mark.parametrize(
        "zendesk_status,expected",
        [
            ("new", "new"),
            ("open", "in_review"),
            ("pending", "in_review"),
            ("hold", "in_review"),
            ("solved", "resolved"),
            ("closed", "closed"),
        ],
    )
    def test_default_map_no_mapping(self, zendesk_status, expected):
        assert resolve_target_status(zendesk_status, None) == expected

    @pytest.mark.parametrize(
        "zendesk_status,expected",
        [
            ("new", "new"),
            ("open", "in_review"),
            ("pending", "in_review"),
            ("hold", "in_review"),
            ("solved", "resolved"),
            ("closed", "closed"),
        ],
    )
    def test_default_map_empty_mapping(self, zendesk_status, expected):
        assert resolve_target_status(zendesk_status, {}) == expected

    def test_override_merge(self):
        mapping = {"closed": "resolved"}
        assert resolve_target_status("closed", mapping) == "resolved"
        # non-overridden keys still fall back to defaults
        assert resolve_target_status("solved", mapping) == "resolved"
        assert resolve_target_status("new", mapping) == "new"

    def test_unknown_status_returns_none(self):
        assert resolve_target_status("bogus", None) is None
        assert resolve_target_status("bogus", {}) is None

    def test_bad_target_returns_none(self):
        mapping = {"open": "bogus"}
        assert resolve_target_status("open", mapping) is None

    def test_mapping_does_not_mutate_default_map(self):
        mapping = {"closed": "resolved"}
        resolve_target_status("closed", mapping)
        assert DEFAULT_ZENDESK_MAP["closed"] == "closed"


class TestDecideUpdate:
    def test_seed_when_stored_is_none(self):
        assert decide_update("open", None) == "seed"

    def test_noop_when_unchanged(self):
        assert decide_update("open", "open") == "noop"

    def test_changed_when_transitioning(self):
        assert decide_update("solved", "open") == "changed"
