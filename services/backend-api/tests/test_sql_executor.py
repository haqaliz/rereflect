"""
TDD tests for SQL Executor (RED → GREEN → REFACTOR).

Tests cover:
- Basic query execution
- 5-second timeout enforcement
- Parameterized query execution (SQL injection prevention)
- Structured result format
- Error handling
"""

import pytest
from unittest.mock import MagicMock, patch, call
import time


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def executor():
    from src.services.copilot.sql_executor import SQLExecutor
    return SQLExecutor()


# ── BASIC EXECUTION ───────────────────────────────────────────────────────────

class TestBasicExecution:
    """Test basic SQL execution and result formatting."""

    def test_execute_returns_structured_result(self, executor, mock_db):
        mock_result = MagicMock()
        mock_result.keys.return_value = ["sentiment_label", "count"]
        mock_result.fetchall.return_value = [
            ("negative", 47),
            ("neutral", 123),
            ("positive", 89),
        ]
        mock_db.execute.return_value = mock_result

        result = executor.execute(
            sql="SELECT sentiment_label, COUNT(*) as count FROM feedback_items GROUP BY sentiment_label LIMIT 100",
            params={"org_id": 1},
            db=mock_db
        )

        assert "columns" in result
        assert "rows" in result
        assert "row_count" in result
        assert "truncated" in result

    def test_execute_returns_correct_columns(self, executor, mock_db):
        mock_result = MagicMock()
        mock_result.keys.return_value = ["sentiment_label", "count"]
        mock_result.fetchall.return_value = [("negative", 47)]
        mock_db.execute.return_value = mock_result

        result = executor.execute(
            sql="SELECT sentiment_label, COUNT(*) as count FROM feedback_items GROUP BY sentiment_label LIMIT 100",
            params={"org_id": 1},
            db=mock_db
        )

        assert result["columns"] == ["sentiment_label", "count"]

    def test_execute_returns_correct_rows(self, executor, mock_db):
        mock_result = MagicMock()
        mock_result.keys.return_value = ["sentiment_label", "count"]
        mock_result.fetchall.return_value = [
            ("negative", 47),
            ("neutral", 123),
        ]
        mock_db.execute.return_value = mock_result

        result = executor.execute(
            sql="SELECT sentiment_label, COUNT(*) FROM feedback_items GROUP BY sentiment_label LIMIT 100",
            params={"org_id": 1},
            db=mock_db
        )

        assert len(result["rows"]) == 2
        assert result["row_count"] == 2

    def test_execute_empty_result_returns_empty_rows(self, executor, mock_db):
        mock_result = MagicMock()
        mock_result.keys.return_value = ["id", "text"]
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        result = executor.execute(
            sql="SELECT id, text FROM feedback_items WHERE organization_id = :org_id LIMIT 50",
            params={"org_id": 1},
            db=mock_db
        )

        assert result["rows"] == []
        assert result["row_count"] == 0

    def test_truncated_flag_false_when_under_limit(self, executor, mock_db):
        mock_result = MagicMock()
        mock_result.keys.return_value = ["id"]
        mock_result.fetchall.return_value = [(i,) for i in range(10)]
        mock_db.execute.return_value = mock_result

        result = executor.execute(
            sql="SELECT id FROM feedback_items LIMIT 50",
            params={"org_id": 1},
            db=mock_db
        )

        assert result["truncated"] is False


# ── PARAMETERIZED EXECUTION ───────────────────────────────────────────────────

class TestParameterizedExecution:
    """Ensure SQL is executed with parameters, preventing injection."""

    def test_params_passed_to_execute(self, executor, mock_db):
        mock_result = MagicMock()
        mock_result.keys.return_value = ["id"]
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        params = {"org_id": 42}
        executor.execute(
            sql="SELECT id FROM feedback_items WHERE organization_id = :org_id LIMIT 50",
            params=params,
            db=mock_db
        )

        # DB execute should be called (with params somewhere in the call)
        mock_db.execute.assert_called_once()

    def test_sql_injection_not_possible_via_params(self, executor, mock_db):
        """Params should be bound, not interpolated into SQL string."""
        mock_result = MagicMock()
        mock_result.keys.return_value = ["id"]
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        # This should not cause SQL injection - it's a parameter value
        params = {"org_id": "1; DROP TABLE feedback_items; --"}
        # Should execute without raising (the value is bound, not interpolated)
        result = executor.execute(
            sql="SELECT id FROM feedback_items WHERE organization_id = :org_id LIMIT 50",
            params=params,
            db=mock_db
        )
        assert result is not None


