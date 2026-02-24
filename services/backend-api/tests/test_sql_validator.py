"""
TDD tests for SQL Validator — safety guardrails (RED → GREEN → REFACTOR).

Every guardrail from PRD §5.3 is tested individually:
- Read-only enforcement
- Schema whitelist
- Join limit
- No subqueries
- Org scope injection
- Row limit injection
- Parameter validation
"""

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def validator():
    from src.services.copilot.sql_validator import SQLValidator
    return SQLValidator()


@pytest.fixture
def sample_whitelist():
    return {
        "feedback_items": ["id", "organization_id", "text", "sentiment_label", "is_urgent", "created_at", "pain_point_category", "feature_request_category"],
        "customer_health_scores": ["id", "organization_id", "customer_email", "health_score", "risk_level", "feedback_count"],
        "anomaly_events": ["id", "organization_id", "detected_at", "anomaly_type"],
    }


# ── READ-ONLY ENFORCEMENT ─────────────────────────────────────────────────────

class TestReadOnlyEnforcement:
    """Only SELECT statements are allowed."""

    @pytest.mark.parametrize("dangerous_sql", [
        "INSERT INTO feedback_items (text) VALUES ('hack')",
        "UPDATE feedback_items SET text = 'hacked'",
        "DELETE FROM feedback_items WHERE id = 1",
        "DROP TABLE feedback_items",
        "ALTER TABLE feedback_items ADD COLUMN hack TEXT",
        "TRUNCATE TABLE feedback_items",
        "GRANT ALL ON feedback_items TO hacker",
        "REVOKE SELECT ON feedback_items FROM user",
        "CREATE TABLE evil_table (id INT)",
        "EXEC sp_executesql N'DROP TABLE users'",
    ])
    def test_rejects_write_operations(self, validator, dangerous_sql):
        result = validator.validate_readonly(dangerous_sql)
        assert result.is_valid is False, f"Expected rejection of: {dangerous_sql!r}"
        assert result.error is not None

    @pytest.mark.parametrize("safe_sql", [
        "SELECT * FROM feedback_items",
        "SELECT id, text FROM feedback_items WHERE organization_id = 1",
        "SELECT COUNT(*) FROM feedback_items GROUP BY sentiment_label",
        "SELECT f.id, c.health_score FROM feedback_items f JOIN customer_health_scores c ON f.customer_email = c.customer_email",
    ])
    def test_allows_select_statements(self, validator, safe_sql):
        result = validator.validate_readonly(safe_sql)
        assert result.is_valid is True, f"Expected to allow: {safe_sql!r}, got error: {result.error}"

    def test_rejects_insert_disguised_in_select(self, validator):
        """Ensure INSERT embedded via tricks is rejected."""
        sql = "SELECT 1; INSERT INTO users VALUES (1, 'hacked')"
        result = validator.validate_readonly(sql)
        assert result.is_valid is False

    def test_rejects_delete_with_leading_whitespace(self, validator):
        sql = "   DELETE FROM feedback_items"
        result = validator.validate_readonly(sql)
        assert result.is_valid is False

    def test_rejects_case_insensitive_write(self, validator):
        sql = "delete from feedback_items where id = 1"
        result = validator.validate_readonly(sql)
        assert result.is_valid is False


# ── SCHEMA WHITELIST ──────────────────────────────────────────────────────────

