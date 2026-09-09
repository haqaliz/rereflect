"""
Phase E TDD — the deterministic proposer hooked into copilot_ws.

These tests drive the genuine `copilot_ws._handle_query` path (SQL results
fed via a patched `SQLExecutor`, so no real DB) and assert on the **emitted
WS frame**, not on `propose_actions` in isolation — a correct proposer whose
output `copilot_ws` never appended must fail here.

Pinned behaviours (deterministic-proposer spec / plan 2026-09-09, Phase E):

1. data-intent, >=1 row with a `customer_email` column -> the structured_data
   frame carries the golden `actions` item.
2. no customer-email column -> no actions item; structured_data is exactly
   `format_response`'s output (table only).
3. single row (row_count == 1): no table, but the actions item is present and
   the frame IS emitted (previously an empty list suppressed the frame at the
   `if structured_data_payload:` gate -- the pinned behavioural change).
4. result over ACTION_EMAIL_CAP (201 unique emails) -> no actions item.
5. `general` intent -> no actions item (no early return exists for general;
   the property holds via the intent guard + truthiness gate).
6. zero rows -> no actions item.
7. no LLM call during proposal: resolve_generation_llm and call_llm_stream are
   each invoked exactly once per data query (the summarization stream), not by
   the proposer path.
"""

import json
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.copilot.action_proposer import ACTION_EMAIL_CAP
from src.services.copilot.llm_resolver import LLMConfig

GOLDEN_ACTIONS_PATH = (
    pathlib.Path(__file__).resolve().parent / "fixtures" / "copilot_actions_item.json"
)


async def _empty_stream_gen():
    """Async generator that yields nothing (mocks call_llm_stream)."""
    if False:
        yield
    return


def load_golden_actions_item() -> dict:
    return json.loads(GOLDEN_ACTIONS_PATH.read_text())


def _llm_cfg() -> LLMConfig:
    return LLMConfig(
        provider="openai",
        model="gpt-4o-mini",
        api_key="sk-test",
        base_url=None,
        is_configured=True,
    )


def _find_structured_frames(received_messages):
    return [m for m in received_messages if m.get("type") == "structured_data"]


def _items_in(frame):
    return frame["data"]["structured_data"]


def _actions_items_in(frames):
    return [
        item
        for frame in frames
        for item in _items_in(frame)
        if item["data_type"] == "actions"
    ]


