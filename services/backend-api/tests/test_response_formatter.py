"""
TDD tests for Copilot Response Formatter (M2.2 Task #7).

Tests cover:
- Table formatting from SQL results
- Chart type auto-detection
- Chart data format (Recharts-compatible)
- Deep link generation
- Markdown sanitization (XSS prevention)
- Empty results handling
- Large result truncation
"""

import pytest
from src.services.copilot.response_formatter import (
    format_table,
    format_chart,
    detect_chart_type,
    generate_deep_links,
    sanitize_markdown,
    format_response,
    ChartType,
)


# =============================================================================
# TABLE FORMATTER TESTS
# =============================================================================


class TestTableFormatter:
    def test_basic_table_formatting(self):
        """Format SQL result rows into table structure."""
        result = format_table(
            columns=["sentiment", "count"],
            rows=[["negative", 47], ["neutral", 123], ["positive", 89]],
        )
        assert result["data_type"] == "table"
        assert result["data"]["columns"] == ["sentiment", "count"]
        assert len(result["data"]["rows"]) == 3
        assert result["data"]["rows"][0] == ["negative", 47]

    def test_table_with_summary(self):
        """Table output includes a summary string."""
        result = format_table(
            columns=["sentiment", "count"],
            rows=[["negative", 47], ["positive", 89]],
        )
        assert "summary" in result["data"]
        assert isinstance(result["data"]["summary"], str)

    def test_empty_table(self):
        """Empty rows produce a valid empty table structure."""
        result = format_table(columns=["col1", "col2"], rows=[])
        assert result["data_type"] == "table"
        assert result["data"]["rows"] == []

    def test_table_with_many_columns(self):
        """Table with many columns is handled correctly."""
        columns = ["id", "text", "sentiment", "score", "category", "is_urgent", "created_at"]
        rows = [
            [1, "Test feedback", "negative", -0.8, "billing", True, "2026-01-15"],
            [2, "Another one", "positive", 0.9, "product", False, "2026-01-16"],
        ]
        result = format_table(columns=columns, rows=rows)
        assert len(result["data"]["columns"]) == 7
        assert len(result["data"]["rows"]) == 2

    def test_table_truncated_at_1000_rows(self):
        """Tables are truncated at 1000 rows to prevent client overload."""
        rows = [[i, f"value_{i}"] for i in range(2000)]
        result = format_table(columns=["id", "value"], rows=rows)
        assert len(result["data"]["rows"]) <= 1000
        assert result["data"].get("truncated") is True

    def test_table_none_values_handled(self):
        """None/null values in rows are preserved."""
        result = format_table(
            columns=["id", "category"],
            rows=[[1, None], [2, "billing"]],
        )
        assert result["data"]["rows"][0][1] is None


# =============================================================================
# CHART TYPE DETECTION TESTS
# =============================================================================


class TestChartTypeDetection:
    def test_categorical_numeric_detects_bar_chart(self):
        """1 categorical + 1 numeric column → bar chart."""
        chart_type = detect_chart_type(
            columns=["sentiment", "count"],
            rows=[["negative", 47], ["neutral", 123], ["positive", 89]],
        )
        assert chart_type == ChartType.BAR

    def test_date_numeric_detects_line_chart(self):
        """Date + numeric column → line chart."""
        chart_type = detect_chart_type(
            columns=["date", "count"],
            rows=[["2026-01-01", 10], ["2026-01-02", 15], ["2026-01-03", 8]],
        )
        assert chart_type == ChartType.LINE

    def test_percentage_breakdown_detects_pie_chart(self):
        """Percentage breakdown → pie chart."""
        chart_type = detect_chart_type(
            columns=["sentiment", "percentage"],
            rows=[["negative", 35.2], ["neutral", 40.1], ["positive", 24.7]],
        )
        assert chart_type == ChartType.PIE

    def test_many_columns_returns_none(self):
        """More than 2 columns → no chart suggestion."""
        chart_type = detect_chart_type(
            columns=["id", "text", "sentiment", "score"],
            rows=[[1, "test", "negative", -0.8]],
        )
        assert chart_type is None

    def test_single_row_returns_none(self):
        """Single row → no meaningful chart."""
        chart_type = detect_chart_type(
            columns=["sentiment", "count"],
            rows=[["negative", 47]],
        )
        assert chart_type is None

    def test_empty_rows_returns_none(self):
        chart_type = detect_chart_type(columns=["col1", "col2"], rows=[])
        assert chart_type is None


