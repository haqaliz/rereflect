# Usage Guide

Complete guide to using the Customer Feedback Analyzer.

## Table of Contents

- [Quick Start](#quick-start)
- [Python Module Usage](#python-module-usage)
- [API Usage](#api-usage)
- [Understanding Results](#understanding-results)
- [Advanced Features](#advanced-features)
- [Integration Examples](#integration-examples)

## Quick Start

### 1. Analyze Sample Data

```bash
python examples/usage_example.py
```

This will analyze 30 sample feedback entries and display:
- Sentiment distribution
- Top pain points
- Feature requests
- Urgent feedback items

### 2. Start API Server

```bash
python -m src.api.main
```

### 3. View API Documentation

Open browser: `http://localhost:8000/docs`

## Python Module Usage

### Basic Analysis

```python
from src.analyzer import FeedbackAnalyzer, FeedbackInput, FeedbackItem

# Create feedback data
feedback_input = FeedbackInput(feedback=[
    FeedbackItem(
        id="1",
        text="The app crashes when uploading files",
        date="2025-11-10",
        source="support_ticket"
    ),
    FeedbackItem(
        id="2",
        text="Would love to see dark mode!",
        date="2025-11-11",
        source="feature_request"
    )
])

# Initialize analyzer
analyzer = FeedbackAnalyzer()

# Perform analysis
result = analyzer.analyze(feedback_input)

# Access results
print(f"Sentiment: {result.sentiment_summary.negative_percent}% negative")
print(f"Pain points found: {len(result.common_pain_points)}")
print(f"Feature requests: {len(result.feature_requests)}")
```

### With Topic Clustering

```python
analyzer = FeedbackAnalyzer(enable_clustering=True)
result = analyzer.analyze(feedback_input)

# Access topic clusters
for cluster in result.topic_clusters:
    print(f"{cluster.topic}: {cluster.count} items")
    print(f"Keywords: {', '.join(cluster.keywords)}")
```

### Custom Thresholds

```python
analyzer = FeedbackAnalyzer(
    urgent_threshold=-0.8,  # More strict urgent flagging
    very_negative_threshold=-0.6
)
```

### Loading from JSON File

```python
import json

# Load feedback from JSON
with open('feedback_data.json', 'r') as f:
    data = json.load(f)

feedback_input = FeedbackInput(**data)
result = analyzer.analyze(feedback_input)
```

### Saving Results

```python
import json

# Save to JSON
with open('analysis_results.json', 'w') as f:
    json.dump(result.model_dump(), f, indent=2)
```

## API Usage

### Using curl

#### Full Analysis

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "feedback": [
      {
        "id": "1",
        "text": "App crashes on upload",
        "date": "2025-11-10",
        "source": "support_ticket"
      }
    ]
  }'
```

#### Quick Analysis (Summary Only)

```bash
curl -X POST http://localhost:8000/api/v1/analyze/quick \
  -H "Content-Type: application/json" \
  -d @examples/sample_data.json
```

### Using Python Requests

```python
import requests
import json

# Load feedback data
with open('examples/sample_data.json', 'r') as f:
    data = json.load(f)

# Send to API
response = requests.post(
    'http://localhost:8000/api/v1/analyze',
    json=data
)

result = response.json()

# Access results
print(f"Total feedback: {result['total_feedback_count']}")
print(f"Top pain point: {result['common_pain_points'][0]['issue']}")
```

### Using JavaScript/TypeScript

```javascript
const response = await fetch('http://localhost:8000/api/v1/analyze', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    feedback: [
      {
        id: '1',
        text: 'App crashes when uploading',
        date: '2025-11-10',
        source: 'support_ticket'
      }
    ]
  })
});

const result = await response.json();
console.log('Sentiment:', result.sentiment_summary);
```

## Understanding Results

### Result Structure

```json
{
  "common_pain_points": [
    {
      "issue": "App crashes on upload",
      "count": 5,
      "examples": ["Example feedback text..."]
    }
  ],
  "feature_requests": [
    {
      "feature": "Dark mode",
      "count": 7,
      "examples": ["User wants dark mode..."]
    }
  ],
  "sentiment_summary": {
    "positive_percent": 15.0,
    "neutral_percent": 20.0,
    "negative_percent": 65.0,
    "trend_by_month": {
      "2025-11": {
        "avg_score": -0.3,
        "negative_percent": 60.0,
        "positive_percent": 20.0,
        "neutral_percent": 20.0
      }
    },
    "by_category": {
      "support_ticket": {
        "positive": 5.0,
        "neutral": 10.0,
        "negative": 85.0
      }
    }
  },
  "urgent_feedback": [
    {
      "id": "12345",
      "issue": "Cannot login to account",
      "reason": "Customer churn risk; Very low sentiment score",
      "sentiment": "very negative",
      "text_excerpt": "I'm canceling if this isn't fixed..."
    }
  ],
  "topic_clusters": [
    {
      "topic": "Performance Issues",
      "count": 10,
      "representative_feedback_ids": ["1", "3", "7"],
      "keywords": ["slow", "lag", "performance"]
    }
  ],
  "analysis_notes": "Note: Analysis completed successfully",
  "total_feedback_count": 30,
  "analysis_timestamp": "2025-11-27T10:30:00"
}
```

### Interpreting Sentiment Scores

- **Compound Score**: -1.0 (most negative) to +1.0 (most positive)
- **Positive**: Compound >= 0.05
- **Neutral**: -0.05 < Compound < 0.05
- **Negative**: Compound <= -0.05

### Sentiment Intensity Levels

- **Very Positive**: Compound >= 0.5
- **Positive**: 0.05 <= Compound < 0.5
- **Neutral**: -0.05 < Compound < 0.05
- **Negative**: -0.5 < Compound <= -0.05
- **Very Negative**: Compound <= -0.5

### Urgent Feedback Flags

Feedback is flagged as urgent when:

1. **Extreme negative sentiment** (all caps, multiple exclamation marks, strong negative words)
2. **Sentiment score below threshold** (default: -0.7)
3. **Churn risk detected** (mentions of canceling, switching, etc.)
4. **Critical functionality issues** (data loss, security, payment failures)
5. **Recent spike in similar issues** (5+ reports in past week)

## Advanced Features

### Topic Clustering with BERTopic

Enable advanced topic clustering:

```python
analyzer = FeedbackAnalyzer(enable_clustering=True)
result = analyzer.analyze(feedback_input)

# Explore topics
for cluster in result.topic_clusters:
    print(f"\nTopic: {cluster.topic}")
    print(f"Size: {cluster.count} feedback items")
    print(f"Keywords: {', '.join(cluster.keywords[:5])}")
    print(f"Example IDs: {cluster.representative_feedback_ids[:3]}")
```

**Note:** Topic clustering requires:
- At least 10 feedback items
- More computational resources
- BERTopic dependencies installed

### Sentiment Trend Analysis

Analyze sentiment changes over time:

```python
result = analyzer.analyze(feedback_input)

for month, trend in result.sentiment_summary.trend_by_month.items():
    print(f"\n{month}:")
    print(f"  Average score: {trend.avg_score:.2f}")
    print(f"  Negative: {trend.negative_percent}%")
    print(f"  Positive: {trend.positive_percent}%")
```

### Category-Based Analysis

Analyze sentiment by feedback source:

```python
for category, sentiment in result.sentiment_summary.by_category.items():
    print(f"\n{category}:")
    print(f"  Positive: {sentiment.positive}%")
    print(f"  Negative: {sentiment.negative}%")
```

## Integration Examples

### Slack Notification Integration

```python
import requests
from src.analyzer import FeedbackAnalyzer, FeedbackInput

def send_to_slack(result):
    """Send urgent feedback to Slack."""
    webhook_url = "YOUR_SLACK_WEBHOOK_URL"

    for urgent in result.urgent_feedback[:5]:  # Top 5
        message = {
            "text": f"🚨 Urgent Feedback Alert",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Issue:* {urgent.issue}\n*Reason:* {urgent.reason}\n*Sentiment:* {urgent.sentiment}"
                    }
                }
            ]
        }
        requests.post(webhook_url, json=message)