class TestSchemaWhitelist:
    """Only whitelisted tables/columns are allowed."""

    def test_allows_whitelisted_table(self, validator, sample_whitelist):
        sql = "SELECT id, text FROM feedback_items"
        result = validator.validate_schema_whitelist(sql, sample_whitelist)
        assert result.is_valid is True

    def test_rejects_non_whitelisted_table(self, validator, sample_whitelist):
        sql = "SELECT * FROM users"
        result = validator.validate_schema_whitelist(sql, sample_whitelist)
        assert result.is_valid is False
        assert "users" in result.error.lower()

    def test_rejects_subscriptions_table(self, validator, sample_whitelist):
        sql = "SELECT * FROM subscriptions"
        result = validator.validate_schema_whitelist(sql, sample_whitelist)
        assert result.is_valid is False

    def test_rejects_org_api_keys_table(self, validator, sample_whitelist):
        sql = "SELECT encrypted_key FROM org_api_keys"
        result = validator.validate_schema_whitelist(sql, sample_whitelist)
        assert result.is_valid is False

    def test_rejects_sessions_table(self, validator, sample_whitelist):
        sql = "SELECT * FROM sessions"
        result = validator.validate_schema_whitelist(sql, sample_whitelist)
        assert result.is_valid is False

    def test_allows_multiple_whitelisted_tables_in_join(self, validator, sample_whitelist):
        sql = "SELECT f.id FROM feedback_items f JOIN customer_health_scores c ON f.organization_id = c.organization_id"
        result = validator.validate_schema_whitelist(sql, sample_whitelist)
        assert result.is_valid is True

    def test_rejects_join_with_non_whitelisted_table(self, validator, sample_whitelist):
        sql = "SELECT f.id FROM feedback_items f JOIN users u ON f.organization_id = u.organization_id"
        result = validator.validate_schema_whitelist(sql, sample_whitelist)
        assert result.is_valid is False


# ── JOIN LIMIT ────────────────────────────────────────────────────────────────

class TestJoinLimit:
    """Maximum 3 JOINs are allowed per query."""

    def test_allows_zero_joins(self, validator):
        sql = "SELECT * FROM feedback_items"
        result = validator.validate_join_limit(sql, max_joins=3)
        assert result.is_valid is True

    def test_allows_one_join(self, validator):
        sql = "SELECT * FROM feedback_items f JOIN customer_health_scores c ON f.customer_email = c.customer_email"
        result = validator.validate_join_limit(sql, max_joins=3)
        assert result.is_valid is True

    def test_allows_two_joins(self, validator):
        sql = """
            SELECT * FROM feedback_items f
            JOIN customer_health_scores c ON f.customer_email = c.customer_email
            JOIN anomaly_events a ON f.organization_id = a.organization_id
        """
        result = validator.validate_join_limit(sql, max_joins=3)
        assert result.is_valid is True

    def test_allows_exactly_three_joins(self, validator):
        sql = """
            SELECT * FROM feedback_items f
            JOIN customer_health_scores c ON f.customer_email = c.customer_email
            JOIN anomaly_events a ON f.organization_id = a.organization_id
            JOIN customer_health_scores c2 ON f.organization_id = c2.organization_id
        """
        result = validator.validate_join_limit(sql, max_joins=3)
        assert result.is_valid is True

    def test_rejects_four_joins(self, validator):
        sql = """
            SELECT * FROM feedback_items f
            JOIN customer_health_scores c1 ON f.organization_id = c1.organization_id
            JOIN customer_health_scores c2 ON f.organization_id = c2.organization_id
            JOIN anomaly_events a ON f.organization_id = a.organization_id
            JOIN customer_health_scores c3 ON f.organization_id = c3.organization_id
        """
        result = validator.validate_join_limit(sql, max_joins=3)
        assert result.is_valid is False
        assert "join" in result.error.lower()

    def test_join_limit_is_configurable(self, validator):
        sql = "SELECT * FROM feedback_items f JOIN customer_health_scores c ON f.organization_id = c.organization_id"
        result_1 = validator.validate_join_limit(sql, max_joins=0)
        result_2 = validator.validate_join_limit(sql, max_joins=1)
        assert result_1.is_valid is False
        assert result_2.is_valid is True


# ── NO SUBQUERIES ─────────────────────────────────────────────────────────────

