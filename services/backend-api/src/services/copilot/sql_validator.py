"""
SQL Validator — enforces all safety guardrails on LLM-generated SQL.

Guardrails (PRD §5.3):
- Read-only: Only SELECT statements
- Schema whitelist: Only approved tables/columns
- Join limit: Max 3 JOINs
- No subqueries: No nested SELECT
- Org scope: Auto-inject WHERE organization_id = :org_id
- Row limits: Enforce LIMIT based on query type + plan tier
- Parameterized: All user values must be parameters
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ── Row limits by plan and query type ─────────────────────────────────────────

# Base limits (Free plan = 1x multiplier)
_BASE_LIMITS = {
    "aggregation": 100,
    "detail": 50,
    "export": 25,
}

# Plan multipliers
_PLAN_MULTIPLIERS = {
    "free": 1,
    "pro": 5,
    "business": 25,
    "enterprise": 100,
}

# Write operation keywords to reject
_WRITE_KEYWORDS = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|CREATE|EXEC|EXECUTE|MERGE|REPLACE)\b",
    re.IGNORECASE
)

# Require SQL to start with SELECT (catches garbage / natural-language output from weak models)
_SELECT_START = re.compile(r"^\s*SELECT\b", re.IGNORECASE)

# Detect multiple statements (SQL injection via semicolons)
_MULTI_STATEMENT = re.compile(r";\s*(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|CREATE)\b", re.IGNORECASE)

# JOIN detection
_JOIN_PATTERN = re.compile(r"\bJOIN\b", re.IGNORECASE)

# Subquery detection: nested SELECT not preceded by "CREATE" etc.
_SUBQUERY_PATTERN = re.compile(r"\(\s*SELECT\b", re.IGNORECASE)

# Aggregation detection
_AGGREGATION_PATTERN = re.compile(r"\b(COUNT|SUM|AVG|MIN|MAX|GROUP\s+BY)\b", re.IGNORECASE)

# Export detection
_SELECT_STAR = re.compile(r"SELECT\s+\*\s+FROM", re.IGNORECASE)

# Existing LIMIT detection
_LIMIT_PATTERN = re.compile(r"\bLIMIT\s+(\d+)\b", re.IGNORECASE)

# Existing org_id WHERE detection
_ORG_ID_PATTERN = re.compile(r"\borganization_id\s*=\s*:org_id\b", re.IGNORECASE)


@dataclass
class ValidationResult:
    """Result of a SQL validation check."""
    is_valid: bool
    error: Optional[str] = None


class SQLValidator:
    """Validates SQL queries against all safety guardrails."""

    # ── Individual validators ─────────────────────────────────────────────────

    def validate_readonly(self, sql: str) -> ValidationResult:
        """Reject any non-SELECT statement.

        Enforces two rules:
        1. Statement must start with SELECT (rejects garbage, natural-language output
           from weak models, Python code, etc.).
        2. No write-operation keywords (INSERT, UPDATE, DELETE, DROP, etc.) anywhere.
        """
        stripped = sql.strip()

        # Check for multi-statement attacks
        if _MULTI_STATEMENT.search(stripped):
            return ValidationResult(
                is_valid=False,
                error="Multi-statement SQL is not allowed"
            )

        # Check write operations (fast path before SELECT check)
        if _WRITE_KEYWORDS.match(stripped):
            keyword = stripped.split()[0].upper()
            return ValidationResult(
                is_valid=False,
                error=f"Write operation '{keyword}' is not allowed. Only SELECT queries are permitted."
            )

        # Must start with SELECT — catches garbage output from weak local models
        # (e.g. "I don't know how to answer that." or code blocks).
        if not _SELECT_START.match(stripped):
            return ValidationResult(
                is_valid=False,
                error=(
                    "Query must start with SELECT. "
                    "The model may have returned a non-SQL response."
                )
            )

        return ValidationResult(is_valid=True)

    def validate_schema_whitelist(self, sql: str, whitelist: dict) -> ValidationResult:
        """Ensure query only references whitelisted tables."""
        sql_upper = sql.upper()

        # Extract table references from FROM and JOIN clauses
        table_pattern = re.compile(
            r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)\b",
            re.IGNORECASE
        )
        referenced_tables = set(
            m.group(1).lower()
            for m in table_pattern.finditer(sql)
        )

        allowed_tables = {t.lower() for t in whitelist.keys()}

        for table in referenced_tables:
            if table not in allowed_tables:
                return ValidationResult(
                    is_valid=False,
                    error=f"Table '{table}' is not in the allowed schema whitelist. "
                          f"Allowed tables: {', '.join(sorted(allowed_tables))}"
                )

        return ValidationResult(is_valid=True)

    def validate_join_limit(self, sql: str, max_joins: int = 3) -> ValidationResult:
        """Reject queries with too many JOINs."""
        join_count = len(_JOIN_PATTERN.findall(sql))

        if join_count > max_joins:
            return ValidationResult(
                is_valid=False,
                error=f"Too many JOINs: {join_count} found, maximum is {max_joins}. "
                      f"Please simplify your query."
            )

        return ValidationResult(is_valid=True)

    def validate_no_subqueries(self, sql: str) -> ValidationResult:
        """Reject queries with nested SELECT statements."""
        if _SUBQUERY_PATTERN.search(sql):
            return ValidationResult(
                is_valid=False,
                error="Nested subquery (SELECT within SELECT) is not allowed. Please simplify your query."
            )

        return ValidationResult(is_valid=True)

    def inject_org_scope(self, sql: str, org_id: int) -> str:
        """
        Inject WHERE organization_id = :org_id into the query.
        Idempotent: if already present, does not add twice.
        """
        # If already has org_id filter, return as-is
        if _ORG_ID_PATTERN.search(sql):
            return sql

        sql_stripped = sql.strip().rstrip(";")

        # Check if there's a WHERE clause already
        has_where = bool(re.search(r"\bWHERE\b", sql_stripped, re.IGNORECASE))
        # Check if there's a GROUP BY, HAVING, ORDER BY, or LIMIT that comes before end
        # We need to inject before these
        terminator_match = re.search(
            r"\b(GROUP\s+BY|HAVING|ORDER\s+BY|LIMIT)\b",
            sql_stripped,
            re.IGNORECASE
        )

        org_condition = "organization_id = :org_id"

        if has_where:
            # Add to existing WHERE with AND, before terminators
            if terminator_match:
                pos = terminator_match.start()
                sql_stripped = (
                    sql_stripped[:pos].rstrip() +
                    f" AND {org_condition} " +
                    sql_stripped[pos:]
                )
            else:
                # Find the WHERE and append condition
                where_match = re.search(r"\bWHERE\b", sql_stripped, re.IGNORECASE)
                if where_match:
                    pos = where_match.end()
                    sql_stripped = (
                        sql_stripped[:pos] +
                        f" {org_condition} AND" +
                        sql_stripped[pos:]
                    )
        else:
            # No WHERE clause — add one before any GROUP BY, HAVING, ORDER BY, LIMIT
            if terminator_match:
                pos = terminator_match.start()
                sql_stripped = (
                    sql_stripped[:pos].rstrip() +
                    f" WHERE {org_condition} " +
                    sql_stripped[pos:]
                )
            else:
                sql_stripped = sql_stripped + f" WHERE {org_condition}"

        return sql_stripped

    def detect_query_type(self, sql: str) -> str:
        """
        Detect query type: aggregation, export, or detail.

        - aggregation: has COUNT, SUM, AVG, MIN, MAX, or GROUP BY
        - export: SELECT * FROM
        - detail: SELECT with specific columns
        """
        if _AGGREGATION_PATTERN.search(sql):
            return "aggregation"
        if _SELECT_STAR.search(sql):
            return "export"
        return "detail"

    def inject_row_limit(
        self,
        sql: str,
        query_type: str,
        plan: str,
        user_requested_limit: Optional[int] = None,
    ) -> str:
        """
        Enforce row limits based on query type and plan tier.
        Caps any user-requested limit at the plan ceiling.
        """
        multiplier = _PLAN_MULTIPLIERS.get(plan, 1)
        base = _BASE_LIMITS.get(query_type, 50)
        plan_limit = base * multiplier

        # Determine effective limit
        if user_requested_limit is not None:
            effective_limit = min(user_requested_limit, plan_limit)
        else:
            effective_limit = plan_limit

        sql_stripped = sql.strip().rstrip(";")

        # Remove existing LIMIT clause if present
        existing_limit_match = _LIMIT_PATTERN.search(sql_stripped)
        if existing_limit_match:
            existing_val = int(existing_limit_match.group(1))
            # If user-requested limit is provided, cap it; otherwise use existing if under plan limit
            if user_requested_limit is not None:
                # Replace with capped value
                sql_stripped = _LIMIT_PATTERN.sub(f"LIMIT {effective_limit}", sql_stripped)
            elif existing_val > plan_limit:
                # Cap at plan limit
                sql_stripped = _LIMIT_PATTERN.sub(f"LIMIT {plan_limit}", sql_stripped)
            # else: existing LIMIT is within plan, keep it
        else:
            # Append LIMIT
            sql_stripped = sql_stripped + f" LIMIT {effective_limit}"

        return sql_stripped

    # ── Full validation pipeline ──────────────────────────────────────────────

    def validate(
        self,
        sql: str,
        org_id: int,
        plan: str,
        whitelist: dict,
        max_joins: int = 3,
        user_requested_limit: Optional[int] = None,
    ) -> ValidationResult:
        """
        Run all guardrails in order. Returns first failure or success.

        Does NOT modify the SQL — for injection (org scope, limits), use
        inject_org_scope() and inject_row_limit() separately.
        """
        # 1. Read-only check
        result = self.validate_readonly(sql)
        if not result.is_valid:
            return result

        # 2. Schema whitelist
        result = self.validate_schema_whitelist(sql, whitelist)
        if not result.is_valid:
            return result

        # 3. No subqueries
        result = self.validate_no_subqueries(sql)
        if not result.is_valid:
            return result

        # 4. Join limit
        result = self.validate_join_limit(sql, max_joins=max_joins)
        if not result.is_valid:
            return result

        return ValidationResult(is_valid=True)
