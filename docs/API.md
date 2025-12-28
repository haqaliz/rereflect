# API Reference

Complete API documentation for the Customer Feedback Analyzer.

## Base URL

```
http://localhost:8000
```

## Authentication

Currently, the API does not require authentication. For production use, implement:
- API key authentication
- JWT tokens
- OAuth 2.0

## Endpoints

### GET /

Root endpoint with API information.

**Response:**

```json
{
  "name": "Customer Feedback Analyzer API",
  "version": "1.0.0",
  "endpoints": {
    "analyze": "/api/v1/analyze",
    "health": "/health"
  }
}
```

### GET /health

Health check endpoint.

**Response:**

```json
{
  "status": "healthy",
  "clustering_enabled": false
}
```

### POST /api/v1/analyze

Perform complete feedback analysis.

**Request Body:**

```json
{
  "feedback": [
    {
      "id": "string",
      "text": "string",
      "date": "YYYY-MM-DD",
      "source": "string (optional)"
    }
  ]
}
```

**Field Descriptions:**

- `id` (required): Unique identifier for feedback entry
- `text` (required): The feedback text content
- `date` (required): Date in ISO format (YYYY-MM-DD)
- `source` (optional): Source of feedback (e.g., "support_ticket", "app_review")

**Response:**

```json
{
  "common_pain_points": [
    {
      "issue": "string",
      "count": 0,
      "examples": ["string"]
    }
  ],
  "feature_requests": [
    {
      "feature": "string",
      "count": 0,
      "examples": ["string"]
    }
  ],
  "sentiment_summary": {
    "positive_percent": 0.0,
    "neutral_percent": 0.0,
    "negative_percent": 0.0,
    "trend_by_month": {
      "YYYY-MM": {
        "avg_score": 0.0,
        "negative_percent": 0.0,
        "positive_percent": 0.0,
        "neutral_percent": 0.0
      }
    },
    "by_category": {
      "source_name": {
        "positive": 0.0,
        "neutral": 0.0,
        "negative": 0.0
      }
    }
  },
  "urgent_feedback": [
    {
      "id": "string",
      "issue": "string",
      "reason": "string",
      "sentiment": "string",
      "text_excerpt": "string"
    }
  ],
  "topic_clusters": [
    {
      "topic": "string",
      "count": 0,
      "representative_feedback_ids": ["string"],
      "keywords": ["string"]
    }
  ],
  "analysis_notes": "string",
  "total_feedback_count": 0,
  "analysis_timestamp": "ISO-8601 timestamp"
}
```

**Status Codes:**

- `200 OK`: Analysis completed successfully
- `400 Bad Request`: Invalid input (empty feedback, validation errors)
- `422 Unprocessable Entity`: JSON validation error
- `500 Internal Server Error`: Analysis failed

**Example Request:**

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "feedback": [
      {
        "id": "1",
        "text": "The app crashes when I upload files",
        "date": "2025-11-10",
        "source": "support_ticket"
      },
      {
        "id": "2",
        "text": "Would love to see dark mode!",
        "date": "2025-11-11",
        "source": "feature_request"
      }
    ]
  }'
```

### POST /api/v1/analyze/quick

Perform quick analysis returning summary statistics only.

Faster than full analysis, useful for dashboards requiring overview metrics.

**Request Body:**

Same as `/api/v1/analyze`

**Response:**

```json
{
  "total_feedback": 0,
  "sentiment": {
    "positive_percent": 0.0,
    "neutral_percent": 0.0,
    "negative_percent": 0.0
  },
  "pain_points_count": 0,
  "feature_requests_count": 0,
  "urgent_feedback_count": 0,
  "top_pain_point": "string or null",
  "top_feature_request": "string or null"
}
```

**Status Codes:**

- `200 OK`: Quick analysis completed
- `400 Bad Request`: Invalid input
- `422 Unprocessable Entity`: JSON validation error
- `500 Internal Server Error`: Analysis failed

**Example Request:**

```bash
curl -X POST http://localhost:8000/api/v1/analyze/quick \
  -H "Content-Type: application/json" \
  -d @examples/sample_data.json
