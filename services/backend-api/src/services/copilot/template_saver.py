"""
Template Saver — auto-saves successful LLM-generated SQL as query templates.

Saving flow:
1. Check if identical SQL already exists as a template (idempotent)
2. If SQL exists → add new question_pattern + embedding (many-to-one mapping)
3. If SQL is new → create new query_template record + mapping
4. Increment usage_count on matched templates

Pre-populates 10-15 common system templates on first run.
"""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


# ── System templates (pre-built) ──────────────────────────────────────────────

SYSTEM_TEMPLATES = [
    {
        "description": "Count total feedbacks",
        "sql_query": "SELECT COUNT(*) as total_feedbacks FROM feedback_items WHERE organization_id = :org_id",
        "parameter_schema": {"org_id": "integer"},
        "question_patterns": [
            "how many feedbacks do we have",
            "total feedback count",
            "count all feedbacks",
            "number of feedbacks",
        ],
    },
    {
        "description": "Count feedbacks by sentiment",
        "sql_query": (
            "SELECT sentiment_label, COUNT(*) as count "
            "FROM feedback_items "
            "WHERE organization_id = :org_id "
            "GROUP BY sentiment_label "
            "ORDER BY count DESC "
            "LIMIT 100"
        ),
        "parameter_schema": {"org_id": "integer"},
        "question_patterns": [
            "how many negative feedbacks",
            "sentiment breakdown",
            "feedbacks by sentiment",
            "negative feedback count",
            "positive feedback count",
        ],
    },
    {
        "description": "List urgent feedbacks",
        "sql_query": (
            "SELECT id, text, sentiment_label, created_at "
            "FROM feedback_items "
            "WHERE organization_id = :org_id AND is_urgent = true "
            "ORDER BY created_at DESC "
            "LIMIT 50"
        ),
        "parameter_schema": {"org_id": "integer"},
        "question_patterns": [
            "show urgent feedbacks",
            "list urgent feedbacks",
            "urgent feedback that needs attention",
            "critical feedbacks",
        ],
    },
    {
        "description": "Top pain point categories this month",
        "sql_query": (
            "SELECT pain_point_category, COUNT(*) as count "
            "FROM feedback_items "
            "WHERE organization_id = :org_id "
            "AND pain_point_category IS NOT NULL "
            "GROUP BY pain_point_category "
            "ORDER BY count DESC "
            "LIMIT 100"
        ),
        "parameter_schema": {"org_id": "integer"},
        "question_patterns": [
            "top pain points",
            "most common pain points",
            "pain point categories",
            "what are the top pain points this month",
            "biggest pain points",
        ],
    },
    {
        "description": "Most requested feature categories",
        "sql_query": (
            "SELECT feature_request_category, COUNT(*) as count "
            "FROM feedback_items "
            "WHERE organization_id = :org_id "
            "AND feature_request_category IS NOT NULL "
            "GROUP BY feature_request_category "
            "ORDER BY count DESC "
            "LIMIT 100"
        ),
        "parameter_schema": {"org_id": "integer"},
        "question_patterns": [
            "most requested features",
            "top feature requests",
            "feature request categories",
            "what features do customers want",
            "popular feature requests",
        ],
    },
    {
        "description": "Customer health score summary",
        "sql_query": (
            "SELECT "
            "  COUNT(*) as total_customers, "
            "  ROUND(AVG(health_score), 1) as avg_health_score, "
            "  MIN(health_score) as min_score, "
            "  MAX(health_score) as max_score "
            "FROM customer_health_scores "
            "WHERE organization_id = :org_id"
        ),
        "parameter_schema": {"org_id": "integer"},
        "question_patterns": [
            "customer health summary",
            "average health score",
            "overall customer health",
            "customer health overview",
        ],
    },
    {
        "description": "Top churn risk customers",
        "sql_query": (
            "SELECT customer_email, health_score, risk_level, feedback_count "
            "FROM customer_health_scores "
            "WHERE organization_id = :org_id "
            "AND risk_level IN ('at_risk', 'critical') "
            "ORDER BY health_score ASC "
            "LIMIT 50"
        ),
        "parameter_schema": {"org_id": "integer"},
        "question_patterns": [
            "top churn risks",
            "customers at churn risk",
            "at risk customers",
            "critical customers",
            "customers with lowest health scores",
        ],
    },
    {
        "description": "Healthiest customers",
        "sql_query": (
            "SELECT customer_email, health_score, risk_level, feedback_count "
            "FROM customer_health_scores "
            "WHERE organization_id = :org_id "
            "AND risk_level = 'healthy' "
            "ORDER BY health_score DESC "
            "LIMIT 50"
        ),
        "parameter_schema": {"org_id": "integer"},
        "question_patterns": [
            "healthiest customers",
            "best customers",
            "customers with highest health score",
            "top performing customers",
        ],
    },
    {
        "description": "Feedbacks this week",
        "sql_query": (
            "SELECT COUNT(*) as count, sentiment_label "
            "FROM feedback_items "
            "WHERE organization_id = :org_id "
            "AND created_at >= :week_start "
            "GROUP BY sentiment_label "
            "LIMIT 100"
        ),
        "parameter_schema": {"org_id": "integer", "week_start": "datetime"},
        "question_patterns": [
            "feedbacks this week",
            "this week feedback summary",
            "feedback this week",
            "weekly feedback count",
        ],
    },
    {
        "description": "Recent feedbacks list",
        "sql_query": (
            "SELECT id, text, sentiment_label, source, created_at "
            "FROM feedback_items "
            "WHERE organization_id = :org_id "
            "ORDER BY created_at DESC "
            "LIMIT 50"
        ),
        "parameter_schema": {"org_id": "integer"},
        "question_patterns": [
            "show recent feedbacks",
            "latest feedbacks",
            "most recent feedback",
            "last feedbacks",
        ],
    },
    {
        "description": "Feedback count by source",
        "sql_query": (
            "SELECT source, COUNT(*) as count "
            "FROM feedback_items "
            "WHERE organization_id = :org_id "
            "AND source IS NOT NULL "
            "GROUP BY source "
            "ORDER BY count DESC "
            "LIMIT 100"
        ),
        "parameter_schema": {"org_id": "integer"},
        "question_patterns": [
            "feedback by source",
            "which channel has most feedback",
            "feedback sources breakdown",
            "intercom zendesk slack feedback count",
        ],
    },
    {
        "description": "Customers with declining health",
        "sql_query": (
            "SELECT customer_email, health_score, risk_level "
            "FROM customer_health_scores "
            "WHERE organization_id = :org_id "
            "AND risk_level IN ('moderate', 'at_risk', 'critical') "
            "ORDER BY health_score ASC "
            "LIMIT 50"
        ),
        "parameter_schema": {"org_id": "integer"},
        "question_patterns": [
            "customers with declining health scores",
            "declining customers",
            "customers getting worse",
            "deteriorating customers",
        ],
    },
    {
        "description": "Pain points by severity",
        "sql_query": (
            "SELECT pain_point_severity, COUNT(*) as count "
            "FROM feedback_items "
            "WHERE organization_id = :org_id "
            "AND pain_point_severity IS NOT NULL "
            "GROUP BY pain_point_severity "
            "ORDER BY count DESC "
            "LIMIT 100"
        ),
        "parameter_schema": {"org_id": "integer"},
        "question_patterns": [
            "pain points by severity",
            "critical pain points",
            "most severe issues",
            "severity breakdown of pain points",
        ],
    },
    {
        "description": "Feedback count in date range",
        "sql_query": (
            "SELECT COUNT(*) as count, sentiment_label "
            "FROM feedback_items "
            "WHERE organization_id = :org_id "
            "AND created_at >= :date_from "
            "AND created_at <= :date_to "
            "GROUP BY sentiment_label "
            "LIMIT 100"
        ),
        "parameter_schema": {"org_id": "integer", "date_from": "datetime", "date_to": "datetime"},
        "question_patterns": [
            "feedback in date range",
            "feedback last 30 days",
            "feedback last month",
            "sentiment over last 30 days",
        ],
    },
    {
        "description": "Urgent feedback categories",
        "sql_query": (
            "SELECT urgent_category, COUNT(*) as count "
            "FROM feedback_items "
            "WHERE organization_id = :org_id "
            "AND is_urgent = true "
            "AND urgent_category IS NOT NULL "
            "GROUP BY urgent_category "
            "ORDER BY count DESC "
            "LIMIT 100"
        ),
        "parameter_schema": {"org_id": "integer"},
        "question_patterns": [
            "urgent feedback categories",
            "types of urgent issues",
            "urgent issue breakdown",
            "most common urgent issues",
        ],
    },
]


