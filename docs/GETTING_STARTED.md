# Getting Started

Welcome to the Customer Feedback Analyzer! This guide will help you get up and running quickly.

## What is This?

An AI-powered system that analyzes customer feedback to automatically:

- **Identify Pain Points**: Find what's frustrating customers
- **Extract Feature Requests**: See what customers want
- **Analyze Sentiment**: Track how customers feel over time
- **Flag Urgent Issues**: Detect critical problems and churn risks
- **Cluster Topics**: Group feedback into themes

## 5-Minute Quick Start

### Option 1: Automated Setup

```bash
./quickstart.sh
```

This script will:
1. Check Python version
2. Create virtual environment
3. Install dependencies
4. Download required data
5. Run tests
6. Run example analysis

### Option 2: Manual Setup

```bash
# 1. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Download NLTK data
python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"

# 4. Copy environment file
cp .env.example .env

# 5. Run example
python examples/usage_example.py
```

## Your First Analysis

### Using Python Module

Create a file `my_analysis.py`:

```python
from src.analyzer import FeedbackAnalyzer, FeedbackInput, FeedbackItem

# Prepare your feedback
feedback = FeedbackInput(feedback=[
    FeedbackItem(
        id="1",
        text="The app crashes when I upload files",
        date="2025-11-10",
        source="support_ticket"
    ),
    FeedbackItem(
        id="2",
        text="Would love to see dark mode!",
        date="2025-11-11",
        source="feature_request"
    ),
    FeedbackItem(
        id="3",
        text="Great features! Love the interface.",
        date="2025-11-12",
        source="app_review"
    )
])

# Analyze
analyzer = FeedbackAnalyzer()
result = analyzer.analyze(feedback)

# Display results
print(f"Total feedback: {result.total_feedback_count}")
print(f"Negative sentiment: {result.sentiment_summary.negative_percent}%")
print(f"\nTop pain points:")
for pp in result.common_pain_points[:3]:
    print(f"  - {pp.issue} ({pp.count} mentions)")

print(f"\nTop feature requests:")
for fr in result.feature_requests[:3]:
    print(f"  - {fr.feature} ({fr.count} requests)")

print(f"\nUrgent items: {len(result.urgent_feedback)}")
```

Run it:

```bash
python my_analysis.py
```

### Using the API

**Terminal 1** - Start API server:

```bash
python -m src.api.main
```

**Terminal 2** - Send request:

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d @examples/sample_data.json
```

Or use the Python example:

```bash
python examples/api_example.py
```

## Understanding the Output

### Sentiment Summary

```json
{
  "positive_percent": 15.0,
  "neutral_percent": 20.0,
  "negative_percent": 65.0
}
```

- **Positive**: Happy customers
- **Neutral**: Neither positive nor negative
- **Negative**: Unhappy customers

### Pain Points

```json
{
  "issue": "App crashes on file upload",
  "count": 5,
  "examples": ["The app crashes when..."]
}
```

- **issue**: Description of the problem
- **count**: How many times mentioned
- **examples**: Sample feedback quotes

### Feature Requests

```json
{
  "feature": "Dark mode",
  "count": 7,
  "examples": ["Would love dark mode..."]
}
```

- **feature**: What customers want
- **count**: How many requested it
- **examples**: Sample requests

### Urgent Feedback

```json
{
  "id": "12345",
  "issue": "Cannot login to account",
  "reason": "Customer churn risk; Critical functionality issue",
  "sentiment": "very negative"
}
```

- **id**: Feedback identifier
- **issue**: What's wrong
- **reason**: Why it's flagged as urgent
- **sentiment**: How negative it is

## Common Use Cases

### 1. Daily Feedback Review

```bash
# Run this daily
python examples/usage_example.py > daily_report.txt
```

### 2. API Integration

```python
# In your application
import requests

response = requests.post(
    'http://localhost:8000/api/v1/analyze/quick',
    json={"feedback": feedback_list}
)

summary = response.json()
# Use summary in your dashboard
```

### 3. Urgent Alerts

```python
result = analyzer.analyze(feedback_input)

if result.urgent_feedback:
    # Send to Slack, email, etc.
    alert_team(result.urgent_feedback)
```

## Configuration

Edit `.env` to customize:

```bash
# Enable/disable topic clustering
ENABLE_CLUSTERING=false

# Adjust urgency threshold (-1.0 to 1.0)
URGENT_SENTIMENT_THRESHOLD=-0.7

