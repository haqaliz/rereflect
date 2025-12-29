"""Data models for feedback analysis."""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class FeedbackItem(BaseModel):
    """Single feedback entry."""
    id: str
    text: str
    date: str
    source: Optional[str] = None


class FeedbackInput(BaseModel):
    """Input payload containing feedback entries."""
    feedback: List[FeedbackItem]


class PainPoint(BaseModel):
    """Identified pain point or complaint."""
    issue: str
    count: int
    examples: List[str] = Field(default_factory=list)
    category: Optional[str] = None  # security_breach, data_loss, payment_issue, etc.
    severity: Optional[str] = None  # critical, major, moderate, minor, trivial


class FeatureRequest(BaseModel):
    """Identified feature request."""
    feature: str
    count: int
    examples: List[str] = Field(default_factory=list)
    category: Optional[str] = None  # core_functionality, automation, integration, etc.
    priority: Optional[str] = None  # high, medium, low


class SentimentByPeriod(BaseModel):
    """Sentiment metrics for a time period."""
    avg_score: float
    negative_percent: float
    positive_percent: float
    neutral_percent: float


class CategorySentiment(BaseModel):
    """Sentiment breakdown for a category."""
    positive: float
    neutral: float
    negative: float


class SentimentSummary(BaseModel):
    """Overall sentiment analysis results."""
    positive_percent: float
    neutral_percent: float
    negative_percent: float
    trend_by_month: Dict[str, SentimentByPeriod] = Field(default_factory=dict)
    by_category: Dict[str, CategorySentiment] = Field(default_factory=dict)


class UrgentFeedback(BaseModel):
    """Flagged urgent feedback item."""
    id: str
    issue: str
    reason: str
    sentiment: str
    text_excerpt: Optional[str] = None
    category: Optional[str] = None  # service_outage, data_breach, payment_failure, etc.
    response_time: Optional[str] = None  # immediate, 1_hour, 4_hours, 24_hours


class TopicCluster(BaseModel):
    """Identified topic cluster."""
    topic: str
    count: int
    representative_feedback_ids: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    """Complete analysis output."""
    common_pain_points: List[PainPoint] = Field(default_factory=list)
    feature_requests: List[FeatureRequest] = Field(default_factory=list)
    sentiment_summary: SentimentSummary
    urgent_feedback: List[UrgentFeedback] = Field(default_factory=list)
    topic_clusters: Optional[List[TopicCluster]] = None
    analysis_notes: Optional[str] = None
    total_feedback_count: int = 0
    analysis_timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
