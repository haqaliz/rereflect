"""
Phase D TDD — deterministic action proposer (copilot-suggested-actions).

Unit tests for the pure, synchronous proposer module
(`src/services/copilot/action_proposer.py`):

- `extract_customer_emails`: finds the customer-email column in a SQL result
  by name (`customer_email` / `email`, case-insensitive, first match wins),
  collects non-empty string values in row order and dedupes order-preservingly.
- `propose_actions`: emits the `actions` envelope for a frozen cohort of
  emails — deterministic `proposal_id` for identical (message_id, emails)
  inputs, changing when the cohort changes. Pure Python, no LLM imports.

See docs/planning/copilot-suggested-actions/deterministic-proposer/plan_20260909.md
(Phase D) and the action-contract spec for the envelope shape.
"""

from src.services.copilot.action_proposer import (
    ACTION_EMAIL_CAP,
    extract_customer_emails,
    propose_actions,
)


# ── extract_customer_emails ──────────────────────────────────────────────────


class TestExtractCustomerEmails:
    def test_returns_non_empty_strings_in_row_order_with_order_preserving_dedupe(self):
        columns = ["customer_email", "sentiment"]
        rows = [
            ["a@x.com", "neg"],
            ["b@y.com", "pos"],
            ["a@x.com", "neg"],
        ]
        assert extract_customer_emails(columns, rows) == ["a@x.com", "b@y.com"]

    def test_email_column_name_also_matches(self):
        columns = ["email", "feedback_count"]
        rows = [["grace@example.com", 3], ["ada@example.com", 1]]
        assert extract_customer_emails(columns, rows) == [
            "grace@example.com",
            "ada@example.com",
        ]

    def test_column_match_is_case_insensitive(self):
        columns = ["Customer_Email", "sentiment"]
        rows = [["a@x.com", "pos"]]
        assert extract_customer_emails(columns, rows) == ["a@x.com"]

    def test_first_matching_column_wins(self):
        columns = ["email", "customer_email"]
        rows = [["first@x.com", "second@x.com"]]
        assert extract_customer_emails(columns, rows) == ["first@x.com"]

    def test_no_email_column_returns_empty_list(self):
        assert extract_customer_emails(["sentiment", "created_at"], [["neg", "2026"]]) == []

    def test_empty_rows_return_empty_list(self):
        assert extract_customer_emails(["customer_email"], []) == []

    def test_empty_and_non_string_cell_values_are_skipped(self):
        columns = ["customer_email", "sentiment"]
        rows = [
            ["a@x.com", "pos"],
            ["", "pos"],
            [None, "pos"],
            [42, "pos"],
            ["b@y.com", "neg"],
        ]
        assert extract_customer_emails(columns, rows) == ["a@x.com", "b@y.com"]


# ── propose_actions ──────────────────────────────────────────────────────────


class TestProposeActions:
    def test_emits_the_actions_envelope_with_exact_shape(self):
        result = propose_actions(
            message_id="msg-42",
            customer_emails=["ada@example.com", "grace@example.com", "alan@example.com"],
        )

        assert set(result.keys()) == {"data_type", "data"}
        assert result["data_type"] == "actions"

        data = result["data"]
        assert data["proposal_id"] == "msg-42:tag_customers:4a72f4"
        assert len(data["actions"]) == 1

        entry = data["actions"][0]
        assert entry["action"] == "tag_customers"
        assert entry["label"] == "Tag these 3 customers…"
        assert entry["params"] == {
            "emails": ["ada@example.com", "grace@example.com", "alan@example.com"]
        }
        assert entry["requires_input"] == ["tag"]
        assert "tag" not in entry["params"]

    def test_proposal_id_is_stable_for_identical_inputs(self):
        emails = ["ada@example.com", "grace@example.com"]
        first = propose_actions(message_id="m1", customer_emails=emails)
        second = propose_actions(message_id="m1", customer_emails=list(emails))
        assert first["data"]["proposal_id"] == second["data"]["proposal_id"]
        assert first == second

    def test_proposal_id_changes_when_emails_change(self):
        first = propose_actions(message_id="m1", customer_emails=["ada@example.com"])
        second = propose_actions(message_id="m1", customer_emails=["grace@example.com"])
        assert first["data"]["proposal_id"] != second["data"]["proposal_id"]

    def test_proposal_id_changes_when_message_id_changes(self):
        first = propose_actions(message_id="m1", customer_emails=["ada@example.com"])
        second = propose_actions(message_id="m2", customer_emails=["ada@example.com"])
        assert first["data"]["proposal_id"] != second["data"]["proposal_id"]

    def test_cohort_is_deduped_before_hashing_and_labeling(self):
        result = propose_actions(
            message_id="msg-42",
            customer_emails=[
                "ada@example.com",
                "grace@example.com",
                "ada@example.com",
                "alan@example.com",
            ],
        )
        entry = result["data"]["actions"][0]
        assert entry["params"]["emails"] == [
            "ada@example.com",
            "grace@example.com",
            "alan@example.com",
        ]
        assert entry["label"] == "Tag these 3 customers…"
        assert result["data"]["proposal_id"] == "msg-42:tag_customers:4a72f4"

    def test_single_customer_label_uses_the_same_template(self):
        result = propose_actions(message_id="m1", customer_emails=["ada@example.com"])
        entry = result["data"]["actions"][0]
        assert entry["label"] == "Tag these 1 customers…"


# ── Cap constant ─────────────────────────────────────────────────────────────


class TestActionEmailCap:
    def test_cap_is_200(self):
        """The action cap is its own constant, under MAX_TABLE_ROWS=1000.

        See plan decision: a result over the cap offers no action rather than
        a silently truncated cohort.
        """
        assert ACTION_EMAIL_CAP == 200
