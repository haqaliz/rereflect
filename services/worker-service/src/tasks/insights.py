"""
Weekly insights generation task.
Generates AI-powered weekly insight summaries for each organization.
"""

import logging
from datetime import datetime, timedelta

from celery import shared_task

from src.database import get_db_session
from src.models import Organization, FeedbackItem, WeeklyInsight, CustomerHealth
from src.openai_client import generate_insights, generate_churn_analysis

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


@shared_task(name="src.tasks.insights.generate_churn_insights")
def generate_churn_insights() -> dict:
    """
    Periodic task: Generate LLM-powered churn analysis for at-risk customers.
    Runs every Monday at 7:00 AM UTC (before weekly insights at 8:30 AM).

    Workflow:
    1. For each org with AI enabled, find customers with health_score < 40
    2. For each at-risk customer, gather recent feedback
    3. Send to GPT for deep churn analysis
    4. Store LLM analysis on the CustomerHealth record
    """
    with get_db_session() as db:
        organizations = db.query(Organization).filter(
            Organization.ai_analysis_enabled == True,
        ).all()

        if not organizations:
            return {"status": "no_organizations", "analyzed": 0}

        analyzed = 0
        skipped = 0
        errors = 0

        for org in organizations:
            try:
                # Find at-risk customers (health_score < 40)
                at_risk = db.query(CustomerHealth).filter(
                    CustomerHealth.organization_id == org.id,
                    CustomerHealth.health_score < 40,
                ).order_by(CustomerHealth.health_score.asc()).limit(20).all()

                if not at_risk:
                    skipped += 1
                    continue

                org_key = getattr(org, "openai_api_key", None)

                for customer in at_risk:
                    try:
                        # Get recent feedback for this customer
                        recent_feedback = db.query(FeedbackItem).filter(
                            FeedbackItem.organization_id == org.id,
                            FeedbackItem.customer_email == customer.customer_email,
                        ).order_by(
                            FeedbackItem.created_at.desc()
                        ).limit(20).all()

                        if len(recent_feedback) < 2:
                            continue

                        feedback_texts = [item.text for item in recent_feedback]

                        result = generate_churn_analysis(
                            customer_email=customer.customer_email,
                            health_score=customer.health_score,
                            risk_level=customer.risk_level,
                            churn_risk_component=customer.churn_risk_component,
                            sentiment_component=customer.sentiment_component,
                            resolution_component=customer.resolution_component,
                            frequency_component=customer.frequency_component,
                            feedback_texts=feedback_texts,
                            org_api_key=org_key,
                        )

                        if result:
                            # Build analysis text from structured result
                            analysis_parts = [result["analysis"]]
                            if result.get("recommended_actions"):
                                analysis_parts.append(
                                    "Actions: " + "; ".join(result["recommended_actions"])
                                )
                            if result.get("estimated_urgency"):
                                analysis_parts.append(
                                    f"Urgency: {result['estimated_urgency']}"
                                )

                            customer.llm_analysis = " | ".join(analysis_parts)
                            customer.llm_analyzed_at = datetime.utcnow()
                            db.flush()
                            analyzed += 1

                            logger.info(
                                f"Generated churn analysis for {customer.customer_email} "
                                f"(org {org.id}, score {customer.health_score})"
                            )

                    except Exception as e:
                        logger.error(
                            f"Error analyzing customer {customer.customer_email} "
                            f"(org {org.id}): {e}"
                        )
                        errors += 1

            except Exception as e:
                logger.error(f"Error processing churn insights for org {org.id}: {e}")
                errors += 1

        logger.info(
            f"Churn insights complete: analyzed={analyzed}, skipped={skipped}, errors={errors}"
        )

        return {
            "status": "complete",
            "analyzed": analyzed,
            "skipped": skipped,
            "errors": errors,
        }
