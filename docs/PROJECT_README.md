# Customer Feedback Analyzer

AI-powered customer feedback analysis system for SaaS and app businesses. Transforms unstructured feedback into actionable insights.

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.0-009688.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

This system analyzes customer feedback to identify:

- **Pain Points & Complaints**: Automatically detects and clusters common issues
- **Feature Requests**: Identifies what customers want
- **Sentiment Analysis**: Tracks sentiment trends over time and by category
- **Urgent Feedback**: Flags critical issues and churn risks
- **Topic Clustering**: Groups feedback by themes (optional)

### Key Features

- Fast sentiment analysis using VADER
- Intelligent clustering of similar feedback
- Pattern recognition for complaints and feature requests
- Urgent feedback detection (churn risk, critical bugs)
- RESTful API with FastAPI
- Optional advanced topic modeling with BERTopic
- Comprehensive test suite
- Production-ready architecture

## Quick Start

### Installation

```bash
# Clone repository
cd /home/aliz/dev/at/customer-feedback-analyzer

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Download NLTK data
python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"
```

### Run Example Analysis

```bash
python examples/usage_example.py
```

### Start API Server

```bash
python -m src.api.main
```

Visit `http://localhost:8000/docs` for interactive API documentation.

## Project Structure

```
customer-feedback-analyzer/
├── src/
│   ├── analyzer/
│   │   ├── core.py           # Main analyzer orchestration
│   │   ├── sentiment.py      # Sentiment analysis (VADER)
│   │   ├── extractors.py     # Pain points & feature requests
│   │   └── models.py         # Pydantic data models
│   └── api/
│       └── main.py           # FastAPI application
├── tests/
│   ├── test_analyzer.py      # Core analyzer tests
│   ├── test_sentiment.py     # Sentiment tests
│   ├── test_extractors.py    # Extractor tests
│   └── test_api.py           # API endpoint tests
├── examples/
│   ├── sample_data.json      # Sample feedback data
│   ├── usage_example.py      # Python module usage
│   └── api_example.py        # API client example
├── requirements.txt          # Python dependencies
├── .env.example             # Environment configuration template
├── SETUP.md                 # Detailed setup guide
├── USAGE.md                 # Usage documentation
└── API.md                   # API reference
```

## Usage Examples

### Python Module

```python
from src.analyzer import FeedbackAnalyzer, FeedbackInput, FeedbackItem

# Create feedback data
feedback = FeedbackInput(feedback=[
    FeedbackItem(
        id="1",
        text="App crashes when uploading files",
        date="2025-11-10",
        source="support_ticket"
    )
])

# Analyze
analyzer = FeedbackAnalyzer()
result = analyzer.analyze(feedback)

# Access results
print(f"Sentiment: {result.sentiment_summary.negative_percent}% negative")
print(f"Pain points: {len(result.common_pain_points)}")
print(f"Urgent items: {len(result.urgent_feedback)}")
```

### API (curl)

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

### API (Python)

```python
import requests

response = requests.post(
    'http://localhost:8000/api/v1/analyze',
    json={"feedback": [...]}
)

result = response.json()
```

## Analysis Output

The analyzer returns comprehensive insights:

```json
{
  "common_pain_points": [
    {
      "issue": "App crashes on file upload",
      "count": 5,
      "examples": ["The app crashes when I upload..."]
    }
  ],
  "feature_requests": [
    {
      "feature": "Dark mode",
      "count": 7,
      "examples": ["Would love dark mode..."]
    }
  ],
  "sentiment_summary": {
    "positive_percent": 15.0,
    "neutral_percent": 20.0,
    "negative_percent": 65.0,
    "trend_by_month": {...},
    "by_category": {...}
  },
  "urgent_feedback": [
    {
      "id": "12345",
      "issue": "Cannot login to account",
      "reason": "Customer churn risk; Critical functionality issue",
      "sentiment": "very negative"
    }
  ],
  "total_feedback_count": 30
}
```

## Key Capabilities

### 1. Pain Point Detection

Automatically identifies and clusters customer complaints:

- Pattern recognition for problem indicators
- Similarity-based clustering
- Frequency ranking
- Example quotes included

### 2. Feature Request Extraction

Detects and groups feature requests:

- Request pattern detection ("wish", "need", "please add")
- Intelligent clustering of similar requests
- Prioritization by frequency

### 3. Sentiment Analysis

Comprehensive sentiment tracking:

- VADER-based sentiment scoring
- Positive/neutral/negative classification
- Intensity levels (very positive to very negative)
- Trend analysis over time
- Category-based breakdown

### 4. Urgent Feedback Flagging

Identifies critical items requiring immediate attention:

- Extreme negative sentiment detection
- Churn risk indicators (cancellation threats)
- Critical bug patterns (data loss, security)
- Recent issue spike detection
- Multiple urgency criteria

### 5. Topic Clustering (Optional)

Advanced thematic analysis using BERTopic:

- Unsupervised topic discovery
- Keyword extraction
- Representative examples
- Semantic similarity grouping

## Configuration

Edit `.env` file:

```bash
# API Settings
API_HOST=0.0.0.0
API_PORT=8000

# Analysis Settings
ENABLE_CLUSTERING=false  # Enable topic clustering
MIN_CLUSTER_SIZE=3
MAX_CLUSTERS=10

# Sentiment Thresholds
URGENT_SENTIMENT_THRESHOLD=-0.7      # Flag as urgent below this
VERY_NEGATIVE_THRESHOLD=-0.5         # Very negative classification
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_analyzer.py

# Verbose output
pytest -v
```

