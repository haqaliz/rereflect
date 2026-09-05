"""
Contract test for the AI Copilot "actions" structured_data item.

The `actions` item is a new structured_data envelope (alongside the existing
`table` and `chart` items formatted in `response_formatter.py`) that lets the
Copilot propose one-click follow-ups (e.g. "tag these customers") instead of
just returning text/table/chart. This file is the backend half of a two-suite
contract: the golden fixture at `tests/fixtures/copilot_actions_item.json` is
also read by the frontend suite, so backend and frontend never drift on the
shape independently.

See docs/planning/copilot-suggested-actions/action-contract/plan_20260906.md.
"""

import json
import pathlib

import pytest

GOLDEN_ACTIONS_PATH = (
    pathlib.Path(__file__).resolve().parent / "fixtures" / "copilot_actions_item.json"
)


def load_golden_actions_item() -> dict:
    """Load the actions-item contract shared with the frontend suite.

    Deliberately raises rather than skipping when the file is absent. A skip
    would turn the one test guarding this seam into a silent no-op -- which is
    the exact failure mode that let the Intercom envelope defect ship in every
    release, and which MessageBubble's silent data_type skip reproduces here.
    """
    if not GOLDEN_ACTIONS_PATH.exists():
        raise AssertionError(
            f"Golden actions-item fixture missing at {GOLDEN_ACTIONS_PATH}. "
            "It is a shared contract also read by the frontend suite -- "
            "restore it rather than skipping this test."
        )
    return json.loads(GOLDEN_ACTIONS_PATH.read_text())


# ============================================================================
# Structural assertions -- these describe the fixture and can pass now.
# ============================================================================


class TestGoldenActionsItemStructure:
    def test_data_type_is_actions(self):
        item = load_golden_actions_item()
        assert item["data_type"] == "actions"

    def test_proposal_id_is_a_non_empty_string(self):
        item = load_golden_actions_item()
        proposal_id = item["data"]["proposal_id"]
        assert isinstance(proposal_id, str)
        assert proposal_id != ""

    def test_actions_is_a_non_empty_list_of_well_formed_entries(self):
        item = load_golden_actions_item()
        actions = item["data"]["actions"]
        assert isinstance(actions, list)
        assert len(actions) > 0
        for entry in actions:
            assert "action" in entry
            assert "label" in entry
            assert "params" in entry
            assert "requires_input" in entry

    def test_requires_input_names_user_supplied_params_not_server_authored(self):
        """`requires_input` lists params the USER supplies at click-time.

        Pins PRD M6: the server never authors the tag value itself, it only
        names which param the frontend must collect before dispatching the
        action.
        """
        item = load_golden_actions_item()
        entry = item["data"]["actions"][0]
        assert "tag" in entry["requires_input"]
        assert "tag" not in entry["params"]
        assert all(isinstance(name, str) for name in entry["requires_input"])

    def test_envelope_has_exactly_data_type_and_data(self):
        """No sibling top-level keys for this item.

        `format_chart` sets a precedent that the envelope may carry a sibling
        key alongside `data_type`/`data` (it adds `chart_type`,
        response_formatter.py:170-174). The `actions` item uses none, and the
        tighter assertion here -- exactly {data_type, data} -- is what would
        catch a future drift onto that pattern.
        """
        item = load_golden_actions_item()
        assert set(item.keys()) == {"data_type", "data"}


# ============================================================================
# RED -- the backend does not propose actions yet.
# ============================================================================


@pytest.mark.xfail(
    reason="RED until deterministic-proposer lands; do not delete this marker "
    "without deleting the xfail",
    strict=True,
)
def test_proposer_emits_the_golden_actions_item():
    """The (not yet built) proposer must emit exactly the golden fixture.

    Imported inside the test body, not at module scope, so its absence fails
    only this test instead of erroring collection of the whole module.
    """
    from src.services.copilot.action_proposer import propose_actions

    result = propose_actions(
        message_id="msg-42",
        customer_emails=["ada@example.com", "grace@example.com", "alan@example.com"],
    )

    assert result == load_golden_actions_item()
