"""
Copilot rate limiter service (M2.2 AI Copilot).

Enforces:
- Free tier: 10 queries/day per user
- Monthly token budget per organization
"""

from datetime import datetime, date
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.models.conversation_message import ConversationMessage
from src.models.organization import Organization


# Daily query limits by plan
DAILY_QUERY_LIMITS = {
    "free": 10,
    "pro": None,       # No daily cap
    "business": None,
    "enterprise": None,
}

# Monthly token budgets by plan
MONTHLY_TOKEN_BUDGETS = {
    "free": 50_000,
    "pro": 500_000,
    "business": 5_000_000,
    "enterprise": None,  # Unlimited
}


def get_daily_query_count(user_id: int, db: Session) -> int:
    """
    Count the number of user-role conversation messages created today.
    Each user message = 1 copilot query.
    """
    from src.models.conversation import Conversation

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    count = (
        db.query(func.count(ConversationMessage.id))
        .join(Conversation, Conversation.id == ConversationMessage.conversation_id)
        .filter(
            ConversationMessage.role == "user",
            ConversationMessage.created_at >= today_start,
            Conversation.created_by_user_id == user_id,
        )
        .scalar()
        or 0
    )
    return count


def get_monthly_tokens_used(org_id: int, db: Session) -> int:
    """
    Sum tokens consumed by the org in the current billing month.
    Only counts assistant messages (which have token data).
    """
    from src.models.conversation import Conversation

    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total = (
        db.query(
            func.coalesce(func.sum(ConversationMessage.tokens_in), 0)
            + func.coalesce(func.sum(ConversationMessage.tokens_out), 0)
        )
        .join(Conversation, Conversation.id == ConversationMessage.conversation_id)
        .filter(
            ConversationMessage.role == "assistant",
            ConversationMessage.created_at >= month_start,
            Conversation.organization_id == org_id,
        )
        .scalar()
        or 0
    )
    return int(total)


def check_rate_limits(
    user_id: int,
    org: Organization,
    db: Session,
) -> Optional[str]:
    """
    Check all rate limits for a user/org.
    Returns an error string if a limit is exceeded, else None.
    """
    plan = org.plan or "free"
    daily_limit = DAILY_QUERY_LIMITS.get(plan)
    monthly_limit = MONTHLY_TOKEN_BUDGETS.get(plan)

    # Daily query cap (Free tier only)
    if daily_limit is not None:
        daily_used = get_daily_query_count(user_id, db)
        if daily_used >= daily_limit:
            return (
                f"Daily query limit reached ({daily_limit} queries/day on {plan} plan). "
                "Upgrade to Pro for unlimited daily queries."
            )

    # Monthly token budget
    if monthly_limit is not None:
        monthly_used = get_monthly_tokens_used(org.id, db)
        if monthly_used >= monthly_limit:
            return (
                f"Monthly token budget exceeded ({monthly_limit:,} tokens on {plan} plan). "
                "Upgrade your plan or wait until next billing cycle."
            )

    return None


def get_usage_stats(user_id: int, org: Organization, db: Session) -> dict:
    """
    Get usage statistics for display in the UI.
    """
    plan = org.plan or "free"
    daily_limit = DAILY_QUERY_LIMITS.get(plan)
    monthly_limit = MONTHLY_TOKEN_BUDGETS.get(plan)

    daily_used = get_daily_query_count(user_id, db)
    monthly_used = get_monthly_tokens_used(org.id, db)

    return {
        "plan": plan,
        "daily_queries_used": daily_used,
        "daily_queries_limit": daily_limit,
        "monthly_tokens_used": monthly_used,
        "monthly_tokens_limit": monthly_limit,
    }