# Analyze and send alerts
analyzer = FeedbackAnalyzer()
result = analyzer.analyze(feedback_input)
send_to_slack(result)
```

### Dashboard Data Feed

```python
def prepare_dashboard_data(result):
    """Prepare data for dashboard visualization."""
    return {
        "summary": {
            "total": result.total_feedback_count,
            "sentiment": {
                "positive": result.sentiment_summary.positive_percent,
                "neutral": result.sentiment_summary.neutral_percent,
                "negative": result.sentiment_summary.negative_percent
            }
        },
        "top_issues": [
            {"label": pp.issue, "count": pp.count}
            for pp in result.common_pain_points[:5]
        ],
        "top_requests": [
            {"label": fr.feature, "count": fr.count}
            for fr in result.feature_requests[:5]
        ],
        "alerts": len(result.urgent_feedback)
    }
```

### Email Report Generation

```python
def generate_email_report(result):
    """Generate HTML email report."""
    html = f"""
    <h2>Feedback Analysis Report</h2>
    <p><strong>Total Feedback:</strong> {result.total_feedback_count}</p>

    <h3>Sentiment Overview</h3>
    <ul>
      <li>Positive: {result.sentiment_summary.positive_percent}%</li>
      <li>Neutral: {result.sentiment_summary.neutral_percent}%</li>
      <li>Negative: {result.sentiment_summary.negative_percent}%</li>
    </ul>

    <h3>Top Pain Points</h3>
    <ol>
      {"".join(f"<li>{pp.issue} ({pp.count} mentions)</li>" for pp in result.common_pain_points[:5])}
    </ol>

    <h3>Top Feature Requests</h3>
    <ol>
      {"".join(f"<li>{fr.feature} ({fr.count} requests)</li>" for fr in result.feature_requests[:5])}
    </ol>

    <h3>Urgent Items: {len(result.urgent_feedback)}</h3>
    """
    return html