# API port
API_PORT=8000
```

## Testing Your Setup

### Run Tests

```bash
# All tests
pytest

# Specific test
pytest tests/test_analyzer.py

# With coverage
pytest --cov=src
```

### Verify API

```bash
# Health check
curl http://localhost:8000/health

# Expected: {"status": "healthy", "clustering_enabled": false}
```

## What's Next?

### Learn More

1. **[USAGE.md](USAGE.md)** - Detailed usage guide
2. **[API.md](API.md)** - Complete API reference
3. **[SETUP.md](SETUP.md)** - Advanced setup options
4. **[examples/](examples/)** - More code examples

### Try These Tasks

1. Analyze the sample data with clustering enabled
2. Create your own feedback dataset
3. Integrate with your existing tools (Slack, email)
4. Build a dashboard using the API
5. Schedule daily analysis runs

## Tips for Success

### 1. Data Quality

- Use clear, complete sentences
- Include dates for trend analysis
- Categorize by source (support, reviews, surveys)

### 2. Batch Size

- **Small**: < 50 items (instant results)
- **Medium**: 100-500 items (recommended)
- **Large**: > 1000 items (split into batches)

### 3. Threshold Tuning

Adjust based on your needs:

```python
analyzer = FeedbackAnalyzer(
    urgent_threshold=-0.8,  # More strict
    # or
    urgent_threshold=-0.5   # More sensitive
)
```

### 4. Interpreting Results

- **High negative %**: Focus on pain points
- **Many urgent items**: Critical issues need attention
- **Common feature requests**: Consider for roadmap
- **Sentiment trend**: Track improvement/decline

## Common Questions

**Q: How much feedback do I need?**
A: Minimum 5-10 items for basic analysis, 50+ for reliable trends, 100+ for clustering.

**Q: What languages are supported?**
A: Currently English only (US/Canada).

**Q: How accurate is the sentiment analysis?**
A: VADER achieves ~80% accuracy on social media text. Review results for your domain.

**Q: Can I customize the patterns?**
A: Yes! Edit [src/analyzer/extractors.py](src/analyzer/extractors.py) to add domain-specific patterns.

**Q: How do I deploy to production?**
A: See [SETUP.md](SETUP.md) for deployment guidance using Docker or gunicorn.

## Troubleshooting

### "ModuleNotFoundError"

```bash
# Activate virtual environment
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

### "NLTK data not found"

```bash
python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"
```

### API won't start

```bash
# Check if port is in use
lsof -i :8000

# Change port in .env
API_PORT=8080
```

### Poor results

- Check data quality (remove spam, very short entries)
- Ensure feedback is in English
- Adjust sentiment thresholds
- Need more data for reliable patterns

## Getting Help

1. Check documentation files
2. Review example scripts
3. Run tests to verify setup
4. Check error messages carefully

## Example Output

Here's what you should see after running the example:

```
Customer Feedback Analyzer - Example Usage
============================================================

Analyzing 30 feedback items...

ANALYSIS RESULTS
============================================================

📊 SENTIMENT SUMMARY
------------------------------------------------------------
Positive: 13.33%
Neutral:  20.0%
Negative: 66.67%

🚨 COMMON PAIN POINTS
------------------------------------------------------------

1. App crashes on upload
   Mentions: 5
   Example: "The app crashes when I try to upload a file..."

2. Performance issues
   Mentions: 4
   Example: "App is way too slow. Loading times are ridiculous..."

💡 TOP FEATURE REQUESTS
------------------------------------------------------------

1. Dark mode
   Requests: 4
   Example: "Would love to see a dark mode option..."

⚠️  URGENT FEEDBACK
------------------------------------------------------------

1. ID: 12361
   Issue: PAYMENT PROCESSING FAILED
   Reason: Extreme negative sentiment detected
   Sentiment: very negative

============================================================
✅ Full analysis saved to: examples/analysis_output.json
```

## Quick Reference

```bash
# Setup
./quickstart.sh

# Run example
python examples/usage_example.py

# Start API
python -m src.api.main

# Run tests
pytest

# Clean up
make clean
```

---

**Ready to analyze your customer feedback?** Start with the examples and customize from there!

For detailed documentation, see:
- [USAGE.md](USAGE.md) - Complete usage guide
- [API.md](API.md) - API reference
- [SETUP.md](SETUP.md) - Setup & deployment