class TemplateSaver:
    """
    Auto-saves successful LLM-generated SQL as query templates.
    Manages the self-learning template system.
    """

    def get_system_templates(self) -> list:
        """Return the list of pre-built system templates."""
        return SYSTEM_TEMPLATES

    def save_template(
        self,
        sql_query: str,
        question: str,
        description: str,
        parameter_schema: dict,
        created_by: str,
        org_id: Optional[int],
        db,
    ) -> dict:
        """
        Save a query template and its question mapping.

        If identical SQL already exists, creates a new mapping (idempotent).
        If SQL is new, creates both a new template and a mapping.

        Args:
            sql_query: The SQL query with :param placeholders
            question: The user question that generated this SQL
            description: Human-readable description of the template
            parameter_schema: Dict of parameter names and types
            created_by: "llm" | "admin" | "system"
            org_id: Organization ID (None for global/system templates)
            db: SQLAlchemy session

        Returns:
            {"template_id": str, "is_new": bool}
        """
        # 1. Generate embedding for the question
        embedding = self._generate_embedding(question)

        # 2. Check if identical SQL already exists as a template
        existing_template = self._find_template_by_sql(sql_query, org_id, db)

        if existing_template is not None:
            # Reuse existing template, add new mapping
            template_id = existing_template.id
            is_new = False
        else:
            # Create new template
            template_id = self._create_template(
                sql_query=sql_query,
                description=description,
                parameter_schema=parameter_schema,
                created_by=created_by,
                org_id=org_id,
                db=db,
            )
            is_new = True

        # 3. Add new question mapping
        self._create_mapping(
            template_id=template_id,
            question=question,
            embedding=embedding,
            db=db,
        )

        db.commit()

        return {"template_id": str(template_id), "is_new": is_new}

    def record_template_usage(self, template_id: int, db) -> None:
        """
        Increment usage_count and update last_used_at for a matched template.

        Args:
            template_id: ID of the template that was used
            db: SQLAlchemy session
        """
        try:
            from src.models.query_template import QueryTemplate
            template = db.query(QueryTemplate).filter_by(id=template_id).first()
        except ImportError:
            # Model not yet available (before migration)
            template = None

        if template is None:
            # Try raw SQL approach
            try:
                from sqlalchemy import text
                db.execute(
                    text(
                        "UPDATE query_templates SET usage_count = usage_count + 1, "
                        "last_used_at = :now WHERE id = :template_id"
                    ),
                    {"now": datetime.utcnow(), "template_id": template_id}
                )
                db.commit()
            except Exception as e:
                logger.warning(f"Failed to update template usage: {e}")
            return

        template.usage_count = (template.usage_count or 0) + 1
        template.last_used_at = datetime.utcnow()
        db.commit()

    def seed_system_templates(self, db) -> None:
        """
        Seed the database with pre-built system templates.
        Idempotent: skips templates that already exist.
        """
        for template_def in SYSTEM_TEMPLATES:
            existing = self._find_template_by_sql(template_def["sql_query"], None, db)
            if existing is not None:
                continue

            try:
                embedding = self._generate_embedding(template_def["question_patterns"][0])
            except Exception as e:
                logger.warning(f"Failed to generate embedding for system template: {e}")
                continue

            template_id = self._create_template(
                sql_query=template_def["sql_query"],
                description=template_def["description"],
                parameter_schema=template_def["parameter_schema"],
                created_by="system",
                org_id=None,
                db=db,
            )

            for pattern in template_def["question_patterns"]:
                try:
                    emb = self._generate_embedding(pattern)
                except Exception:
                    emb = embedding

                self._create_mapping(
                    template_id=template_id,
                    question=pattern,
                    embedding=emb,
                    db=db,
                )

        db.commit()

    # ── Private helpers ───────────────────────────────────────────────────────

    def _generate_embedding(self, text: str) -> list:
        """Generate embedding vector for text. Separated for testability."""
        import os

        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not configured")

        import openai
        client = openai.OpenAI(api_key=api_key)
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        return response.data[0].embedding

    def _find_template_by_sql(self, sql_query: str, org_id: Optional[int], db):
        """Find an existing template with identical SQL."""
        try:
            from src.models.query_template import QueryTemplate
            return db.query(QueryTemplate).filter_by(
                sql_query=sql_query,
                organization_id=org_id,
            ).first()
        except ImportError:
            # Model not yet available
            return None
        except Exception as e:
            logger.debug(f"Template lookup failed: {e}")
            return None

    def _create_template(
        self,
        sql_query: str,
        description: str,
        parameter_schema: dict,
        created_by: str,
        org_id: Optional[int],
        db,
    ):
        """Create a new QueryTemplate record and return its ID."""
        try:
            from src.models.query_template import QueryTemplate
            template = QueryTemplate(
                sql_query=sql_query,
                description=description,
                parameter_schema=parameter_schema,
                created_by=created_by,
                organization_id=org_id,
                usage_count=0,
                is_active=True,
            )
            db.add(template)
            db.flush()  # Get the ID
            return template.id
        except ImportError:
            # Fallback: use raw SQL — let DB auto-assign Integer PK
            import json as _json
            from sqlalchemy import text
            result = db.execute(
                text(
                    "INSERT INTO query_templates "
                    "(sql_query, description, parameter_schema, created_by, organization_id, usage_count, is_active, created_at, updated_at) "
                    "VALUES (:sql, :desc, :schema, :by, :org, 0, true, :now, :now) "
                    "RETURNING id"
                ),
                {
                    "sql": sql_query,
                    "desc": description,
                    "schema": _json.dumps(parameter_schema),
                    "by": created_by,
                    "org": org_id,
                    "now": datetime.utcnow(),
                }
            )
            row = result.fetchone()
            return row[0] if row else None

    def _create_mapping(self, template_id, question: str, embedding: list, db) -> None:
        """Create a new QueryTemplateMapping record."""
        try:
            from src.models.query_template_mapping import QueryTemplateMapping
            mapping = QueryTemplateMapping(
                template_id=template_id,
                question_pattern=question.lower(),
                question_embedding=embedding,
                match_count=0,
            )
            db.add(mapping)
        except ImportError:
            # Fallback: raw SQL — let DB auto-assign Integer PK
            import json as _json
            from sqlalchemy import text
            db.execute(
                text(
                    "INSERT INTO query_template_mappings "
                    "(template_id, question_pattern, question_embedding, match_count, created_at) "
                    "VALUES (:template_id, :pattern, :embedding, 0, :now)"
                ),
                {
                    "template_id": template_id,
                    "pattern": question.lower(),
                    "embedding": _json.dumps(embedding),
                    "now": datetime.utcnow(),
                }
            )