```

## Error Responses

### 400 Bad Request

```json
{
  "detail": "No feedback items provided in input"
}
```

### 422 Validation Error

```json
{
  "detail": [
    {
      "loc": ["body", "feedback", 0, "text"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### 500 Internal Server Error

```json
{
  "detail": "Analysis failed: [error message]"
}
```

## Rate Limiting

Currently not implemented. For production:

- Implement rate limiting per IP/API key
- Suggested: 100 requests per hour
- Return `429 Too Many Requests` when exceeded

## CORS Configuration

CORS is enabled for all origins in development. For production:

```python
# Update in src/api/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)
```

## Interactive API Documentation

FastAPI provides automatic interactive API documentation:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## Request/Response Examples

### Example 1: Minimal Request

**Request:**

```json
{
  "feedback": [
    {
      "id": "1",
      "text": "App is great!",
      "date": "2025-11-10"
    }
  ]
}
```

**Response (excerpt):**

```json
{
  "sentiment_summary": {
    "positive_percent": 100.0,
    "neutral_percent": 0.0,
    "negative_percent": 0.0
  },
  "total_feedback_count": 1,
  "analysis_notes": "Note: Only 1 feedback entries were analyzed. Insights may be limited due to small dataset size."
}
```

### Example 2: Multiple Feedback Sources

**Request:**

```json
{
  "feedback": [
    {
      "id": "1",
      "text": "App crashes constantly",
      "date": "2025-11-10",
      "source": "support_ticket"
    },
    {
      "id": "2",
      "text": "Great customer support!",
      "date": "2025-11-10",
      "source": "survey"
    },
    {
      "id": "3",
      "text": "Terrible performance",
      "date": "2025-11-10",
      "source": "app_review"
    }
  ]
}
```

**Response (excerpt):**

```json
{
  "sentiment_summary": {
    "by_category": {
      "support_ticket": {
        "positive": 0.0,
        "neutral": 0.0,
        "negative": 100.0
      },
      "survey": {
        "positive": 100.0,
        "neutral": 0.0,
        "negative": 0.0
      },
      "app_review": {
        "positive": 0.0,
        "neutral": 0.0,
        "negative": 100.0
      }
    }
  }
}
```

### Example 3: Urgent Feedback Detection

**Request:**

```json
{
  "feedback": [
    {
      "id": "urgent1",
      "text": "I'M CANCELING MY SUBSCRIPTION! This app is completely broken and you're not fixing it!",
      "date": "2025-11-20",
      "source": "support_ticket"
    }
  ]
}
```

**Response (excerpt):**

```json
{
  "urgent_feedback": [
    {
      "id": "urgent1",
      "issue": "I'M CANCELING MY SUBSCRIPTION!",
      "reason": "Extreme negative sentiment detected; Customer churn risk; Very low sentiment score",
      "sentiment": "very negative",
      "text_excerpt": "I'M CANCELING MY SUBSCRIPTION! This app is completely broken and you're not fixing it!"
    }
  ]
}
```

## Client Libraries

### Python

```python
import requests

class FeedbackAnalyzerClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url

    def analyze(self, feedback_data):
        response = requests.post(
            f"{self.base_url}/api/v1/analyze",
            json=feedback_data
        )
        response.raise_for_status()
        return response.json()

    def quick_analyze(self, feedback_data):
        response = requests.post(
            f"{self.base_url}/api/v1/analyze/quick",
            json=feedback_data
        )
        response.raise_for_status()
        return response.json()

# Usage
client = FeedbackAnalyzerClient()
result = client.analyze({"feedback": [...]})
```

### JavaScript/TypeScript

```typescript
class FeedbackAnalyzerClient {
  constructor(private baseUrl: string = 'http://localhost:8000') {}

  async analyze(feedbackData: any) {
    const response = await fetch(`${this.baseUrl}/api/v1/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(feedbackData)
    });

    if (!response.ok) {
      throw new Error(`Analysis failed: ${response.statusText}`);
    }

    return response.json();
  }

  async quickAnalyze(feedbackData: any) {
    const response = await fetch(`${this.baseUrl}/api/v1/analyze/quick`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(feedbackData)
    });

    if (!response.ok) {
      throw new Error(`Quick analysis failed: ${response.statusText}`);
    }

    return response.json();
  }
}

// Usage
const client = new FeedbackAnalyzerClient();
const result = await client.analyze({ feedback: [...] });
```

## Performance Considerations

### Request Size Limits

- **Recommended**: 100-500 feedback items per request
- **Maximum**: 1000 items (configurable)
- Larger datasets: split into multiple batches

### Response Times

- **Quick Analysis**: < 1 second for 100 items
- **Full Analysis (no clustering)**: 2-5 seconds for 100 items
- **Full Analysis (with clustering)**: 10-30 seconds for 100 items

### Optimization Tips

1. Use `/api/v1/analyze/quick` for real-time dashboards
2. Process large datasets in batches
3. Disable clustering for faster results
4. Cache results when possible
5. Use async requests for multiple analyses

## Deployment

### Environment Variables

```bash
API_HOST=0.0.0.0
API_PORT=8000
ENABLE_CLUSTERING=false
URGENT_SENTIMENT_THRESHOLD=-0.7
VERY_NEGATIVE_THRESHOLD=-0.5
```

### Production Recommendations

1. **Use HTTPS**: Deploy behind reverse proxy (nginx, traefik)
2. **Add Authentication**: Implement API keys or OAuth
3. **Enable Rate Limiting**: Prevent abuse
4. **Add Monitoring**: Track API performance and errors
5. **Configure CORS**: Restrict to specific domains
6. **Use Process Manager**: gunicorn, uvicorn workers
7. **Add Logging**: Structured logging for debugging

### Example Production Deployment

```bash
# Using gunicorn with uvicorn workers
gunicorn src.api.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --access-logfile - \
  --error-logfile -
```

## Webhooks (Future Feature)

Planned webhook support for async processing:

```json
POST /api/v1/analyze/async
{
  "feedback": [...],
  "webhook_url": "https://your-domain.com/webhook",
  "callback_id": "unique-id"
}
```

## API Versioning

Current version: `v1`

Future versions will be available at:
- `/api/v2/analyze`
- API version in response headers

## Support

For API issues:
- Check API logs
- Review error messages
- Test with sample data
- Check [USAGE.md](USAGE.md) for examples
