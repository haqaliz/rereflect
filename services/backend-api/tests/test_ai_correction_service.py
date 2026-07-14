"""
Characterization + behavior tests for `create_ai_correction`
(src/services/ai_correction_service.py).

Locks the current (pre-bulk) default behavior — commits internally — before
adding an optional `commit: bool = True` param for the bulk-write handler.
"""

from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.models.ai_correction import AICorrection
from src.models.base import Base
from src.models.organization import Organization
from src.services.ai_correction_service import create_ai_correction

_SQLITE_URL = "sqlite:///:memory:"
_engine = create_engine(
    _SQLITE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture(scope="function")
def db() -> Generator[Session, None, None]:
    Base.metadata.create_all(bind=_engine)
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


@pytest.fixture
def org(db: Session) -> Organization:
    o = Organization(name="Acme Corp", plan="pro")
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


class TestCreateAiCorrectionDefaultCommits:
    def test_default_commits_row_is_durable(self, db: Session, org: Organization):
        """Default (no `commit` kwarg) behavior: the row is committed and
        visible via a fresh query with no explicit db.commit() by the caller."""
        create_ai_correction(
            db,
            organization_id=org.id,
            user_id=None,
            correction_type="category",
            entity_type="feedback_item",
            entity_id=1,
            signal="correction",
            original_value="old",
            corrected_value="new",
            feedback_text="some text",
        )

        # Prove durability: roll back any pending (uncommitted) session state,
        # then re-query. If the row was truly committed, it survives.
        db.rollback()
        rows = db.query(AICorrection).filter(AICorrection.entity_id == 1).all()
        assert len(rows) == 1
        assert rows[0].corrected_value == "new"

    def test_explicit_commit_true_same_as_default(self, db: Session, org: Organization):
        create_ai_correction(
            db,
            organization_id=org.id,
            user_id=None,
            correction_type="category",
            entity_type="feedback_item",
            entity_id=2,
            signal="correction",
            original_value="old",
            corrected_value="new",
            feedback_text="some text",
            commit=True,
        )
        db.rollback()
        rows = db.query(AICorrection).filter(AICorrection.entity_id == 2).all()
        assert len(rows) == 1


class TestCreateAiCorrectionCommitFalse:
    def test_commit_false_does_not_commit_row_rolled_back_if_session_rolls_back(
        self, db: Session, org: Organization
    ):
        """commit=False: row is visible in-session (flushed) but NOT durable —
        a session rollback wipes it out."""
        row = create_ai_correction(
            db,
            organization_id=org.id,
            user_id=None,
            correction_type="category",
            entity_type="feedback_item",
            entity_id=3,
            signal="correction",
            original_value="old",
            corrected_value="new",
            feedback_text="some text",
            commit=False,
        )
        assert row.id is not None  # flushed, visible in-session

        # Visible within the same uncommitted transaction.
        in_session = db.query(AICorrection).filter(AICorrection.entity_id == 3).all()
        assert len(in_session) == 1

        # Roll back the outer transaction — since create_ai_correction did NOT
        # commit, the row must be gone.
        db.rollback()
        after_rollback = db.query(AICorrection).filter(AICorrection.entity_id == 3).all()
        assert len(after_rollback) == 0

    def test_commit_false_then_caller_commits_persists(self, db: Session, org: Organization):
        create_ai_correction(
            db,
            organization_id=org.id,
            user_id=None,
            correction_type="category",
            entity_type="feedback_item",
            entity_id=4,
            signal="correction",
            original_value="old",
            corrected_value="new",
            feedback_text="some text",
            commit=False,
        )
        db.commit()

        db.rollback()  # no-op — already committed
        rows = db.query(AICorrection).filter(AICorrection.entity_id == 4).all()
        assert len(rows) == 1
