"""
Weekly insights generation task.
Generates AI-powered weekly insight summaries for each organization.
"""

import logging
from datetime import datetime, timedelta

from celery import shared_task

from src.database import get_db_session
from src.models import Organization, FeedbackItem, WeeklyInsight
from src.openai_client import generate_insights

logger = logging.getLogger(__name__)


@shared_task(name="src.tasks.insights.generate_weekly_insights")
def generate_weekly_insights() -> dict:
    """
    Periodic task: Generate AI-powered weekly insights for each organization.
    Runs every Monday at 8:30 AM UTC (before weekly digest at 9 AM).

    Workflow:
    1. For each org with AI enabled, collect past 7 days of feedback
    2. Send feedback batch to GPT for insight generation
    3. Store WeeklyInsight record
    """
    with get_db_session() as db:
        organizations = db.query(Organization).filter(
            Organization.ai_analysis_enabled == True,
        ).all()

        if not organizations:
            return {"status": "no_organizations", "generated": 0}

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=7)
        generated = 0
        skipped = 0
        errors = 0

        for org in organizations:
            try:
                # Get feedback texts from the past week
                feedback_items = db.query(FeedbackItem).filter(
                    FeedbackItem.organization_id == org.id,
                    FeedbackItem.created_at >= start_date,
                    FeedbackItem.created_at <= end_date,
                ).all()

                if len(feedback_items) < 3:
                    skipped += 1
                    continue

                feedback_texts = [item.text for item in feedback_items]

                # Generate insights via OpenAI
                org_key = getattr(org, "openai_api_key", None)
                insights = generate_insights(feedback_texts, org_api_key=org_key)

                if not insights:
                    logger.warning(f"No insights generated for org {org.id}")
                    skipped += 1
                    continue

                # Store the insights
                weekly_insight = WeeklyInsight(
                    organization_id=org.id,
                    week_start=start_date,
                    week_end=end_date,
                    insights=insights,
                    generated_at=datetime.utcnow(),
                )
                db.add(weekly_insight)
                db.commit()
                generated += 1

                logger.info(f"Generated {len(insights)} insights for org {org.id}")

            except Exception as e:
                logger.error(f"Error generating insights for org {org.id}: {e}")
                errors += 1

        logger.info(f"Weekly insights complete: generated={generated}, skipped={skipped}, errors={errors}")

        return {
            "status": "complete",
            "generated": generated,
            "skipped": skipped,
            "errors": errors,
        }
