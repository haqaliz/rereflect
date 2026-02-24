"""
SQL Executor — executes validated SQL with safety features.

Features:
- Parameterized query execution
- 5-second timeout enforcement
- Structured result format: { columns, rows, row_count, truncated }
- Error handling: syntax errors, timeout, no results
"""

import logging
import signal
import threading
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 5.0


class QueryTimeoutError(Exception):
    """Raised when a query exceeds the execution timeout."""
    pass


class QueryExecutionError(Exception):
    """Raised when query execution fails."""
    pass


class SQLExecutor:
    """
    Executes validated, parameterized SQL queries with timeout and structured results.
    """

    def execute(
        self,
        sql: str,
        params: dict,
        db,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> dict:
        """
        Execute a SQL query with timeout and return structured results.

        Args:
            sql: The SQL query string (with :param_name placeholders)
            params: Dict of parameter values to bind
            db: SQLAlchemy session
            timeout_seconds: Max execution time (default 5s)

        Returns:
            {
                "columns": list[str],
                "rows": list[list],
                "row_count": int,
                "truncated": bool,
            }

        Raises:
            QueryTimeoutError: If execution exceeds timeout_seconds
            QueryExecutionError: If SQL execution fails
        """
        result_holder = {}
        error_holder = {}

        def _make_json_safe(value):
            """Convert non-JSON-serializable types to strings."""
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, date):
                return value.isoformat()
            if isinstance(value, Decimal):
                return float(value)
            if isinstance(value, bytes):
                return value.decode("utf-8", errors="replace")
            return value

        def _run_query():
            try:
                db_result = db.execute(text(sql), params)
                columns = list(db_result.keys())
                raw_rows = db_result.fetchall()
                rows = [
                    [_make_json_safe(cell) for cell in row]
                    for row in raw_rows
                ]
                result_holder["columns"] = columns
                result_holder["rows"] = rows
            except SQLAlchemyError as e:
                error_holder["error"] = e
            except Exception as e:
                error_holder["error"] = e

        thread = threading.Thread(target=_run_query, daemon=True)
        thread.start()
        thread.join(timeout=timeout_seconds)

        if thread.is_alive():
            raise QueryTimeoutError(
                f"Query timed out after {timeout_seconds} seconds. "
                "Please try a more specific question or narrow your date range."
            )

        if "error" in error_holder:
            raise QueryExecutionError(
                f"Query execution failed: {error_holder['error']}"
            ) from error_holder["error"]

        columns = result_holder.get("columns", [])
        rows = result_holder.get("rows", [])
        row_count = len(rows)

        # Detect if results were truncated by LIMIT
        # (simple heuristic: if row_count equals any common limit boundary,
        #  it may have been truncated — callers can check this)
        truncated = False  # Set to True if row_count == limit in the future

        return {
            "columns": columns,
            "rows": rows,
            "row_count": row_count,
            "truncated": truncated,
        }