```

### Scheduled Analysis (Cron Job)

```python
#!/usr/bin/env python
"""
Scheduled feedback analysis script.
Run daily via cron: 0 9 * * * /path/to/venv/bin/python /path/to/scheduled_analysis.py
"""

import json
from datetime import datetime, timedelta
from src.analyzer import FeedbackAnalyzer, FeedbackInput

def fetch_recent_feedback():
    """Fetch feedback from last 24 hours (implement your data source)."""
    # Example: Query database, fetch from API, etc.
    pass

def main():
    # Fetch recent feedback
    feedback_data = fetch_recent_feedback()
    feedback_input = FeedbackInput(**feedback_data)

    # Analyze
    analyzer = FeedbackAnalyzer()
    result = analyzer.analyze(feedback_input)

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d")
    with open(f'daily_analysis_{timestamp}.json', 'w') as f:
        json.dump(result.model_dump(), f, indent=2)

    # Send alerts if urgent items found
    if result.urgent_feedback:
        send_alerts(result.urgent_feedback)

if __name__ == '__main__':
    main()
```

## Best Practices

1. **Batch Processing**: Process feedback in batches of 100-500 items for optimal performance
2. **Regular Analysis**: Run analysis daily or weekly for trend tracking
3. **Urgent Monitoring**: Set up real-time alerts for urgent feedback
4. **Data Quality**: Clean and standardize feedback text before analysis
5. **Threshold Tuning**: Adjust sentiment thresholds based on your specific use case
6. **Resource Management**: Disable clustering for large datasets if resources are limited

## Troubleshooting

### Poor Clustering Results

- Increase minimum feedback count (need 20+ items)
- Ensure feedback has diverse topics
- Check feedback text quality (remove spam, very short entries)

### Inaccurate Sentiment

- Review sentiment thresholds
- Check for sarcasm (may be misclassified)
- Consider domain-specific sentiment lexicon

### Missing Pain Points

- Check if feedback is truly negative
- Review extraction patterns
- Lower clustering similarity threshold

## Next Steps

- See [API.md](API.md) for detailed API reference
- Review [ARCHITECTURE.md](ARCHITECTURE.md) for system design
- Check [examples/](examples/) for more code samples
