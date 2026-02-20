"""
Weekly insights generation task.
Generates AI-powered weekly insight summaries for each organization.
"""

import logging
import time
from datetime import datetime, timedelta

from celery import shared_task

from src.database import get_db_session
from src.models import Organization, FeedbackItem, WeeklyInsight, CustomerHealth, CustomerAnalysisAction
from src.openai_client import generate_insights, generate_churn_analysis, generate_customer_analysis
from src.notification_dispatch import dispatch_alert

logger = logging.getLogger(__name__)


def _store_analysis_result(db, customer: CustomerHealth, result: dict, org_id: int) -> None:
    """
    Store a structured analysis result on a CustomerHealth record.

    - Writes llm_analysis_data (structured JSON)
    - Writes llm_raw_response (raw OpenAI response)
    - Keeps legacy llm_analysis pipe-separated text in sync (transition period)
    - Archives old pending action items, creates new ones
    - Dispatches alert for immediate urgency
    """
    # Extract raw response before building structured data
    raw_response = result.pop("_raw_response", None)

    # Build structured data (without _raw_response)
    structured_data = {
        "analysis": result["analysis"],
        "recommended_actions": result.get("recommended_actions", []),
        "risk_drivers": result.get("risk_drivers", []),
        "estimated_urgency": result.get("estimated_urgency", "this_month"),
        "analysis_type": result.get("analysis_type", "churn_risk"),
    }

    # Store structured JSON
    customer.llm_analysis_data = structured_data
    customer.llm_raw_response = raw_response
    customer.llm_analyzed_at = datetime.utcnow()

    # Keep legacy pipe-separated text in sync (transition period)
    analysis_parts = [result["analysis"]]
    if result.get("recommended_actions"):
        analysis_parts.append("Actions: " + "; ".join(result["recommended_actions"]))
    if result.get("estimated_urgency"):
        analysis_parts.append(f"Urgency: {result['estimated_urgency']}")
    customer.llm_analysis = " | ".join(analysis_parts)

    db.flush()

    # Archive old pending action items for this customer
    db.query(CustomerAnalysisAction).filter(
        CustomerAnalysisAction.customer_health_id == customer.id,
        CustomerAnalysisAction.status == "pending",
    ).delete(synchronize_session="fetch")

    # Create new action items from recommended_actions
    for action_text in result.get("recommended_actions", []):
        action = CustomerAnalysisAction(
            customer_health_id=customer.id,
            organization_id=org_id,
            action_text=action_text,
        )
        db.add(action)

    db.flush()

    # Dispatch alert for immediate urgency
    if result.get("estimated_urgency") == "immediate":
        try:
            dispatch_alert(
                org_id=org_id,
                alert_type="churn_risk",
                title=f"Immediate churn risk: {customer.customer_email}",
                message=result["analysis"][:200],
                link=f"/customers/{customer.customer_email}",
                metadata={
                    "customer_email": customer.customer_email,
                    "health_score": customer.health_score,
                    "analysis_type": structured_data["analysis_type"],
                },
            )
        except Exception as e:
            logger.error(f"Failed to dispatch churn alert for {customer.customer_email}: {e}")


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

                        result = generate_customer_analysis(
                            analysis_type="churn_risk",
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
                            _store_analysis_result(db, customer, result, org.id)
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


# Delay between LLM calls to avoid rate limiting (seconds)
_BATCH_CALL_DELAY = 1.5

# Staleness threshold: re-analyze if llm_analyzed_at is older than this
_STALE_DAYS = 7


@shared_task(name="src.tasks.insights.batch_churn_analysis")
def batch_churn_analysis(org_id: int) -> dict:
    """
    On-demand task: Run LLM churn analysis for all at-risk customers in an org.

    Triggered by POST /api/v1/customers/batch-analyze.
    Processes customers where health_score < 40 AND (llm_analysis is NULL
    OR llm_analyzed_at is older than 7 days).

    Workflow:
    1. Find at-risk customers that need analysis (new or stale)
    2. For each, gather recent feedback and call generate_churn_analysis
    3. Update llm_analysis and llm_analyzed_at on the CustomerHealth record
    4. Add a small delay between API calls to avoid rate limiting
    """
    stale_cutoff = datetime.utcnow() - timedelta(days=_STALE_DAYS)

    with get_db_session() as db:
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            logger.error(f"batch_churn_analysis: org {org_id} not found")
            return {"status": "error", "detail": "org_not_found"}

        org_key = getattr(org, "openai_api_key", None)

        all_customers = (
            db.query(CustomerHealth)
            .filter(
                CustomerHealth.organization_id == org_id,
                CustomerHealth.is_archived == False,
            )
            .order_by(CustomerHealth.health_score.asc())
            .all()
        )

        # Filter to customers that need analysis (missing or stale)
        to_analyze = [
            c for c in all_customers
            if c.llm_analysis_data is None or (
                c.llm_analyzed_at is not None and c.llm_analyzed_at < stale_cutoff
            )
        ]

        if not to_analyze:
            logger.info(f"batch_churn_analysis: no customers need analysis for org {org_id}")
            return {"status": "complete", "analyzed": 0, "skipped": len(all_customers), "errors": 0}

        logger.info(
            f"batch_churn_analysis: processing {len(to_analyze)} customers for org {org_id} "
            f"({len(all_customers) - len(to_analyze)} already up to date)"
        )

        analyzed = 0
        errors = 0

        for i, customer in enumerate(to_analyze):
            try:
                recent_feedback = (
                    db.query(FeedbackItem)
                    .filter(
                        FeedbackItem.organization_id == org_id,
                        FeedbackItem.customer_email == customer.customer_email,
                    )
                    .order_by(FeedbackItem.created_at.desc())
                    .limit(20)
                    .all()
                )

                if len(recent_feedback) < 2:
                    logger.info(
                        f"batch_churn_analysis: skipping {customer.customer_email} "
                        f"— insufficient feedback ({len(recent_feedback)} items)"
                    )
                    continue

                feedback_texts = [item.text for item in recent_feedback]

                # Determine analysis type based on health score
                if customer.health_score < 40:
                    analysis_type = "churn_risk"
                elif customer.health_score < 70:
                    analysis_type = "retention"
                else:
                    analysis_type = "growth_opportunity"

                result = generate_customer_analysis(
                    analysis_type=analysis_type,
                    customer_email=customer.customer_email,
                    health_score=customer.health_score,
                    risk_level=customer.risk_level,
                    churn_risk_component=customer.churn_risk_component or 50,
                    sentiment_component=customer.sentiment_component or 50,
                    resolution_component=customer.resolution_component or 50,
                    frequency_component=customer.frequency_component or 50,
                    feedback_texts=feedback_texts,
                    org_api_key=org_key,
                )

                if result:
                    _store_analysis_result(db, customer, result, org_id)
                    analyzed += 1

                    logger.info(
                        f"batch_churn_analysis: analyzed {customer.customer_email} "
                        f"(org {org_id}, type {analysis_type}, score {customer.health_score})"
                    )

            except Exception as e:
                logger.error(
                    f"batch_churn_analysis: error for {customer.customer_email} "
                    f"(org {org_id}): {e}"
                )
                errors += 1

            # Avoid rate limiting between API calls
            if i < len(to_analyze) - 1:
                time.sleep(_BATCH_CALL_DELAY)

        db.commit()

        logger.info(
            f"batch_churn_analysis complete for org {org_id}: "
            f"analyzed={analyzed}, errors={errors}"
        )

        return {
            "status": "complete",
            "analyzed": analyzed,
            "skipped": len(all_customers) - len(to_analyze),
            "errors": errors,
        }


def _run_tiered_analysis(analysis_type: str, score_min: int, score_max: int, limit_per_org: int) -> dict:
    """
    Shared logic for tiered analysis tasks (retention, growth).
    Queries customers in the given score range, runs analysis, stores results.
    """
    stale_cutoff = datetime.utcnow() - timedelta(days=_STALE_DAYS)

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
                customers = db.query(CustomerHealth).filter(
                    CustomerHealth.organization_id == org.id,
                    CustomerHealth.health_score >= score_min,
                    CustomerHealth.health_score < score_max,
                    CustomerHealth.is_archived == False,
                ).order_by(CustomerHealth.health_score.asc()).limit(limit_per_org).all()

                if not customers:
                    skipped += 1
                    continue

                org_key = getattr(org, "openai_api_key", None)

                for i, customer in enumerate(customers):
                    # Skip if analysis is fresh
                    if (
                        customer.llm_analysis_data is not None
                        and customer.llm_analyzed_at is not None
                        and customer.llm_analyzed_at >= stale_cutoff
                    ):
                        continue

                    try:
                        recent_feedback = db.query(FeedbackItem).filter(
                            FeedbackItem.organization_id == org.id,
                            FeedbackItem.customer_email == customer.customer_email,
                        ).order_by(
                            FeedbackItem.created_at.desc()
                        ).limit(20).all()

                        if len(recent_feedback) < 2:
                            continue

                        feedback_texts = [item.text for item in recent_feedback]

                        result = generate_customer_analysis(
                            analysis_type=analysis_type,
                            customer_email=customer.customer_email,
                            health_score=customer.health_score,
                            risk_level=customer.risk_level,
                            churn_risk_component=customer.churn_risk_component or 50,
                            sentiment_component=customer.sentiment_component or 50,
                            resolution_component=customer.resolution_component or 50,
                            frequency_component=customer.frequency_component or 50,
                            feedback_texts=feedback_texts,
                            org_api_key=org_key,
                        )

                        if result:
                            _store_analysis_result(db, customer, result, org.id)
                            analyzed += 1

                            logger.info(
                                f"Generated {analysis_type} analysis for {customer.customer_email} "
                                f"(org {org.id}, score {customer.health_score})"
                            )

                    except Exception as e:
                        logger.error(
                            f"Error in {analysis_type} analysis for {customer.customer_email} "
                            f"(org {org.id}): {e}"
                        )
                        errors += 1

                    # Rate limiting
                    if i < len(customers) - 1:
                        time.sleep(_BATCH_CALL_DELAY)

                db.commit()

            except Exception as e:
                logger.error(f"Error processing {analysis_type} insights for org {org.id}: {e}")
                errors += 1

        logger.info(
            f"{analysis_type} insights complete: analyzed={analyzed}, skipped={skipped}, errors={errors}"
        )

        return {
            "status": "complete",
            "analyzed": analyzed,
            "skipped": skipped,
            "errors": errors,
        }


@shared_task(name="src.tasks.insights.generate_retention_insights")
def generate_retention_insights() -> dict:
    """
    Periodic task: Generate retention analysis for moderate customers (40-69 health score).
    Runs every Monday at 7:15 AM UTC, bi-weekly (even ISO weeks only).
    """
    # Bi-weekly skip logic: only run on even ISO weeks
    iso_week = datetime.utcnow().isocalendar()[1]
    if iso_week % 2 != 0:
        logger.info(f"generate_retention_insights: skipping odd ISO week {iso_week}")
        return {"status": "skipped", "reason": f"odd_iso_week_{iso_week}"}

    return _run_tiered_analysis(
        analysis_type="retention",
        score_min=40,
        score_max=70,
        limit_per_org=20,
    )


@shared_task(name="src.tasks.insights.generate_growth_insights")
def generate_growth_insights() -> dict:
    """
    Periodic task: Generate growth opportunity analysis for healthy customers (70+ health score).
    Runs every Monday at 7:30 AM UTC, monthly (first Monday of month only).
    """
    # Monthly skip logic: only run in the first 7 days of the month
    day = datetime.utcnow().day
    if day > 7:
        logger.info(f"generate_growth_insights: skipping, day {day} > 7")
        return {"status": "skipped", "reason": f"day_{day}_not_first_week"}

    return _run_tiered_analysis(
        analysis_type="growth_opportunity",
        score_min=70,
        score_max=101,  # health_score max is 100
        limit_per_org=10,
    )


@shared_task(name="src.tasks.insights.analyze_customer_health")
def analyze_customer_health(org_id: int, customer_email: str) -> dict:
    """
    On-demand task: Run LLM analysis for a single customer.
    Triggered by POST /api/v1/customers/{email}/analyze.
    Determines analysis type based on health score tier.
    """
    with get_db_session() as db:
        customer = (
            db.query(CustomerHealth)
            .filter(
                CustomerHealth.organization_id == org_id,
                CustomerHealth.customer_email == customer_email,
            )
            .first()
        )

        if not customer:
            logger.error(f"analyze_customer_health: customer {customer_email} not found in org {org_id}")
            return {"status": "error", "detail": "customer_not_found"}

        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            logger.error(f"analyze_customer_health: org {org_id} not found")
            return {"status": "error", "detail": "org_not_found"}

        org_key = getattr(org, "openai_api_key", None)

        recent_feedback = (
            db.query(FeedbackItem)
            .filter(
                FeedbackItem.organization_id == org_id,
                FeedbackItem.customer_email == customer_email,
            )
            .order_by(FeedbackItem.created_at.desc())
            .limit(20)
            .all()
        )

        if len(recent_feedback) < 1:
            logger.info(f"analyze_customer_health: no feedback for {customer_email}")
            return {"status": "skipped", "detail": "no_feedback"}

        feedback_texts = [item.text for item in recent_feedback]

        # Determine analysis type based on health score
        if customer.health_score < 40:
            analysis_type = "churn_risk"
        elif customer.health_score < 70:
            analysis_type = "retention"
        else:
            analysis_type = "growth_opportunity"

        result = generate_customer_analysis(
            analysis_type=analysis_type,
            customer_email=customer.customer_email,
            health_score=customer.health_score,
            risk_level=customer.risk_level,
            churn_risk_component=customer.churn_risk_component or 50,
            sentiment_component=customer.sentiment_component or 50,
            resolution_component=customer.resolution_component or 50,
            frequency_component=customer.frequency_component or 50,
            feedback_texts=feedback_texts,
            org_api_key=org_key,
        )

        if result:
            _store_analysis_result(db, customer, result, org_id)
            db.commit()
            logger.info(
                f"analyze_customer_health: completed {analysis_type} analysis for "
                f"{customer_email} (org {org_id}, score {customer.health_score})"
            )
            return {"status": "complete", "analysis_type": analysis_type}

        return {"status": "no_result"}


@shared_task(name="src.tasks.insights.generate_churn_insights_for_customer")
def generate_churn_insights_for_customer(org_id: int, customer_email: str) -> dict:
    """
    On-demand task: Run LLM churn analysis for a single customer.
    Triggered automatically when a health drop alert fires and analysis is stale (>24h).
    Delegates to analyze_customer_health for the actual analysis logic.
    """
    return analyze_customer_health(org_id, customer_email)