class TestNoSubqueries:
    """Nested SELECT statements are not allowed."""

    def test_allows_simple_select(self, validator):
        sql = "SELECT * FROM feedback_items WHERE organization_id = 1"
        result = validator.validate_no_subqueries(sql)
        assert result.is_valid is True

    def test_rejects_subquery_in_where(self, validator):
        sql = "SELECT * FROM feedback_items WHERE id IN (SELECT id FROM feedback_items WHERE is_urgent = true)"
        result = validator.validate_no_subqueries(sql)
        assert result.is_valid is False
        assert "subquery" in result.error.lower()

    def test_rejects_subquery_in_from(self, validator):
        sql = "SELECT * FROM (SELECT id FROM feedback_items) AS sub"
        result = validator.validate_no_subqueries(sql)
        assert result.is_valid is False

    def test_rejects_correlated_subquery(self, validator):
        sql = "SELECT * FROM feedback_items f WHERE EXISTS (SELECT 1 FROM customer_health_scores c WHERE c.customer_email = f.customer_email)"
        result = validator.validate_no_subqueries(sql)
        assert result.is_valid is False

    def test_allows_select_with_group_by(self, validator):
        sql = "SELECT sentiment_label, COUNT(*) FROM feedback_items GROUP BY sentiment_label"
        result = validator.validate_no_subqueries(sql)
        assert result.is_valid is True


# ── ORG SCOPE INJECTION ───────────────────────────────────────────────────────

class TestOrgScopeInjection:
    """organization_id must be injected into every query."""

    def test_injects_org_id_where_clause(self, validator):
        sql = "SELECT * FROM feedback_items"
        result_sql = validator.inject_org_scope(sql, org_id=42)
        assert ":org_id" in result_sql or "42" in result_sql or "organization_id" in result_sql.lower()

    def test_org_id_appears_in_where(self, validator):
        sql = "SELECT * FROM feedback_items"
        result_sql = validator.inject_org_scope(sql, org_id=42)
        assert "organization_id" in result_sql.lower()

    def test_preserves_existing_where_clause(self, validator):
        sql = "SELECT * FROM feedback_items WHERE sentiment_label = 'negative'"
        result_sql = validator.inject_org_scope(sql, org_id=42)
        assert "sentiment_label" in result_sql
        assert "organization_id" in result_sql.lower()

    def test_org_id_uses_parameter_not_literal(self, validator):
        """Org ID should be parameterized, not interpolated as a literal."""
        sql = "SELECT * FROM feedback_items"
        result_sql = validator.inject_org_scope(sql, org_id=42)
        # Should use :org_id parameter placeholder, not raw int
        assert ":org_id" in result_sql

    def test_existing_org_id_filter_not_duplicated(self, validator):
        """If org_id is already in WHERE, don't add it twice."""
        sql = "SELECT * FROM feedback_items WHERE organization_id = :org_id"
        result_sql = validator.inject_org_scope(sql, org_id=42)
        # Should not have double organization_id clauses
        count = result_sql.lower().count("organization_id")
        assert count == 1


# ── ROW LIMIT INJECTION ───────────────────────────────────────────────────────

class TestRowLimitInjection:
    """Row limits are enforced based on query type and plan tier."""

    def test_enforces_limit_on_simple_select(self, validator):
        sql = "SELECT * FROM feedback_items WHERE organization_id = :org_id"
        result_sql = validator.inject_row_limit(sql, query_type="detail", plan="free")
        assert "LIMIT" in result_sql.upper()

    def test_free_plan_detail_limit_is_50(self, validator):
        sql = "SELECT id, text FROM feedback_items WHERE organization_id = :org_id"
        result_sql = validator.inject_row_limit(sql, query_type="detail", plan="free")
        assert "50" in result_sql

    def test_pro_plan_detail_limit_is_250(self, validator):
        sql = "SELECT id, text FROM feedback_items WHERE organization_id = :org_id"
        result_sql = validator.inject_row_limit(sql, query_type="detail", plan="pro")
        assert "250" in result_sql

    def test_business_plan_detail_limit_is_1250(self, validator):
        sql = "SELECT id, text FROM feedback_items WHERE organization_id = :org_id"
        result_sql = validator.inject_row_limit(sql, query_type="detail", plan="business")
        assert "1250" in result_sql

    def test_enterprise_plan_detail_limit_is_5000(self, validator):
        sql = "SELECT id, text FROM feedback_items WHERE organization_id = :org_id"
        result_sql = validator.inject_row_limit(sql, query_type="detail", plan="enterprise")
        assert "5000" in result_sql

    def test_free_plan_aggregation_limit_is_100(self, validator):
        sql = "SELECT sentiment_label, COUNT(*) FROM feedback_items GROUP BY sentiment_label"
        result_sql = validator.inject_row_limit(sql, query_type="aggregation", plan="free")
        assert "100" in result_sql

    def test_free_plan_export_limit_is_25(self, validator):
        sql = "SELECT * FROM feedback_items WHERE organization_id = :org_id"
        result_sql = validator.inject_row_limit(sql, query_type="export", plan="free")
        assert "25" in result_sql

    def test_existing_limit_is_capped_at_plan_max(self, validator):
        """If user requests higher LIMIT, cap it at plan ceiling."""
        sql = "SELECT * FROM feedback_items WHERE organization_id = :org_id LIMIT 10000"
        result_sql = validator.inject_row_limit(sql, query_type="detail", plan="free", user_requested_limit=10000)
        # Free plan max for detail is 50
        assert "50" in result_sql
        assert "10000" not in result_sql

    def test_user_can_request_lower_limit_than_plan_max(self, validator):
        """User can request a limit below the plan max."""
        sql = "SELECT * FROM feedback_items WHERE organization_id = :org_id"
        result_sql = validator.inject_row_limit(sql, query_type="detail", plan="pro", user_requested_limit=10)
        assert "10" in result_sql


