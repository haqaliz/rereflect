"""
AI correction service — shared helper for persisting human-in-the-loop
correction/rating signals.

Extracted from the internal ``POST /api/v1/ai-corrections`` route so that both
the internal route and the public write API create corrections identically.
"""
from typing import Optional

from sqlalchemy.orm import Session

from src.models.ai_correction import AICorrection


def create_ai_correction(
    db: Session,
    *,
    organization_id: int,
    user_id: Optional[int],
    correction_type: str,
    entity_type: str,
    entity_id: Optional[int] = None,
    signal: str,
    original_value: Optional[str] = None,
    corrected_value: Optional[str] = None,
    feedback_text: Optional[str] = None,
) -> AICorrection:
    """Persist an ``AICorrection`` and return the refreshed row.

    ``user_id`` may be ``None`` for API-key writes (the FK is nullable).
    Commits internally, mirroring the original route behavior.
    """
    correction = AICorrection(
        organization_id=organization_id,
        user_id=user_id,
        correction_type=correction_type,
        entity_type=entity_type,
        entity_id=entity_id,
        signal=signal,
        original_value=original_value,
        corrected_value=corrected_value,
        feedback_text=feedback_text,
    )
    db.add(correction)
    db.commit()
    db.refresh(correction)
    return correction