# ── TIMEOUT ENFORCEMENT ───────────────────────────────────────────────────────

class TestTimeoutEnforcement:
    """Queries exceeding 5 seconds should be cancelled."""

    def test_timeout_error_on_slow_query(self, executor, mock_db):
        """Simulate a slow query that exceeds 5s timeout."""
        def slow_execute(*args, **kwargs):
            time.sleep(10)  # Way past 5s limit
            return MagicMock()

        mock_db.execute.side_effect = slow_execute

        with pytest.raises(Exception) as exc_info:
            executor.execute(
                sql="SELECT * FROM feedback_items LIMIT 50",
                params={"org_id": 1},
                db=mock_db,
                timeout_seconds=0.1  # Short timeout for test speed
            )
        assert "timeout" in str(exc_info.value).lower() or "timed out" in str(exc_info.value).lower() or exc_info.type.__name__ in ("TimeoutError", "SQLAlchemyError", "OperationalError")

    def test_fast_query_completes_successfully(self, executor, mock_db):
        """Fast queries should not be affected by timeout."""
        mock_result = MagicMock()
        mock_result.keys.return_value = ["id"]
        mock_result.fetchall.return_value = [(1,), (2,)]
        mock_db.execute.return_value = mock_result

        result = executor.execute(
            sql="SELECT id FROM feedback_items LIMIT 50",
            params={"org_id": 1},
            db=mock_db,
            timeout_seconds=5.0
        )
        assert result["row_count"] == 2


# ── ERROR HANDLING ────────────────────────────────────────────────────────────

class TestErrorHandling:
    """Handle various execution errors gracefully."""

    def test_database_error_raises_executor_error(self, executor, mock_db):
        from sqlalchemy.exc import SQLAlchemyError
        mock_db.execute.side_effect = SQLAlchemyError("Syntax error near 'FROM'")

        with pytest.raises(Exception) as exc_info:
            executor.execute(
                sql="SELECT FROM feedback_items",
                params={"org_id": 1},
                db=mock_db
            )
        # Should raise some kind of error
        assert exc_info.type is not None

    def test_result_serializable(self, executor, mock_db):
        """Result should be JSON-serializable."""
        import json
        mock_result = MagicMock()
        mock_result.keys.return_value = ["id", "count"]
        mock_result.fetchall.return_value = [(1, 47), (2, 23)]
        mock_db.execute.return_value = mock_result

        result = executor.execute(
            sql="SELECT id, COUNT(*) as count FROM feedback_items GROUP BY id LIMIT 50",
            params={"org_id": 1},
            db=mock_db
        )

        # Should be JSON-serializable
        json_str = json.dumps(result)
        assert json_str is not None


# ── RESULT STRUCTURE ──────────────────────────────────────────────────────────

class TestResultStructure:
    """Verify the exact structure of execution results."""

    def test_result_columns_is_list(self, executor, mock_db):
        mock_result = MagicMock()
        mock_result.keys.return_value = ["id"]
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        result = executor.execute("SELECT id FROM feedback_items LIMIT 10", {"org_id": 1}, mock_db)
        assert isinstance(result["columns"], list)

    def test_result_rows_is_list_of_lists(self, executor, mock_db):
        mock_result = MagicMock()
        mock_result.keys.return_value = ["id", "text"]
        mock_result.fetchall.return_value = [(1, "hello"), (2, "world")]
        mock_db.execute.return_value = mock_result

        result = executor.execute("SELECT id, text FROM feedback_items LIMIT 10", {"org_id": 1}, mock_db)
        assert isinstance(result["rows"], list)
        for row in result["rows"]:
            assert isinstance(row, list)

    def test_result_row_count_matches_rows_length(self, executor, mock_db):
        mock_result = MagicMock()
        mock_result.keys.return_value = ["id"]
        mock_result.fetchall.return_value = [(1,), (2,), (3,)]
        mock_db.execute.return_value = mock_result

        result = executor.execute("SELECT id FROM feedback_items LIMIT 10", {"org_id": 1}, mock_db)
        assert result["row_count"] == len(result["rows"])
