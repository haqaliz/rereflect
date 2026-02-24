"""
Response formatter for AI Copilot (M2.2 Task #7).

Converts SQL results + LLM text into structured, renderable responses:
- Table formatter: converts SQL rows to table structure
- Chart formatter: auto-detects chart type and formats for Recharts
- Deep link generator: replaces entity references with clickable links
- Markdown sanitizer: strips XSS vectors from LLM output
"""

import re
from enum import Enum
from typing import Optional


class ChartType(str, Enum):
    BAR = "bar"
    LINE = "line"
    PIE = "pie"


# ── Table Formatter ───────────────────────────────────────────────────────────

MAX_TABLE_ROWS = 1000


def format_table(columns: list, rows: list) -> dict:
    """
    Convert SQL result rows into a structured table response.

    Returns:
        {
            "data_type": "table",
            "data": {
                "columns": [...],
                "rows": [...],
                "summary": "...",
                "truncated": True/False  (only if truncated)
            }
        }
    """
    truncated = len(rows) > MAX_TABLE_ROWS
    display_rows = rows[:MAX_TABLE_ROWS] if truncated else rows

    total = len(rows)
    summary = f"{total} row{'s' if total != 1 else ''}"
    if truncated:
        summary += f" (showing first {MAX_TABLE_ROWS})"

    data = {
        "columns": columns,
        "rows": display_rows,
        "summary": summary,
    }
    if truncated:
        data["truncated"] = True

    return {
        "data_type": "table",
        "data": data,
    }


# ── Chart Type Detection ──────────────────────────────────────────────────────

# Date-like column name patterns
_DATE_PATTERNS = re.compile(
    r"^(date|day|week|month|year|period|time|timestamp|created|updated).*$",
    re.IGNORECASE,
)

# Percentage-like column name patterns
_PCT_PATTERNS = re.compile(
    r"^(percent|pct|percentage|share|proportion|ratio).*$",
    re.IGNORECASE,
)


def _is_date_column(col_name: str, rows: list, col_index: int) -> bool:
    """Detect if a column represents dates/time."""
    if _DATE_PATTERNS.match(col_name):
        return True
    # Check if values look like dates (YYYY-MM-DD or similar)
    if rows:
        sample = rows[0][col_index]
        if isinstance(sample, str) and re.match(r"^\d{4}-\d{2}", sample):
            return True
    return False


def _is_percentage_column(col_name: str, rows: list, col_index: int) -> bool:
    """Detect if a column represents percentages."""
    if _PCT_PATTERNS.match(col_name):
        return True
    # Check if values are all between 0 and 100
    if rows and len(rows) >= 2:
        values = [row[col_index] for row in rows if row[col_index] is not None]
        if values and all(isinstance(v, (int, float)) and 0 <= v <= 100 for v in values):
            # Sum near 100 is a good indicator
            total = sum(values)
            if 95 <= total <= 105:
                return True
    return False