# ── QUERY TYPE DETECTION ──────────────────────────────────────────────────────

class TestQueryTypeDetection:
    """Detect query type from SQL structure."""

    def test_detects_aggregation_query(self, validator):
        sql = "SELECT sentiment_label, COUNT(*) FROM feedback_items GROUP BY sentiment_label"
        qtype = validator.detect_query_type(sql)
        assert qtype == "aggregation"

    def test_detects_aggregation_with_sum(self, validator):
        sql = "SELECT SUM(health_score) FROM customer_health_scores"
        qtype = validator.detect_query_type(sql)
        assert qtype == "aggregation"

    def test_detects_aggregation_with_avg(self, validator):
        sql = "SELECT AVG(health_score) FROM customer_health_scores"
        qtype = validator.detect_query_type(sql)
        assert qtype == "aggregation"

    def test_detects_export_query_select_star(self, validator):
        sql = "SELECT * FROM feedback_items WHERE organization_id = :org_id"
        qtype = validator.detect_query_type(sql)
        assert qtype == "export"

    def test_detects_detail_query_with_columns(self, validator):
        sql = "SELECT id, text, sentiment_label FROM feedback_items WHERE organization_id = :org_id"
        qtype = validator.detect_query_type(sql)
        assert qtype == "detail"


# ── FULL VALIDATION PIPELINE ──────────────────────────────────────────────────

class TestFullValidationPipeline:
    """Test the combined validate() method that runs all guardrails."""

    def test_valid_query_passes_all_guardrails(self, validator, sample_whitelist):
        sql = "SELECT id, text, sentiment_label FROM feedback_items WHERE organization_id = :org_id LIMIT 50"
        result = validator.validate(sql, org_id=1, plan="free", whitelist=sample_whitelist)
        assert result.is_valid is True

    def test_write_query_fails_pipeline(self, validator, sample_whitelist):
        sql = "DELETE FROM feedback_items WHERE id = 1"
        result = validator.validate(sql, org_id=1, plan="free", whitelist=sample_whitelist)
        assert result.is_valid is False

    def test_non_whitelisted_table_fails_pipeline(self, validator, sample_whitelist):
        sql = "SELECT * FROM users WHERE organization_id = :org_id"
        result = validator.validate(sql, org_id=1, plan="free", whitelist=sample_whitelist)
        assert result.is_valid is False

    def test_subquery_fails_pipeline(self, validator, sample_whitelist):
        sql = "SELECT * FROM feedback_items WHERE id IN (SELECT id FROM feedback_items WHERE is_urgent = true)"
        result = validator.validate(sql, org_id=1, plan="free", whitelist=sample_whitelist)
        assert result.is_valid is False

    def test_validation_result_has_error_message_on_failure(self, validator, sample_whitelist):
        sql = "DELETE FROM feedback_items"
        result = validator.validate(sql, org_id=1, plan="free", whitelist=sample_whitelist)
        assert result.error is not None
        assert len(result.error) > 0
