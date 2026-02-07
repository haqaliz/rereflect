"""
Plan configuration for worker service.
Mirrors the feedback limits from backend-api/src/config/plans.py.
"""

from typing import Optional

FEEDBACK_LIMITS = {
    "free": 250,
    "pro": 2500,
    "business": 25000,
    "enterprise": None,  # Unlimited
}


def get_feedback_limit(plan_id: str) -> Optional[int]:
    """Get feedback limit for a plan. None means unlimited."""
    return FEEDBACK_LIMITS.get(plan_id, FEEDBACK_LIMITS["free"])