# =============================================================================
# CHART FORMATTER TESTS
# =============================================================================


class TestChartFormatter:
    def test_bar_chart_format(self):
        """Bar chart output is Recharts-compatible."""
        result = format_chart(
            chart_type=ChartType.BAR,
            columns=["sentiment", "count"],
            rows=[["negative", 47], ["neutral", 123], ["positive", 89]],
        )
        assert result["data_type"] == "chart"
        assert result["chart_type"] == "bar"
        # Recharts bar chart format
        assert "data" in result
        assert isinstance(result["data"], list)
        # Each entry should have the category key and value key
        first = result["data"][0]
        assert "sentiment" in first or "name" in first
        assert "count" in first or "value" in first

    def test_line_chart_format(self):
        """Line chart output is Recharts-compatible."""
        result = format_chart(
            chart_type=ChartType.LINE,
            columns=["date", "count"],
            rows=[["2026-01-01", 10], ["2026-01-02", 15], ["2026-01-03", 8]],
        )
        assert result["data_type"] == "chart"
        assert result["chart_type"] == "line"
        assert "data" in result
        assert len(result["data"]) == 3

    def test_pie_chart_format(self):
        """Pie chart output is Recharts-compatible."""
        result = format_chart(
            chart_type=ChartType.PIE,
            columns=["sentiment", "percentage"],
            rows=[["negative", 35.2], ["neutral", 40.1], ["positive", 24.7]],
        )
        assert result["data_type"] == "chart"
        assert result["chart_type"] == "pie"
        assert "data" in result
        # Recharts pie expects name + value
        for item in result["data"]:
            assert "name" in item
            assert "value" in item


# =============================================================================
# DEEP LINK GENERATOR TESTS
# =============================================================================


class TestDeepLinkGenerator:
    def test_customer_email_link(self):
        """Customer email references become clickable deep links."""
        text = "The customer john@example.com has high churn risk."
        result = generate_deep_links(text)
        assert "[john@example.com](/customers/john@example.com)" in result

    def test_feedback_id_link(self):
        """Feedback ID references become links to feedback detail page."""
        text = "See feedback #1234 for more details."
        result = generate_deep_links(text)
        assert "[#1234](/feedbacks/1234)" in result

    def test_pain_point_category_link(self):
        """Pain point category references become filtered page links."""
        text = "The 'billing' pain point category has 15 mentions."
        result = generate_deep_links(text)
        assert "/pain-points" in result

    def test_no_links_in_plain_text(self):
        """Text with no entity references is returned unchanged."""
        text = "There are 47 negative feedbacks this week."
        result = generate_deep_links(text)
        assert result == text

    def test_multiple_links_in_one_response(self):
        """Multiple entity references in one text are all linked."""
        text = "Customer john@example.com mentioned feedback #456 about billing."
        result = generate_deep_links(text)
        assert "john@example.com" in result
        assert "#456" in result or "456" in result


# =============================================================================
# MARKDOWN SANITIZATION TESTS
# =============================================================================


class TestMarkdownSanitizer:
    def test_removes_script_tags(self):
        """<script> tags are removed (XSS prevention)."""
        text = "Hello <script>alert('xss')</script> world"
        result = sanitize_markdown(text)
        assert "<script>" not in result
        assert "alert" not in result

    def test_removes_onclick_attributes(self):
        """onclick and other JS event attributes are removed."""
        text = '<a href="/safe" onclick="evil()">Link</a>'
        result = sanitize_markdown(text)
        assert "onclick" not in result

    def test_removes_javascript_urls(self):
        """javascript: URLs in links are removed."""
        text = "[Click me](javascript:alert('xss'))"
        result = sanitize_markdown(text)
        assert "javascript:" not in result

    def test_fixes_unclosed_code_block(self):
        """Unclosed code blocks are closed."""
        text = "Here is some code:\n```python\nx = 1\n"
        result = sanitize_markdown(text)
        assert result.count("```") % 2 == 0

    def test_valid_markdown_unchanged(self):
        """Valid markdown passes through unchanged (structure preserved)."""
        text = "# Header\n\n**Bold** and *italic*\n\n- Item 1\n- Item 2"
        result = sanitize_markdown(text)
        assert "# Header" in result
        assert "**Bold**" in result
        assert "- Item 1" in result

    def test_removes_iframe_tags(self):
        """<iframe> tags are stripped."""
        text = 'Check this: <iframe src="http://evil.com"></iframe>'
        result = sanitize_markdown(text)
        assert "<iframe" not in result


