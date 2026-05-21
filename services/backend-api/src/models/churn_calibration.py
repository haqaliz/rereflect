"""
ChurnCalibrationModel + ChurnBacktestRun — SQLAlchemy models (M4.1).

ChurnCalibrationModel: versioned isotonic regression models.
  - organization_id=NULL → global fallback model.
  - At most one active model per organization (enforced via partial unique index).

ChurnBacktestRun: weekly refit observability history.
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
    Text,
    text,
)
from sqlalchemy.orm import relationship

from .base import Base


class ChurnCalibrationModel(Base):
    """Versioned isotonic calibration model — one global + one per org."""

    __tablename__ = "churn_calibration_models"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,  # NULL = global fallback
    )

    model_json = Column(JSON, nullable=False)  # isotonic regression parameters
    label_count = Column(Integer, nullable=False)
    positive_count = Column(Integer, nullable=False)  # # churn=True labels

    # Accuracy metrics — NULL until first backtest
    precision = Column(Numeric(5, 4), nullable=True)
    recall = Column(Numeric(5, 4), nullable=True)
    f1 = Column(Numeric(5, 4), nullable=True)
    auc = Column(Numeric(5, 4), nullable=True)

    # {"low": 0.30, "medium": 0.50, "high": 0.70, "critical": 0.85}
    threshold_bands = Column(JSON, nullable=False)

    fit_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, nullable=False, default=False)

    # Relationships
    organization = relationship("Organization")
    backtest_runs = relationship(
        "ChurnBacktestRun",
        back_populates="calibration_model",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_churn_cal_model_org_fit", "organization_id", "fit_at"),
        # Partial unique index: at most one active model per org_id value
        # (works on both PostgreSQL and SQLite via sqlite_where)
        Index(
            "uq_churn_cal_model_one_active_per_org",
            "organization_id",
            unique=True,
            sqlite_where=text("is_active = 1"),
            postgresql_where=text("is_active = TRUE"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ChurnCalibrationModel(id={self.id}, org={self.organization_id}, "
            f"active={self.is_active}, labels={self.label_count})>"
        )


class ChurnBacktestRun(Base):
    """Weekly refit observability — history of every calibration run."""

    __tablename__ = "churn_backtest_runs"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,  # NULL = global run
    )
    calibration_model_id = Column(
        Integer,
        ForeignKey("churn_calibration_models.id", ondelete="CASCADE"),
        nullable=False,
    )

    run_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    label_count = Column(Integer, nullable=False)

    precision = Column(Numeric(5, 4), nullable=True)
    recall = Column(Numeric(5, 4), nullable=True)
    f1 = Column(Numeric(5, 4), nullable=True)
    auc = Column(Numeric(5, 4), nullable=True)
    optimal_threshold = Column(Numeric(5, 4), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)  # e.g. "insufficient labels, fell back to global"

    # Relationships
    organization = relationship("Organization")
    calibration_model = relationship("ChurnCalibrationModel", back_populates="backtest_runs")

    __table_args__ = (
        Index("ix_churn_backtest_org_run_at", "organization_id", "run_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<ChurnBacktestRun(id={self.id}, org={self.organization_id}, "
            f"run_at={self.run_at}, f1={self.f1})>"
        )
