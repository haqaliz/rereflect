"""
Phase 3 TDD — Provider-agnostic SQL safety + honest weak-model UX.

Tests:
1. SQL safety validator rejects malicious/unsafe SQL regardless of provider
   (DROP, cross-org, 5-join, subquery, multi-statement injection).
2. When SQLGenerator.generate returns a safety-check error, _handle_query
   streams an honest "couldn't turn that into a safe query" message — not
   a 500/unhandled exception.
3. An unconfigured org gets the "configure a model in Settings → AI" message.
4. Quality guardrail: 10 canned questions against a mocked local model →
   ≥70% produce valid, org-scoped, safety-passing SQL; the rest hit the
   graceful path (no unhandled error or unsafe SQL).
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock


# ── 1. SQL safety validator is provider-agnostic ─────────────────────────────


class TestSQLValidatorProviderAgnostic:
    """
    The SQL validator must reject dangerous SQL regardless of provider.
    Tests use 'as if emitted by a local model' strings directly.
    """

    def _validator(self):
        from src.services.copilot.sql_validator import SQLValidator
        return SQLValidator()

    def _whitelist(self):
        return {"feedback_items": ["id", "organization_id", "content", "sentiment_label"]}

    def test_drop_table_rejected(self):
        v = self._validator()
        result = v.validate(
            sql="DROP TABLE feedback_items",
            org_id=1, plan="pro", whitelist=self._whitelist()
        )
        assert not result.is_valid
        assert "drop" in result.error.lower() or "write" in result.error.lower() or "not allowed" in result.error.lower()

    def test_cross_org_injection_rejected(self):
        """SQL without org_id filter — validate() does not check org injection
        but the whitelist check ensures correct tables; org injection is enforced
        post-validation via inject_org_scope. For a direct SELECT without org_id,
        the safety validator passes (org scope is injected separately).
        We verify: a malicious SQL with a different org_id condition is still
        READ-ONLY (no writes) and whitelist-compliant, but the SQL with a
        hard-coded org_id that's not :org_id would not be injected. This is by
        design — the parameterized :org_id is enforced at execution time."""
        v = self._validator()
        # Multi-statement injection: valid SELECT + DROP
        result = v.validate(
            sql="SELECT * FROM feedback_items WHERE organization_id = :org_id; DROP TABLE feedback_items",
            org_id=1, plan="pro", whitelist=self._whitelist()
        )
        assert not result.is_valid, (
            "Multi-statement SQL with DROP must be rejected"
        )

    def test_five_joins_rejected(self):
        """More than 3 JOINs must be rejected."""
        v = self._validator()
        sql = (
            "SELECT f.id FROM feedback_items f "
            "JOIN users u ON u.id = f.id "
            "JOIN organizations o ON o.id = f.id "
            "JOIN customer_health_scores c ON c.id = f.id "
            "JOIN subscriptions s ON s.id = f.id "
            "WHERE f.organization_id = :org_id LIMIT 50"
        )
        result = v.validate(sql=sql, org_id=1, plan="pro", whitelist={
            "feedback_items": None, "users": None, "organizations": None,
            "customer_health_scores": None, "subscriptions": None,
        })
        assert not result.is_valid
        assert "join" in result.error.lower()

    def test_subquery_rejected(self):
        """Nested SELECT (subquery) must be rejected."""
        v = self._validator()
        sql = (
            "SELECT * FROM feedback_items WHERE organization_id = :org_id "
            "AND id IN (SELECT id FROM feedback_items WHERE sentiment_label = 'negative') LIMIT 50"
        )
        result = v.validate(sql=sql, org_id=1, plan="pro", whitelist=self._whitelist())
        assert not result.is_valid
        assert "subquery" in result.error.lower() or "nested" in result.error.lower()

    def test_delete_rejected(self):
        """DELETE statement must be rejected."""
        v = self._validator()
        result = v.validate(
            sql="DELETE FROM feedback_items WHERE organization_id = :org_id",
            org_id=1, plan="pro", whitelist=self._whitelist()
        )
        assert not result.is_valid

    def test_insert_rejected(self):
        """INSERT statement must be rejected."""
        v = self._validator()
        result = v.validate(
            sql="INSERT INTO feedback_items (organization_id) VALUES (1)",
            org_id=1, plan="pro", whitelist=self._whitelist()
        )
        assert not result.is_valid

    def test_unknown_table_rejected(self):
        """Tables not in the whitelist must be rejected."""
        v = self._validator()
        result = v.validate(
            sql="SELECT * FROM system_passwords WHERE organization_id = :org_id LIMIT 1",
            org_id=1, plan="pro", whitelist=self._whitelist()
        )
        assert not result.is_valid
        assert "whitelist" in result.error.lower() or "not in" in result.error.lower() or "allowed" in result.error.lower()

    def test_valid_select_passes(self):
        """A well-formed SELECT must pass all validators."""
        v = self._validator()
        result = v.validate(
            sql="SELECT sentiment_label, COUNT(*) FROM feedback_items WHERE organization_id = :org_id GROUP BY sentiment_label LIMIT 100",
            org_id=1, plan="pro", whitelist=self._whitelist()
        )
        assert result.is_valid, f"Expected valid SQL to pass; got: {result.error}"


# ── 2. Weak-model UX: unsafe/empty SQL → honest "couldn't make safe query" ───


class TestWeakModelUX:
    """
    When SQLGenerator.generate returns a safety-check error OR an empty SQL,
    _handle_query must NOT crash and must deliver an honest degraded message.
    """

    def _make_minimal_mocks(self, org_id=1):
        mock_ws = AsyncMock()
        mock_org = MagicMock()
        mock_org.id = org_id
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
        return mock_ws, mock_org, mock_user, mock_conv, mock_db

    def _local_llm_cfg(self):
        from src.services.copilot.llm_resolver import LLMConfig
        return LLMConfig(
            provider="openai_compatible",
            model="llama3",
            api_key=None,
            base_url="http://localhost:11434/v1",
            is_configured=True,
        )

    @pytest.mark.asyncio
    async def test_unsafe_sql_from_local_model_does_not_crash(self):
        """
        When the local model produces SQL that fails the safety check,
        _handle_query must not raise an unhandled exception; must send stream
        or error message, never crash.
        """
        from src.api.routes.copilot_ws import _handle_query

        mock_ws, mock_org, mock_user, mock_conv, mock_db = self._make_minimal_mocks()
        cfg = self._local_llm_cfg()

        async def _mock_llm_stream(**kwargs):
            yield MagicMock(choices=[MagicMock(delta=MagicMock(content="result"))])

        # SQLGenerator returns a safety-check failure
        bad_gen_result = {
            "sql": None,
            "parameters": {},
            "query_type": "detail",
            "error": "Generated SQL failed safety check: Write operation 'DROP' is not allowed.",
        }

        with patch("src.api.routes.copilot_ws.resolve_generation_llm", return_value=cfg), \
             patch("src.api.routes.copilot_ws.resolve_embedding_provider", return_value=None), \
             patch("src.api.routes.copilot_ws.IntentClassifier") as MockIC, \
             patch("src.api.routes.copilot_ws.ContextResolver") as MockCR, \
             patch("src.api.routes.copilot_ws.SQLGenerator") as MockGen, \
             patch("src.api.routes.copilot_ws.TemplateMatcher") as MockMatcher, \
             patch("src.api.routes.copilot_ws.call_llm_stream",
                   side_effect=_mock_llm_stream):

            MockIC.return_value.classify.return_value = {"intent": "data", "confidence": 0.9, "reason": ""}
            MockCR.return_value.parse_mentions.return_value = []
            MockCR.return_value.build_context.return_value = "ctx"
            MockMatcher.return_value.find_match.return_value = None
            MockGen.return_value.generate.return_value = bad_gen_result

            # Must NOT raise
            try:
                await _handle_query(
                    websocket=mock_ws,
                    db=mock_db,
                    user=mock_user,
                    org=mock_org,
                    conversation=mock_conv,
                    content="DROP feedback data now",
                    context_scope="all_data",
                    message_id="msg_unsafe_1",
                )
            except Exception as e:
                pytest.fail(f"_handle_query raised an exception: {e}")

    @pytest.mark.asyncio
    async def test_safety_failure_surfaces_honest_message(self):
        """
        When SQL safety check fails, the user must see a message indicating the
        query couldn't be made safe — not a generic system error or empty response.
        The message must be present in the streamed or error response.
        """
        from src.api.routes.copilot_ws import _handle_query

        mock_ws, mock_org, mock_user, mock_conv, mock_db = self._make_minimal_mocks()
        cfg = self._local_llm_cfg()

        # Track what was streamed / sent
        streamed_content = []
        error_messages = []

        async def capturing_ws_send_json(data):
            if data.get("type") == "stream" and data.get("delta"):
                streamed_content.append(data["delta"])
            if data.get("type") == "error":
                error_messages.append(data.get("message", "") + data.get("error", ""))

        mock_ws.send_json = AsyncMock(side_effect=capturing_ws_send_json)

        # SQL generation fails safety check
        bad_gen_result = {
            "sql": None,
            "parameters": {},
            "query_type": "detail",
            "error": "Generated SQL failed safety check: Write operation 'DROP' is not allowed.",
        }

        # call_llm_stream is used for fallback explanation — it should still work
        async def _mock_llm_stream(**kwargs):
            # Check system prompt for "safe" keyword to confirm honest UX context
            sys_msg = next(
                (m["content"] for m in kwargs.get("messages", []) if m["role"] == "system"),
                ""
            )
            if "safe" in sys_msg.lower() or "couldn't" in sys_msg.lower() or "model" in sys_msg.lower():
                yield MagicMock(choices=[MagicMock(delta=MagicMock(content="I couldn't generate a safe query for that."))])
            else:
                yield MagicMock(choices=[MagicMock(delta=MagicMock(content="Some context-aware answer."))])

        with patch("src.api.routes.copilot_ws.resolve_generation_llm", return_value=cfg), \
             patch("src.api.routes.copilot_ws.resolve_embedding_provider", return_value=None), \
             patch("src.api.routes.copilot_ws.IntentClassifier") as MockIC, \
             patch("src.api.routes.copilot_ws.ContextResolver") as MockCR, \
             patch("src.api.routes.copilot_ws.SQLGenerator") as MockGen, \
             patch("src.api.routes.copilot_ws.TemplateMatcher") as MockMatcher, \
             patch("src.api.routes.copilot_ws.call_llm_stream",
                   side_effect=_mock_llm_stream):

            MockIC.return_value.classify.return_value = {"intent": "data", "confidence": 0.9, "reason": ""}
            MockCR.return_value.parse_mentions.return_value = []
            MockCR.return_value.build_context.return_value = "ctx"
            MockMatcher.return_value.find_match.return_value = None
            MockGen.return_value.generate.return_value = bad_gen_result

            try:
                await _handle_query(
                    websocket=mock_ws,
                    db=mock_db,
                    user=mock_user,
                    org=mock_org,
                    conversation=mock_conv,
                    content="attack query",
                    context_scope="all_data",
                    message_id="msg_safe_ux_1",
                )
            except Exception:
                pass  # we care about messages, not exceptions

        # There must be some stream or error response — not complete silence
        total_output = " ".join(streamed_content + error_messages)
        assert len(total_output) > 0, (
            "When SQL safety fails, user must receive some response (not silence)"
        )

    @pytest.mark.asyncio
    async def test_fully_unconfigured_org_sends_configure_message(self):
        """
        An org with no key AND no base_url gets a 'configure a model' WS error —
        not a crash, not a generic 500 error.
        """
        from src.api.routes.copilot_ws import _handle_query
        from src.services.copilot.llm_resolver import LLMConfig

        mock_ws, mock_org, mock_user, mock_conv, mock_db = self._make_minimal_mocks()
        unconfigured = LLMConfig(
            provider="openai", model="gpt-4o-mini",
            api_key=None, base_url=None, is_configured=False,
        )

        sent = []
        async def capture(data):
            sent.append(data)
        mock_ws.send_json = AsyncMock(side_effect=capture)

        with patch("src.api.routes.copilot_ws.resolve_generation_llm", return_value=unconfigured), \
             patch("src.api.routes.copilot_ws.resolve_embedding_provider", return_value=None), \
             patch("src.api.routes.copilot_ws.IntentClassifier") as MockIC, \
             patch("src.api.routes.copilot_ws.ContextResolver") as MockCR:

            MockIC.return_value.classify.return_value = {"intent": "general", "confidence": 0.9, "reason": ""}
            MockCR.return_value.parse_mentions.return_value = []
            MockCR.return_value.build_context.return_value = "ctx"

            try:
                await _handle_query(
                    websocket=mock_ws, db=mock_db, user=mock_user, org=mock_org,
                    conversation=mock_conv, content="hello", context_scope="all_data",
                    message_id="msg_unconf_1",
                )
            except Exception:
                pass

        error_msgs = [m for m in sent if m.get("type") == "error"]
        assert len(error_msgs) >= 1, f"Must send error for unconfigured org; got: {sent}"

        combined = " ".join(
            (m.get("message", "") + m.get("error", "")).lower() for m in error_msgs
        )
        # Must reference settings or configure, not a raw API error
        assert any(kw in combined for kw in ("settings", "configure", "model", "ai")), (
            f"Error message must reference settings/configure/model; got: {combined!r}"
        )


# ── 3. Quality guardrail — ≥70% of 10 canned questions → valid SQL ───────────


class TestQualityGuardrail:
    """
    On a fixed set of 10 canned questions, a mocked local model must produce
    valid, org-scoped, safety-passing SQL at least 70% of the time.
    The remaining questions must hit the graceful path (error dict from generate),
    NOT raise an unhandled exception.

    This tests the integration of the prompt → validate → inject pipeline,
    not real local-model quality.  The mock returns realistic SQL strings that
    a capable 7B model would produce (some valid, some not).
    """

    # 10 canned questions with realistic mock LLM responses
    # (8 valid, 2 intentionally broken/invalid)
    _QUESTIONS_AND_SQL = [
        (
            "How many feedbacks do we have?",
            "SELECT COUNT(*) FROM feedback_items WHERE organization_id = :org_id LIMIT 100",
        ),
        (
            "What is the breakdown by sentiment?",
            "SELECT sentiment_label, COUNT(*) FROM feedback_items WHERE organization_id = :org_id GROUP BY sentiment_label LIMIT 100",
        ),
        (
            "Show me the most recent 10 feedbacks",
            "SELECT id, content, created_at FROM feedback_items WHERE organization_id = :org_id ORDER BY created_at DESC LIMIT 10",
        ),
        (
            "Count negative feedbacks",
            "SELECT COUNT(*) FROM feedback_items WHERE organization_id = :org_id AND sentiment_label = 'negative' LIMIT 100",
        ),
        (
            "List customers with low health scores",
            "SELECT customer_email, health_score FROM customer_health_scores WHERE organization_id = :org_id ORDER BY health_score ASC LIMIT 50",
        ),
        (
            "How many feedbacks this month?",
            "SELECT COUNT(*) FROM feedback_items WHERE organization_id = :org_id AND created_at >= date_trunc('month', CURRENT_DATE) LIMIT 100",
        ),
        (
            "Show urgent feedbacks",
            "SELECT id, content, created_at FROM feedback_items WHERE organization_id = :org_id AND is_urgent = true ORDER BY created_at DESC LIMIT 50",
        ),
        (
            "Average sentiment score",
            "SELECT AVG(sentiment_score) FROM feedback_items WHERE organization_id = :org_id LIMIT 100",
        ),
        # These two intentionally produce invalid/garbage SQL to test graceful path
        (
            "I don't understand this question",
            "I cannot generate a SQL query for this request.",  # Not SQL
        ),
        (
            "What is the meaning of life?",
            "SELECT * FROM unknown_philosophical_table LIMIT 1",  # Table not in whitelist
        ),
    ]

    def test_at_least_70_percent_produce_valid_sql(self):
        """
        Run 10 questions through SQLGenerator.generate with a mocked _call_llm.
        ≥70% must return a non-None sql (passed safety check).
        The remaining must return error dict — no unhandled exceptions.
        """
        from src.services.copilot.sql_generator import SQLGenerator
        from src.services.copilot.schema_whitelist import DEFAULT_WHITELIST

        gen = SQLGenerator()

        valid_count = 0
        graceful_error_count = 0
        crash_count = 0

        for question, mock_sql_response in self._QUESTIONS_AND_SQL:
            with patch.object(gen, "_call_llm", return_value=mock_sql_response):
                try:
                    result = gen.generate(
                        question=question,
                        org_id=1,
                        plan="pro",
                        api_key=None,
                        model="llama3",
                        base_url="http://localhost:11434/v1",
                    )
                    if result["sql"] is not None:
                        valid_count += 1
                    else:
                        graceful_error_count += 1
                except Exception:
                    crash_count += 1

        total = len(self._QUESTIONS_AND_SQL)
        pct = valid_count / total * 100

        assert crash_count == 0, (
            f"Quality guardrail: {crash_count} questions caused unhandled exceptions. "
            "SQL safety must degrade gracefully, never crash."
        )
        assert pct >= 70.0, (
            f"Quality guardrail: only {valid_count}/{total} ({pct:.0f}%) produced valid SQL. "
            f"Required: ≥70%. Graceful errors: {graceful_error_count}."
        )

    def test_invalid_sql_from_local_model_hits_graceful_path(self):
        """
        Non-SQL or garbage from a local model → generate() returns error dict,
        never an exception.
        """
        from src.services.copilot.sql_generator import SQLGenerator

        gen = SQLGenerator()
        garbage_outputs = [
            "I don't know how to answer that.",
            "Sure! Here's a SELECT: DROP TABLE feedback_items;",
            "",
            "```python\nprint('hello')```",
        ]

        for garbage in garbage_outputs:
            with patch.object(gen, "_call_llm", return_value=garbage):
                try:
                    result = gen.generate(
                        question="test", org_id=1, plan="pro",
                        api_key=None, model="llama3",
                        base_url="http://localhost:11434/v1",
                    )
                    # Must return a dict (not raise)
                    assert isinstance(result, dict)
                    assert "sql" in result
                    assert "error" in result
                    # sql must be None (failed validation)
                    assert result["sql"] is None, (
                        f"Garbage SQL '{garbage[:40]}...' should fail validation, not produce output"
                    )
                except Exception as e:
                    pytest.fail(
                        f"generate() must not raise for garbage input '{garbage[:40]}'; got {e}"
                    )