# =============================================================================
# FULL RESPONSE FORMATTER TESTS
# =============================================================================


class TestFormatResponse:
    def test_format_response_with_table_data(self):
        """format_response returns text + structured table when SQL results provided."""
        result = format_response(
            text="Here are the sentiment counts:",
            sql_columns=["sentiment", "count"],
            sql_rows=[["negative", 47], ["neutral", 123], ["positive", 89]],
        )
        assert "text" in result
        assert "structured_data" in result
        structured = result["structured_data"]
        assert any(s["data_type"] == "table" for s in structured)

    def test_format_response_with_chart_auto_detected(self):
        """format_response auto-detects chartable data and includes chart."""
        result = format_response(
            text="Sentiment breakdown:",
            sql_columns=["sentiment", "count"],
            sql_rows=[["negative", 47], ["neutral", 123], ["positive", 89]],
        )
        structured = result["structured_data"]
        types = [s["data_type"] for s in structured]
        assert "chart" in types  # Chart should be auto-detected

    def test_format_response_text_only(self):
        """When no SQL results, only text is returned."""
        result = format_response(
            text="I can help you analyze feedback data.",
            sql_columns=None,
            sql_rows=None,
        )
        assert result["text"] == "I can help you analyze feedback data."
        assert result["structured_data"] == []

    def test_format_response_sanitizes_text(self):
        """LLM text is sanitized before returning."""
        result = format_response(
            text="<script>alert('xss')</script> Summary",
            sql_columns=None,
            sql_rows=None,
        )
        assert "<script>" not in result["text"]

    def test_format_response_empty_sql_results(self):
        """Empty SQL results produce empty table (not an error)."""
        result = format_response(
            text="No data found.",
            sql_columns=["sentiment", "count"],
            sql_rows=[],
        )
        structured = result["structured_data"]
        table = next((s for s in structured if s["data_type"] == "table"), None)
        assert table is not None
        assert table["data"]["rows"] == []

    def test_format_response_include_table_false_skips_table(self):
        """When include_table=False, no table item in structured_data."""
        result = format_response(
            text="Summary only.",
            sql_columns=["sentiment", "count"],
            sql_rows=[["negative", 47], ["neutral", 123], ["positive", 89]],
            include_table=False,
        )
        types = [s["data_type"] for s in result["structured_data"]]
        assert "table" not in types
        # Chart should still be present (default include_chart=True)
        assert "chart" in types

    def test_format_response_include_chart_false_skips_chart(self):
        """When include_chart=False, no chart item in structured_data."""
        result = format_response(
            text="Table only.",
            sql_columns=["sentiment", "count"],
            sql_rows=[["negative", 47], ["neutral", 123], ["positive", 89]],
            include_chart=False,
        )
        types = [s["data_type"] for s in result["structured_data"]]
        assert "chart" not in types
        assert "table" in types

    def test_format_response_both_false_returns_text_only(self):
        """When both include_table=False and include_chart=False, structured_data is empty."""
        result = format_response(
            text="Just text.",
            sql_columns=["sentiment", "count"],
            sql_rows=[["negative", 47], ["neutral", 123], ["positive", 89]],
            include_table=False,
            include_chart=False,
        )
        assert result["structured_data"] == []

    def test_format_response_defaults_include_both(self):
        """Default behavior (no flags) still includes both table and chart."""
        result = format_response(
            text="Full response.",
            sql_columns=["sentiment", "count"],
            sql_rows=[["negative", 47], ["neutral", 123], ["positive", 89]],
        )
        types = [s["data_type"] for s in result["structured_data"]]
        assert "table" in types
        assert "chart" in types