class TestCopilotProposerEmission:
    def _make_mocks(self):
        mock_ws = AsyncMock()
        mock_org = MagicMock()
        mock_org.id = 1
        mock_user = MagicMock()
        mock_user.id = 1
        mock_conv = MagicMock()
        mock_conv.id = 1

        mock_db = MagicMock()
        mock_db.execute.return_value = MagicMock()
        mock_sub = MagicMock()
        mock_sub.plan = "pro"
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_sub
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

        received_messages = []
        mock_ws.send_json = AsyncMock(side_effect=received_messages.append)
        return mock_ws, mock_org, mock_user, mock_conv, mock_db, received_messages

    async def _run_data_query(self, sql_result, message_id="msg-42", content="list the customers who left negative feedback", intent="data"):
        """Drive `_handle_query` with a patched SQLExecutor returning sql_result."""
        from src.api.routes.copilot_ws import _handle_query

        mock_ws, mock_org, mock_user, mock_conv, mock_db, received_messages = self._make_mocks()

        patches = [
            patch("src.api.routes.copilot_ws.resolve_generation_llm", return_value=_llm_cfg()),
            patch("src.api.routes.copilot_ws.resolve_embedding_provider", return_value=None),
            patch("src.api.routes.copilot_ws.IntentClassifier"),
            patch("src.api.routes.copilot_ws.ContextResolver"),
            patch("src.api.routes.copilot_ws.TemplateMatcher"),
            patch("src.api.routes.copilot_ws.SQLGenerator"),
            patch("src.api.routes.copilot_ws.SQLExecutor"),
            patch("src.api.routes.copilot_ws.call_llm_stream",
                  side_effect=lambda **kw: _empty_stream_gen()),
            patch("src.api.routes.copilot_ws.TemplateSaver"),
        ]
        with patches[0], patches[1], patches[2] as MockIC, patches[3] as MockCR, \
                patches[4] as MockMatcher, patches[5] as MockGen, patches[6] as MockExec, \
                patches[7], patches[8]:
            MockIC.return_value.classify.return_value = {
                "intent": intent, "confidence": 0.9, "reason": ""
            }
            MockCR.return_value.parse_mentions.return_value = []
            MockCR.return_value.build_context.return_value = "org context"
            MockMatcher.return_value.find_match.return_value = None
            MockGen.return_value.generate.return_value = {
                "sql": "SELECT customer_email FROM feedback",
                "parameters": {"org_id": 1},
                "query_type": "data",
                "error": None,
            }
            if sql_result is not None:
                MockExec.return_value.execute.return_value = sql_result

            await _handle_query(
                websocket=mock_ws, db=mock_db, user=mock_user,
                org=mock_org, conversation=mock_conv,
                content=content, context_scope="all_data", message_id=message_id,
            )

        return received_messages

    @pytest.mark.asyncio
    async def test_data_result_with_customer_email_column_emits_golden_actions_item(self):
        """data intent + >=1 row with customer_email -> frame carries the fixture item."""
        rows = [
            ["ada@example.com", "neg"],
            ["grace@example.com", "pos"],
            ["alan@example.com", "neg"],
        ]
        received = await self._run_data_query({
            "columns": ["customer_email", "sentiment"],
            "rows": rows,
            "row_count": len(rows),
            "truncated": False,
        })

        frames = _find_structured_frames(received)
        assert len(frames) == 1, f"expected one structured_data frame, got: {received}"
        actions_items = _actions_items_in(frames)
        assert len(actions_items) == 1
        assert actions_items[0] == load_golden_actions_item()

    @pytest.mark.asyncio
    async def test_no_email_column_means_no_actions_item_and_exact_format_response_output(self):
        """No customer-email column -> structured_data exactly as today (table only)."""
        from src.services.copilot.response_formatter import format_response

        columns = ["sentiment", "feedback_count"]
        rows = [
            ["neg", 4],
            ["pos", 7],
        ]
        received = await self._run_data_query({
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": False,
        })

        frames = _find_structured_frames(received)
        assert len(frames) == 1
        expected = format_response(
            text="", sql_columns=columns, sql_rows=rows,
            include_table=True, include_chart=False,
        )["structured_data"]
        assert _items_in(frames[0]) == expected
        assert _actions_items_in(frames) == []

    @pytest.mark.asyncio
    async def test_single_row_no_table_but_actions_item_and_frame_emitted(self):
        """row_count == 1: no table today, but the actions item must emit a frame."""
        from src.services.copilot.action_proposer import propose_actions

        rows = [["solo@example.com", "neg"]]
        received = await self._run_data_query({
            "columns": ["customer_email", "sentiment"],
            "rows": rows,
            "row_count": len(rows),
            "truncated": False,
        })

        frames = _find_structured_frames(received)
        assert len(frames) == 1, (
            "single-row result with an actions item must emit a structured_data "
            f"frame; got messages: {received}"
        )
        items = _items_in(frames[0])
        assert len(items) == 1
        expected_item = propose_actions(
            message_id="msg-42", customer_emails=["solo@example.com"]
        )
        assert items[0] == expected_item
        assert items[0]["data_type"] == "actions"

    @pytest.mark.asyncio
    async def test_result_over_the_cap_offers_no_action(self):
        """201 unique emails > ACTION_EMAIL_CAP -> no actions item (never truncated)."""
        emails = [f"customer{i:03d}@example.com" for i in range(ACTION_EMAIL_CAP + 1)]
        rows = [[email, "neg"] for email in emails]
        received = await self._run_data_query({
            "columns": ["customer_email", "sentiment"],
            "rows": rows,
            "row_count": len(rows),
            "truncated": False,
        })

        frames = _find_structured_frames(received)
        assert len(frames) == 1
        assert _actions_items_in(frames) == []
        table_types = [item["data_type"] for item in _items_in(frames[0])]
        assert "actions" not in table_types

    @pytest.mark.asyncio
    async def test_general_intent_never_emits_actions_item(self):
        """general intent -> no actions item (property via intent guard + gate)."""
        received = await self._run_data_query(
            sql_result=None, intent="general", content="hello there"
        )
        frames = _find_structured_frames(received)
        assert frames == [], f"general intent must emit no structured_data frame: {received}"
        assert _actions_items_in(frames) == []

    @pytest.mark.asyncio
    async def test_zero_rows_offers_no_action(self):
        rows = []
        received = await self._run_data_query({
            "columns": ["customer_email", "sentiment"],
            "rows": rows,
            "row_count": 0,
            "truncated": False,
        })

        frames = _find_structured_frames(received)
        assert frames == [], f"zero rows must emit no structured_data frame: {received}"
        assert _actions_items_in(frames) == []

    @pytest.mark.asyncio
    async def test_proposal_makes_no_llm_calls(self):
        """The proposer path adds no LLM work: exactly one of each LLM call."""
        from src.api.routes.copilot_ws import _handle_query

        mock_ws, mock_org, mock_user, mock_conv, mock_db, received_messages = self._make_mocks()

        rows = [
            ["ada@example.com", "neg"],
            ["grace@example.com", "pos"],
        ]
        with patch("src.api.routes.copilot_ws.resolve_generation_llm") as MockLLM, \
             patch("src.api.routes.copilot_ws.resolve_embedding_provider", return_value=None), \
             patch("src.api.routes.copilot_ws.IntentClassifier") as MockIC, \
             patch("src.api.routes.copilot_ws.ContextResolver") as MockCR, \
             patch("src.api.routes.copilot_ws.TemplateMatcher") as MockMatcher, \
             patch("src.api.routes.copilot_ws.SQLGenerator") as MockGen, \
             patch("src.api.routes.copilot_ws.SQLExecutor") as MockExec, \
             patch("src.api.routes.copilot_ws.call_llm_stream",
                   side_effect=lambda **kw: _empty_stream_gen()) as MockLLMStream, \
             patch("src.api.routes.copilot_ws.TemplateSaver"):
            MockLLM.return_value = _llm_cfg()
            MockIC.return_value.classify.return_value = {
                "intent": "data", "confidence": 0.9, "reason": ""
            }
            MockCR.return_value.parse_mentions.return_value = []
            MockCR.return_value.build_context.return_value = "org context"
            MockMatcher.return_value.find_match.return_value = None
            MockGen.return_value.generate.return_value = {
                "sql": "SELECT customer_email FROM feedback",
                "parameters": {"org_id": 1},
                "query_type": "data",
                "error": None,
            }
            MockExec.return_value.execute.return_value = {
                "columns": ["customer_email", "sentiment"],
                "rows": rows,
                "row_count": len(rows),
                "truncated": False,
            }

            await _handle_query(
                websocket=mock_ws, db=mock_db, user=mock_user,
                org=mock_org, conversation=mock_conv,
                content="list customers by sentiment", context_scope="all_data",
                message_id="msg-42",
            )

        frames = _find_structured_frames(received_messages)
        assert len(_actions_items_in(frames)) == 1, "actions item must have been proposed"
        assert MockLLM.call_count == 1, (
            "resolve_generation_llm must be called exactly once (query LLM config), "
            "never by the proposer"
        )
        assert MockLLMStream.call_count == 1, (
            "call_llm_stream must be called exactly once (the summary stream), "
            "never by the proposer"
        )
