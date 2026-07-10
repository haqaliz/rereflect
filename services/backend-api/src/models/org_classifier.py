"""
OrgClassifierModel + OrgClassifierEvalRun — SQLAlchemy models (M5.2).

OrgClassifierModel: versioned per-org corrections classifier artifact
  (TF-IDF vocab/idf + logreg coef/intercept + classes — JSON, never pickle).
  - organization_id=NULL → global/base model.
  - At most one active model per (organization_id, classifier_type)
    (enforced via partial unique index).

OrgClassifierEvalRun: shadow-mode A/B eval history (incumbent vs challenger).
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import relationship

from .base import Base


class OrgClassifierModel(Base):
    """Versioned per-org corrections classifier artifact — one global + one per org+type."""

    __tablename__ = "org_classifier_models"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,  # NULL = global/base model
    )
    classifier_type = Column(String(30), nullable=False)  # v1: 'sentiment'

    model_json = Column(JSON, nullable=False)  # tfidf vocab/idf + logreg coef/intercept + classes — NO pickle
    label_count = Column(Integer, nullable=False)

    # Accuracy metrics — NULL until first eval
    precision = Column(Numeric(5, 4), nullable=True)
    recall = Column(Numeric(5, 4), nullable=True)
    macro_f1 = Column(Numeric(5, 4), nullable=True)
    accuracy = Column(Numeric(5, 4), nullable=True)

    fit_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, nullable=False, default=False)

    # Relationships
    organization = relationship("Organization")
    eval_runs = relationship(
        "OrgClassifierEvalRun",
        back_populates="classifier_model",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_org_classifier_model_org_type_fit", "organization_id", "classifier_type", "fit_at"),
        # Partial unique index: at most one active model per (org_id, classifier_type) pair
        # (works on both PostgreSQL and SQLite via sqlite_where)
        Index(
            "uq_org_classifier_one_active",
            "organization_id",
            "classifier_type",
            unique=True,
            sqlite_where=text("is_active = 1"),
            postgresql_where=text("is_active = TRUE"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<OrgClassifierModel(id={self.id}, org={self.organization_id}, "
            f"type='{self.classifier_type}', active={self.is_active}, labels={self.label_count})>"
        )


class OrgClassifierEvalRun(Base):
    """Shadow-mode A/B eval history — incumbent vs challenger, one row per run."""

    __tablename__ = "org_classifier_eval_runs"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,  # NULL = global run
    )
    classifier_model_id = Column(
        Integer,
        ForeignKey("org_classifier_models.id", ondelete="CASCADE"),
        nullable=True,
    )
    classifier_type = Column(String(30), nullable=False)

    incumbent_macro_f1 = Column(Numeric(5, 4), nullable=True)
    challenger_macro_f1 = Column(Numeric(5, 4), nullable=True)
    macro_f1_delta = Column(Numeric(5, 4), nullable=True)
    decision = Column(String(20), nullable=False)  # promoted | retained | skipped
    n = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    organization = relationship("Organization")
    classifier_model = relationship("OrgClassifierModel", back_populates="eval_runs")

    __table_args__ = (
        Index("ix_org_classifier_eval_org_type_created", "organization_id", "classifier_type", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<OrgClassifierEvalRun(id={self.id}, org={self.organization_id}, "
            f"type='{self.classifier_type}', decision='{self.decision}')>"
        )