## Performance

- **Quick Analysis**: < 1 second for 100 items
- **Full Analysis**: 2-5 seconds for 100 items (without clustering)
- **With Clustering**: 10-30 seconds for 100 items
- **Recommended Batch Size**: 100-500 items per request

## Use Cases

### 1. Product Teams

- Identify top customer pain points
- Prioritize feature roadmap based on requests
- Track sentiment trends after releases
- Monitor user experience issues

### 2. Customer Support

- Flag urgent tickets automatically
- Identify recurring support issues
- Detect churn risk customers
- Categorize tickets by topic

### 3. Marketing

- Understand customer sentiment
- Identify product messaging gaps
- Track competitor mentions
- Analyze review sentiment

### 4. Executive Dashboards

- High-level sentiment metrics
- Top issues and requests
- Alert notifications
- Trend visualization

## Integration Examples

### Slack Alerts

```python
def send_urgent_to_slack(result):
    for urgent in result.urgent_feedback[:5]:
        slack_webhook_post({
            "text": f"🚨 {urgent.issue}",
            "reason": urgent.reason
        })
```

### Scheduled Analysis

```python
# Run daily via cron
def daily_analysis():
    feedback = fetch_last_24h_feedback()
    result = analyzer.analyze(feedback)
    save_results(result)
    send_alerts_if_urgent(result)
```

### Dashboard Integration

```python
def get_dashboard_data():
    result = analyzer.analyze(feedback_input)
    return {
        "sentiment": result.sentiment_summary,
        "top_issues": result.common_pain_points[:5],
        "alerts": len(result.urgent_feedback)
    }
```

## API Endpoints

- `GET /` - API information
- `GET /health` - Health check
- `POST /api/v1/analyze` - Full analysis
- `POST /api/v1/analyze/quick` - Quick summary

See [API.md](API.md) for complete API reference.

## Documentation

- [SETUP.md](SETUP.md) - Installation and setup guide
- [USAGE.md](USAGE.md) - Detailed usage instructions
- [API.md](API.md) - Complete API reference
- [examples/](examples/) - Code examples

## Technology Stack

- **Python 3.9+**: Core language
- **FastAPI**: REST API framework
- **VADER**: Sentiment analysis
- **scikit-learn**: Text vectorization and clustering
- **BERTopic**: Advanced topic modeling (optional)
- **Pydantic**: Data validation
- **pytest**: Testing framework

## System Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│   FastAPI API   │
└──────┬──────────┘
       │
       ▼
┌──────────────────────────────┐
│    FeedbackAnalyzer          │
│  ┌────────────────────────┐  │
│  │  Sentiment Analyzer    │  │
│  │  (VADER)               │  │
│  └────────────────────────┘  │
│  ┌────────────────────────┐  │
│  │  Pain Point Extractor  │  │
│  │  (TF-IDF + Clustering) │  │
│  └────────────────────────┘  │
│  ┌────────────────────────┐  │
│  │  Feature Extractor     │  │
│  │  (Pattern Matching)    │  │
│  └────────────────────────┘  │
│  ┌────────────────────────┐  │
│  │  Topic Clustering      │  │
│  │  (BERTopic - Optional) │  │
│  └────────────────────────┘  │
└──────────────────────────────┘
       │
       ▼
┌─────────────────┐
│  Analysis Result│
└─────────────────┘
```

## Design Principles

1. **Accuracy First**: Grounded in actual feedback data, no hallucinations
2. **Actionable Insights**: Clear, prioritized, business-focused outputs
3. **Scalable**: Handles small to large datasets efficiently
4. **Extensible**: Modular design for easy customization
5. **Production Ready**: Comprehensive testing and error handling

## Limitations

- **Language**: English only (US/Canada)
- **Sarcasm**: May misclassify sarcastic feedback
- **Context**: Limited context understanding (sentence-level)
- **Real-time**: Not designed for streaming/real-time processing
- **Dataset Size**: Topic clustering requires 10+ items minimum

## Roadmap

- [ ] Multi-language support
- [ ] Real-time streaming analysis
- [ ] Advanced NER (Named Entity Recognition)
- [ ] Trend prediction
- [ ] Webhook support for async processing
- [ ] Custom sentiment lexicons
- [ ] Integration templates (Zendesk, Intercom, etc.)
- [ ] Web dashboard UI

## Contributing

Contributions welcome! Areas for improvement:

- Additional pattern recognition rules
- Domain-specific sentiment tuning
- Performance optimizations
- Integration examples
- Documentation improvements

## License

MIT License - see LICENSE file for details

## Support

For questions or issues:

- Review documentation files
- Check [examples/](examples/) directory
- Test with sample data provided
- Verify configuration in `.env`

## Acknowledgments

Built with:
- VADER Sentiment Analysis
- FastAPI framework
- BERTopic for topic modeling
- scikit-learn for ML utilities

## Version History

- **1.0.0** (2025-11-27): Initial release
  - Core analysis features
  - REST API
  - Comprehensive documentation
  - Test suite

---

**Note**: This system is designed for analyzing customer feedback at scale. Always review results for accuracy and adjust thresholds based on your specific use case.