def _is_numeric(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def detect_chart_type(columns: list, rows: list) -> Optional[ChartType]:
    """
    Auto-detect the best chart type for given columns/rows.

    Rules:
    - Must have exactly 2 columns
    - Must have >= 2 rows
    - date + numeric → LINE
    - categorical + percentage → PIE
    - categorical + numeric → BAR
    - Anything else → None
    """
    if len(columns) != 2 or len(rows) < 2:
        return None

    col0, col1 = columns[0], columns[1]

    # Check col1 is numeric
    sample_vals = [row[1] for row in rows if row[1] is not None]
    if not sample_vals or not all(_is_numeric(v) for v in sample_vals):
        return None

    # Date column → line chart
    if _is_date_column(col0, rows, 0):
        return ChartType.LINE

    # Percentage column → pie chart
    if _is_percentage_column(col1, rows, 1):
        return ChartType.PIE

    # Categorical + numeric → bar chart (default)
    return ChartType.BAR


# ── Chart Formatter ───────────────────────────────────────────────────────────


def format_chart(chart_type: ChartType, columns: list, rows: list) -> dict:
    """
    Format SQL rows as a Recharts-compatible chart data structure.

    Bar/Line chart output: list of dicts with category key + value key
    Pie chart output: list of {name, value} dicts
    """
    col0, col1 = columns[0], columns[1]

    if chart_type == ChartType.PIE:
        data = [
            {"name": row[0], "value": row[1]}
            for row in rows
            if row[0] is not None
        ]
    else:
        # For bar and line charts, Recharts expects a list of objects
        # with the category column as a key and numeric column as another key
        data = [
            {col0: row[0], col1: row[1]}
            for row in rows
        ]

    return {
        "data_type": "chart",
        "chart_type": chart_type.value,
        "data": data,
    }


# ── Deep Link Generator ───────────────────────────────────────────────────────

# Match customer email addresses (word@word.word pattern)
_EMAIL_RE = re.compile(
    r"\b([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\b"
)

# Match feedback ID references like "#1234" or "feedback #1234"
_FEEDBACK_ID_RE = re.compile(r"#(\d+)\b")

# Match pain point category references like "'billing' pain point"
_PAIN_POINT_RE = re.compile(
    r"'([^']+)'\s+pain\s+point",
    re.IGNORECASE,
)


def generate_deep_links(text: str) -> str:
    """
    Replace entity references in text with markdown deep links.

    Supported entities:
    - Customer emails → /customers/{email}
    - Feedback IDs (#1234) → /feedbacks/{id}
    - Pain point categories → /pain-points?category={name}
    """
    # Replace customer emails
    text = _EMAIL_RE.sub(
        lambda m: f"[{m.group(1)}](/customers/{m.group(1)})",
        text,
    )

    # Replace feedback IDs (#1234)
    text = _FEEDBACK_ID_RE.sub(
        lambda m: f"[#{m.group(1)}](/feedbacks/{m.group(1)})",
        text,
    )

    # Replace pain point category references
    text = _PAIN_POINT_RE.sub(
        lambda m: f"['{m.group(1)}' pain point](/pain-points?category={m.group(1)})",
        text,
    )

    return text


# ── Markdown Sanitizer ────────────────────────────────────────────────────────

# Tags to completely strip (including content)
_SCRIPT_RE = re.compile(
    r"<script\b[^>]*>.*?</script>",
    re.IGNORECASE | re.DOTALL,
)

# Tags to strip (keep content)
_TAG_RE = re.compile(
    r"<(?:iframe|object|embed|form|input|button)[^>]*>.*?</(?:iframe|object|embed|form|input|button)>|"
    r"<(?:iframe|object|embed|form|input|button)[^>]*/?>",
    re.IGNORECASE | re.DOTALL,
)

# Remove onclick, onload, onerror etc. event handler attributes
_EVENT_ATTR_RE = re.compile(
    r"\s+on[a-z]+\s*=\s*[\"'][^\"']*[\"']",
    re.IGNORECASE,
)

# Remove javascript: URLs
_JS_URL_RE = re.compile(
    r"\[([^\]]*)\]\(javascript:[^)]*\)",
    re.IGNORECASE,
)


def sanitize_markdown(text: str) -> str:
    """
    Sanitize LLM-generated markdown to prevent XSS.

    - Remove <script> tags and their content
    - Remove <iframe>, <object>, <embed> tags
    - Remove onclick/onerror/etc. event attributes
    - Remove javascript: URLs in markdown links
    - Close unclosed code blocks
    """
    # 1. Remove script tags + content
    text = _SCRIPT_RE.sub("", text)

    # 2. Remove dangerous HTML tags
    text = _TAG_RE.sub("", text)

    # 3. Remove event handler attributes
    text = _EVENT_ATTR_RE.sub("", text)

    # 4. Replace javascript: links
    text = _JS_URL_RE.sub(r"[\1](#)", text)

    # 5. Fix unclosed code blocks (must have even number of ```)
    triple_backtick_count = text.count("```")
    if triple_backtick_count % 2 != 0:
        text = text + "\n```"

    return text


# ── Full Response Formatter ───────────────────────────────────────────────────


def format_response(
    text: str,
    sql_columns: Optional[list],
    sql_rows: Optional[list],
    include_table: bool = True,
    include_chart: bool = True,
) -> dict:
    """
    Format a complete copilot response with text + structured data.

    Returns:
        {
            "text": "sanitized markdown text",
            "structured_data": [
                {"data_type": "table", ...},
                {"data_type": "chart", ...},
            ]
        }
    """
    # 1. Sanitize the LLM text
    clean_text = sanitize_markdown(text)

    # 2. Generate deep links in text
    clean_text = generate_deep_links(clean_text)

    structured_data = []

    if sql_columns is not None and sql_rows is not None:
        # 3. Add table (if requested)
        if include_table:
            table = format_table(columns=sql_columns, rows=sql_rows)
            structured_data.append(table)

        # 4. Auto-detect and add chart (only if rows exist and requested)
        if include_chart and sql_rows:
            chart_type = detect_chart_type(columns=sql_columns, rows=sql_rows)
            if chart_type is not None:
                chart = format_chart(
                    chart_type=chart_type,
                    columns=sql_columns,
                    rows=sql_rows,
                )
                structured_data.append(chart)

    return {
        "text": clean_text,
        "structured_data": structured_data,
    }
