"""Core feedback analyzer implementation."""
from typing import List, Dict, Optional
from datetime import datetime
from collections import defaultdict, Counter
import re

from .models import (
    FeedbackInput,
    AnalysisResult,
    PainPoint,
    FeatureRequest,
    SentimentSummary,
    SentimentByPeriod,
    CategorySentiment,
    UrgentFeedback,
    TopicCluster
)
from .sentiment import SentimentAnalyzer
from .extractors import PainPointExtractor, FeatureRequestExtractor
from .categorizer import PainPointCategorizer, FeatureRequestCategorizer, UrgentCategorizer


class FeedbackAnalyzer:
    """Main feedback analyzer orchestrating all analysis tasks."""

    def __init__(
        self,
        enable_clustering: bool = False,
        urgent_threshold: float = -0.7,
        very_negative_threshold: float = -0.5
    ):
        """
        Initialize the feedback analyzer.

        Args:
            enable_clustering: Whether to enable topic clustering
            urgent_threshold: Sentiment threshold for urgent feedback
            very_negative_threshold: Threshold for very negative sentiment
        """
        self.sentiment_analyzer = SentimentAnalyzer()
        self.pain_point_extractor = PainPointExtractor()
        self.feature_request_extractor = FeatureRequestExtractor()
        self.pain_point_categorizer = PainPointCategorizer()
        self.feature_request_categorizer = FeatureRequestCategorizer()
        self.urgent_categorizer = UrgentCategorizer()
        self.enable_clustering = enable_clustering
        self.urgent_threshold = urgent_threshold
        self.very_negative_threshold = very_negative_threshold

    def analyze(self, feedback_input: FeedbackInput) -> AnalysisResult:
        """
        Perform complete analysis on feedback data.

        Args:
            feedback_input: Input feedback data

        Returns:
            Complete analysis results
        """
        feedback_items = feedback_input.feedback

        if not feedback_items:
            return self._empty_result("No feedback items provided")

        # Add analysis note if dataset is small
        analysis_notes = None
        if len(feedback_items) < 20:
            analysis_notes = f"Note: Only {len(feedback_items)} feedback entries were analyzed. Insights may be limited due to small dataset size."

        # Step 1: Analyze sentiment for each feedback item
        enriched_feedback = self._enrich_with_sentiment(feedback_items)

        # Step 2: Extract pain points and complaints
        pain_points = self._analyze_pain_points(enriched_feedback)

        # Step 3: Extract feature requests
        feature_requests = self._analyze_feature_requests(enriched_feedback)

        # Step 4: Generate sentiment summary
        sentiment_summary = self._generate_sentiment_summary(enriched_feedback)

        # Step 5: Flag urgent feedback
        urgent_feedback = self._flag_urgent_feedback(enriched_feedback)

        # Step 6: Optional topic clustering
        topic_clusters = None
        if self.enable_clustering and len(feedback_items) >= 10:
            topic_clusters = self._perform_clustering(enriched_feedback)

        return AnalysisResult(
            common_pain_points=pain_points,
            feature_requests=feature_requests,
            sentiment_summary=sentiment_summary,
            urgent_feedback=urgent_feedback,
            topic_clusters=topic_clusters,
            analysis_notes=analysis_notes,
            total_feedback_count=len(feedback_items)
        )

    def _enrich_with_sentiment(self, feedback_items: List) -> List[Dict]:
        """Add sentiment analysis to each feedback item."""
        enriched = []

        for item in feedback_items:
            sentiment = self.sentiment_analyzer.analyze(item.text)

            enriched.append({
                'id': item.id,
                'text': item.text,
                'date': item.date,
                'source': item.source,
                'sentiment': sentiment
            })

        return enriched

    def _analyze_pain_points(self, enriched_feedback: List[Dict]) -> List[PainPoint]:
        """Extract and cluster pain points with categorization."""
        pain_points_data = self.pain_point_extractor.extract(enriched_feedback)

        # Convert to PainPoint models with categorization
        pain_points = []
        for pp in pain_points_data[:10]:  # Top 10
            # Categorize the pain point
            categorization = self.pain_point_categorizer.categorize(pp['issue'])

            pain_points.append(PainPoint(
                issue=pp['issue'],
                count=pp['count'],
                examples=pp['examples'],
                category=categorization.category,
                severity=categorization.level
            ))

        return pain_points

    def _analyze_feature_requests(self, enriched_feedback: List[Dict]) -> List[FeatureRequest]:
        """Extract and cluster feature requests with categorization."""
        feature_requests_data = self.feature_request_extractor.extract(enriched_feedback)

        # Convert to FeatureRequest models with categorization
        feature_requests = []
        for fr in feature_requests_data[:10]:  # Top 10
            # Categorize the feature request
            categorization = self.feature_request_categorizer.categorize(
                fr['feature'],
                occurrence_count=fr['count']
            )

            feature_requests.append(FeatureRequest(
                feature=fr['feature'],
                count=fr['count'],
                examples=fr['examples'],
                category=categorization.category,
                priority=categorization.level
            ))

        return feature_requests

    def _generate_sentiment_summary(self, enriched_feedback: List[Dict]) -> SentimentSummary:
        """Generate sentiment summary with trends and categories."""
        total = len(enriched_feedback)

        if total == 0:
            return SentimentSummary(
                positive_percent=0,
                neutral_percent=0,
                negative_percent=0
            )

        # Overall sentiment distribution
        positive_count = sum(1 for f in enriched_feedback if f['sentiment']['label'] == 'positive')
        negative_count = sum(1 for f in enriched_feedback if f['sentiment']['label'] == 'negative')
        neutral_count = total - positive_count - negative_count

        positive_percent = round((positive_count / total) * 100, 2)
        negative_percent = round((negative_count / total) * 100, 2)
        neutral_percent = round((neutral_count / total) * 100, 2)

        # Trend by month
        trend_by_month = self._calculate_sentiment_trend(enriched_feedback)

        # Category breakdown (if sources are available)
        by_category = self._calculate_category_sentiment(enriched_feedback)

        return SentimentSummary(
            positive_percent=positive_percent,
            neutral_percent=neutral_percent,
            negative_percent=negative_percent,
            trend_by_month=trend_by_month,
            by_category=by_category
        )

    def _calculate_sentiment_trend(self, enriched_feedback: List[Dict]) -> Dict[str, SentimentByPeriod]:
        """Calculate sentiment trend over time."""
        # Group by month
        monthly_data = defaultdict(list)

        for item in enriched_feedback:
            try:
                # Parse date (assume YYYY-MM-DD format)
                date_str = item['date']
                date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                month_key = date_obj.strftime('%Y-%m')

                monthly_data[month_key].append(item['sentiment'])
            except (ValueError, AttributeError):
                # Skip items with invalid dates
                continue

        # Calculate stats for each month
        trend = {}
        for month, sentiments in sorted(monthly_data.items()):
            total = len(sentiments)

            positive = sum(1 for s in sentiments if s['label'] == 'positive')
            negative = sum(1 for s in sentiments if s['label'] == 'negative')
            neutral = total - positive - negative

            avg_score = sum(s['compound'] for s in sentiments) / total if total > 0 else 0

            trend[month] = SentimentByPeriod(
                avg_score=round(avg_score, 3),
                negative_percent=round((negative / total) * 100, 2),
                positive_percent=round((positive / total) * 100, 2),
                neutral_percent=round((neutral / total) * 100, 2)
            )

        return trend

    def _calculate_category_sentiment(self, enriched_feedback: List[Dict]) -> Dict[str, CategorySentiment]:
        """Calculate sentiment by category/source."""
        category_data = defaultdict(list)

        for item in enriched_feedback:
            source = item.get('source', 'unknown')
            category_data[source].append(item['sentiment'])

        # Calculate stats for each category
        by_category = {}
        for category, sentiments in category_data.items():
            if len(sentiments) < 3:  # Skip categories with too few items
                continue

            total = len(sentiments)
            positive = sum(1 for s in sentiments if s['label'] == 'positive')
            negative = sum(1 for s in sentiments if s['label'] == 'negative')
            neutral = total - positive - negative

            by_category[category] = CategorySentiment(
                positive=round((positive / total) * 100, 2),
                neutral=round((neutral / total) * 100, 2),
                negative=round((negative / total) * 100, 2)
            )

        return by_category

    def _flag_urgent_feedback(self, enriched_feedback: List[Dict]) -> List[UrgentFeedback]:
        """Flag urgent or high-impact feedback."""
        urgent_items = []

        # Check for recent spike in issues
        recent_issues = self._detect_recent_spikes(enriched_feedback)

        for item in enriched_feedback:
            sentiment = item['sentiment']
            text = item['text']

            reasons = []

            # Check for extreme negative sentiment
            if sentiment['is_extreme']:
                reasons.append("Extreme negative sentiment detected")

            # Check sentiment threshold
            if sentiment['compound'] <= self.urgent_threshold:
                reasons.append("Very low sentiment score")

            # Check for churn risk
            if sentiment['churn_risk']:
                reasons.append("Customer churn risk")

            # Check for critical keywords
            if self._has_critical_issue(text):
                reasons.append("Critical functionality issue")

            # Check if part of recent spike
            issue_type = self._categorize_issue(text)
            if issue_type in recent_issues:
                reasons.append(f"Part of recent spike in {issue_type} issues")

            # If any reasons flagged, add to urgent list
            if reasons:
                # Categorize the urgent feedback
                categorization = self.urgent_categorizer.categorize(
                    text,
                    sentiment_score=sentiment['compound']
                )

                urgent_items.append(UrgentFeedback(
                    id=item['id'],
                    issue=self._extract_issue_summary(text),
                    reason='; '.join(reasons),
                    sentiment=self.sentiment_analyzer.classify_intensity(sentiment['compound']),
                    text_excerpt=text[:150] + '...' if len(text) > 150 else text,
                    category=categorization.category,
                    response_time=categorization.level
                ))

        # Sort by response_time urgency (immediate first) then by sentiment
        response_time_priority = {'immediate': 0, '1_hour': 1, '4_hours': 2, '24_hours': 3}
        urgent_items.sort(
            key=lambda x: (
                response_time_priority.get(x.response_time, 4),
                0 if x.sentiment == 'very negative' else 1
            )
        )

        return urgent_items[:20]  # Return top 20 urgent items

    def _has_critical_issue(self, text: str) -> bool:
        """Check if text mentions critical issues."""
        critical_patterns = [
            r'\b(data\s+loss|lost\s+data|deleted|corrupt)\b',
            r'\b(security|breach|hack|vulnerability)\b',
            r'\b(payment\s+fail|charge|double\s+charged)\b',
            r'\b(login|sign\s+in|authentication)\s+(?:not\s+work|fail|broken)',
            r'\b(complete(?:ly)?\s+(?:broken|down)|not\s+accessible)\b',
        ]

        text_lower = text.lower()
        for pattern in critical_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True

        return False

    def _categorize_issue(self, text: str) -> str:
        """Categorize issue type for spike detection."""
        text_lower = text.lower()

        if 'login' in text_lower or 'sign in' in text_lower:
            return 'login'
        elif 'payment' in text_lower or 'billing' in text_lower:
            return 'payment'
        elif 'crash' in text_lower:
            return 'crash'
        elif 'slow' in text_lower or 'lag' in text_lower:
            return 'performance'
        elif 'upload' in text_lower:
            return 'upload'
        else:
            return 'other'

    def _detect_recent_spikes(self, enriched_feedback: List[Dict], days: int = 7) -> set:
        """Detect recent spikes in specific issue types."""
        # Group by date and issue type
        recent_cutoff = datetime.now()

        recent_issues = defaultdict(int)
        older_issues = defaultdict(int)

        for item in enriched_feedback:
            try:
                date_obj = datetime.fromisoformat(item['date'].replace('Z', '+00:00'))
                days_ago = (recent_cutoff - date_obj).days

                issue_type = self._categorize_issue(item['text'])

                if days_ago <= days:
                    recent_issues[issue_type] += 1
                else:
                    older_issues[issue_type] += 1
            except (ValueError, AttributeError):
                continue

        # Find spikes (more than 3x increase)
        spikes = set()
        for issue_type, recent_count in recent_issues.items():
            if recent_count >= 5:  # At least 5 occurrences
                older_count = older_issues.get(issue_type, 0)
                if older_count == 0 or recent_count > older_count * 3:
                    spikes.add(issue_type)

        return spikes

    def _extract_issue_summary(self, text: str) -> str:
        """Extract short issue summary from text."""
        # Take first sentence or 80 chars
        first_sentence = re.split(r'[.!?]', text)[0].strip()

        if len(first_sentence) > 80:
            return first_sentence[:77] + '...'

        return first_sentence

    def _perform_clustering(self, enriched_feedback: List[Dict]) -> List[TopicCluster]:
        """Perform topic clustering using BERTopic (optional advanced feature)."""
        try:
            from bertopic import BERTopic
            from sklearn.feature_extraction.text import CountVectorizer

            # Prepare documents
            documents = [item['text'] for item in enriched_feedback]

            # Configure BERTopic
            vectorizer = CountVectorizer(stop_words='english', min_df=2)

            topic_model = BERTopic(
                vectorizer_model=vectorizer,
                min_topic_size=3,
                nr_topics='auto'
            )

            # Fit model
            topics, probs = topic_model.fit_transform(documents)

            # Extract topic clusters
            topic_info = topic_model.get_topic_info()

            clusters = []
            for idx, row in topic_info.iterrows():
                if row['Topic'] == -1:  # Skip outlier topic
                    continue

                topic_id = row['Topic']
                topic_words = topic_model.get_topic(topic_id)

                # Get representative documents
                topic_docs = [i for i, t in enumerate(topics) if t == topic_id]

                if not topic_docs:
                    continue

                # Generate topic label from top words
                keywords = [word for word, _ in topic_words[:5]]
                topic_label = ' '.join(keywords).title()

                clusters.append(TopicCluster(
                    topic=topic_label,
                    count=len(topic_docs),
                    representative_feedback_ids=[enriched_feedback[i]['id'] for i in topic_docs[:5]],
                    keywords=keywords
                ))

            return clusters[:10]  # Top 10 clusters

        except ImportError:
            # BERTopic not available, return None
            return None
        except Exception as e:
            # Clustering failed, return None
            print(f"Clustering failed: {e}")
            return None

    def _empty_result(self, note: str) -> AnalysisResult:
        """Return empty result with note."""
        return AnalysisResult(
            sentiment_summary=SentimentSummary(
                positive_percent=0,
                neutral_percent=0,
                negative_percent=0
            ),
            analysis_notes=note,
            total_feedback_count=0
        )
