"""
SQL Generator — generates safe SQL from natural language queries using LLM.

Generation flow:
1. Build LLM prompt with schema whitelist + examples
2. LLM generates candidate SQL
3. Pass through SQL validator (all safety guardrails)
4. Inject org scope + row limits
5. Return validated, safe SQL ready for execution
"""

import logging
import os
import re
from typing import Optional

from src.services.copilot.sql_validator import SQLValidator
from src.services.copilot.schema_whitelist import DEFAULT_WHITELIST

logger = logging.getLogger(__name__)

# System prompt for SQL generation
_SYSTEM_PROMPT = """You are a SQL query generator for a customer feedback analytics platform.

You MUST generate ONLY valid PostgreSQL SELECT queries. NEVER generate INSERT, UPDATE, DELETE, DROP, or any other write operations.

Available tables and columns:
{schema_description}

Safety rules you MUST follow:
1. Only SELECT statements — no writes
2. Always include WHERE organization_id = :org_id
3. Always include a LIMIT clause (max 1000)
4. No subqueries (nested SELECT)
5. Maximum 3 JOINs
6. Use :param_name placeholders for all variable values (NOT SQL injection)
7. Only use tables and columns from the list above

Return ONLY the SQL query, with no explanation or markdown.
"""

_EXAMPLE_QUERIES = """
Examples of valid queries:
- COUNT(*) FROM feedback_items WHERE organization_id = :org_id AND sentiment_label = 'negative' LIMIT 100
- SELECT sentiment_label, COUNT(*) FROM feedback_items WHERE organization_id = :org_id GROUP BY sentiment_label LIMIT 100
- SELECT customer_email, health_score FROM customer_health_scores WHERE organization_id = :org_id ORDER BY health_score ASC LIMIT 50
"""


def _build_schema_description(whitelist: dict) -> str:
    """Format the whitelist as a human-readable schema description for the LLM."""
    lines = []
    for table_name, columns in whitelist.items():
        if columns is None:
            lines.append(f"- {table_name} (all columns)")
        else:
            col_str = ", ".join(columns[:20])  # Limit to first 20 columns for brevity
            if len(columns) > 20:
                col_str += f" ... (+{len(columns) - 20} more)"
            lines.append(f"- {table_name}: {col_str}")
    return "\n".join(lines)


class SQLGenerator:
    """
    Generates validated SQL queries from natural language questions.
    Uses LLM for generation and SQLValidator for safety enforcement.
    """

    def __init__(self):
        self.validator = SQLValidator()

    def generate(
        self,
        question: str,
        org_id: int,
        plan: str,
        whitelist: Optional[dict] = None,
        context: Optional[str] = None,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
    ) -> dict:
        """
        Generate a safe SQL query from a natural language question.

        Args:
            question: User's natural language question
            org_id: Organization ID for scope injection
            plan: User's plan ("free", "pro", "business", "enterprise")
            whitelist: Schema whitelist dict (uses DEFAULT_WHITELIST if None)
            context: Optional context string (scope summary, @mentions data)
            api_key: OpenAI API key (uses env var if None)
            model: LLM model to use

        Returns:
            {
                "sql": str,             # Safe, validated SQL
                "parameters": dict,     # Parameters to bind when executing
                "query_type": str,      # "aggregation", "detail", or "export"
                "error": str | None,    # Error message if generation failed
            }
        """
        if whitelist is None:
            whitelist = DEFAULT_WHITELIST

        # 1. Build LLM prompt
        schema_desc = _build_schema_description(whitelist)
        system_prompt = _SYSTEM_PROMPT.format(schema_description=schema_desc)
        user_prompt = self._build_user_prompt(question, context)

        # 2. Call LLM
        try:
            raw_sql = self._call_llm(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                api_key=api_key,
                model=model,
            )
        except Exception as e:
            logger.error(f"LLM SQL generation failed: {e}")
            return {"sql": None, "parameters": {}, "query_type": "detail", "error": str(e)}

        if not raw_sql:
            return {
                "sql": None,
                "parameters": {},
                "query_type": "detail",
                "error": "LLM returned empty response",
            }

        # 3. Clean up LLM output (strip markdown code blocks)
        sql = self._clean_sql(raw_sql)

        # 4. Validate all safety guardrails
        validation = self.validator.validate(
            sql=sql,
            org_id=org_id,
            plan=plan,
            whitelist=whitelist,
        )

        if not validation.is_valid:
            logger.warning(f"Generated SQL failed validation: {validation.error}")
            return {
                "sql": None,
                "parameters": {},
                "query_type": "detail",
                "error": f"Generated SQL failed safety check: {validation.error}",
            }

        # 5. Inject org scope
        sql = self.validator.inject_org_scope(sql, org_id=org_id)

        # 6. Detect query type and inject row limits
        query_type = self.validator.detect_query_type(sql)
        sql = self.validator.inject_row_limit(sql, query_type=query_type, plan=plan)

        return {
            "sql": sql,
            "parameters": {"org_id": org_id},
            "query_type": query_type,
            "error": None,
        }

    def _build_user_prompt(self, question: str, context: Optional[str]) -> str:
        """Build the user-facing portion of the LLM prompt."""
        parts = []
        if context:
            parts.append(f"Context:\n{context}\n")
        parts.append(f"Generate a SQL query to answer: {question}")
        parts.append(_EXAMPLE_QUERIES)
        return "\n".join(parts)

    def _clean_sql(self, raw: str) -> str:
        """Remove markdown code blocks and extra whitespace from LLM output."""
        # Remove ```sql ... ``` blocks
        raw = re.sub(r"```sql\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"```\s*", "", raw)
        return raw.strip()

    def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        api_key: Optional[str],
        model: str,
    ) -> str:
        """Call OpenAI to generate SQL. Returns the raw SQL string."""
        import openai

        key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise RuntimeError("No OpenAI API key available for SQL generation")

        client = openai.OpenAI(api_key=key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,  # Deterministic SQL generation
            max_tokens=500,
        )
        return response.choices[0].message.content or ""
