# Background Jobs Documentation

## Overview

The Customer Feedback Analyzer uses a background scheduler to automatically process and analyze feedback items. This ensures that all feedback is analyzed without blocking API requests.

## How It Works

### Automatic Analysis Scheduler

- **Frequency**: Runs every 30 seconds
- **Process**: Finds all feedback items with `sentiment_label = NULL` (unanalyzed)
- **Batch Size**: Processes up to 100 items per run
- **Analysis Steps**:
  1. Sentiment analysis using VADER (positive/neutral/negative)
  2. Sentiment override: Strong negative keywords (crash, broken, bug, error) override neutral classification
  3. Sentiment score calculation
  4. Urgency detection (critical keywords + very negative sentiment < -0.5)
  5. Pain point extraction (problem/bug keywords OR negative sentiment)

### When Analysis Happens

The background job automatically analyzes feedback:
- ✅ After manual feedback creation
- ✅ After CSV batch import
- ✅ After feedback updates/edits
- ✅ Any time `sentiment_label` is NULL

### Performance

- **Latency**: Feedback is analyzed within 30 seconds of creation
- **Throughput**: Up to 100 items every 30 seconds (200/minute max)
- **Concurrency**: Single instance to prevent duplicate processing
- **Resilience**: Errors in one item don't stop processing of others

## Technical Details

### Scheduler Implementation

**Technology**: APScheduler (Advanced Python Scheduler)

**Location**: `src/background/scheduler.py`

**Key Functions**:
```python
start_scheduler()      # Start background jobs (called on app startup)
stop_scheduler()       # Stop background jobs (called on app shutdown)
get_scheduler_status() # Get scheduler status and job info
```

### Lifecycle

1. **Startup**: Scheduler starts when FastAPI app initializes
2. **Running**: Background job runs every 30 seconds
3. **Shutdown**: Scheduler stops gracefully when app shuts down

### Database Queries

The scheduler uses this query to find unanalyzed feedback:

```sql
SELECT * FROM feedback_items
WHERE sentiment_label IS NULL
LIMIT 100;
```

## API Endpoints

### Check Scheduler Status

```bash
GET /scheduler/status
```

**Response**:
```json
{
  "running": true,
  "jobs": [
    {
      "id": "analyze_feedback",
      "name": "Process unanalyzed feedback",
      "next_run": "2024-01-15T10:30:45.123456"
    }
  ]
}
```

## Monitoring

### Logs

The scheduler logs useful information:

```
INFO: Starting background scheduler...
INFO: Processing 15 unanalyzed feedback items...
INFO: Analysis complete: 15 successful, 0 failed
DEBUG: No unanalyzed feedback found
ERROR: Failed to analyze feedback 123: [error details]
```

### Health Check

Use the health endpoint to verify the API is running:

```bash
GET /health
```

## Configuration

### Adjust Processing Frequency

Edit `src/background/scheduler.py`:

```python
# Current: Every 30 seconds
scheduler.add_job(
    func=process_unanalyzed_feedback,
    trigger=IntervalTrigger(seconds=30),
    ...
)

# Change to 1 minute:
trigger=IntervalTrigger(minutes=1)

# Change to 5 minutes:
trigger=IntervalTrigger(minutes=5)
```

### Adjust Batch Size

Edit the query limit in `process_unanalyzed_feedback()`:

```python
# Current: 100 items per run
unanalyzed = db.query(FeedbackItem).filter(
    FeedbackItem.sentiment_label == None
).limit(100).all()

# Change to 50 items:
.limit(50).all()

# Change to 500 items:
.limit(500).all()
```

## Troubleshooting

### Feedback Not Being Analyzed

1. **Check scheduler status**:
   ```bash
   curl http://localhost:8000/scheduler/status
   ```

2. **Check logs**:
   ```bash
   # Look for scheduler startup
   grep "Starting background scheduler" logs.txt

   # Look for processing logs
   grep "Processing.*unanalyzed" logs.txt
   ```

3. **Verify database**:
   ```sql
   SELECT COUNT(*) FROM feedback_items WHERE sentiment_label IS NULL;
   ```

### Scheduler Not Running

**Symptoms**:
- `GET /scheduler/status` returns `"running": false`
- No processing logs
- Feedback stays unanalyzed

**Solutions**:
1. Restart the backend server
2. Check for errors in startup logs
3. Verify APScheduler is installed: `pip list | grep apscheduler`

### Analysis Errors

If individual items fail to analyze:

1. **Check error logs** for specific failure messages
2. **Verify analysis engine** is accessible
3. **Check database connection**
4. **Review feedback text** for encoding issues

## Advantages Over Manual Analysis

### ❌ Old Approach (Manual)
- User must click "Analyze Selected"
- Batches only when user triggers
- Requires user interaction
- Can forget to analyze

### ✅ New Approach (Background)
- Automatic processing
- Runs continuously
- No user action needed
- Guaranteed analysis within 30 seconds
- Scales to handle bulk imports

## Future Enhancements

Potential improvements:

1. **Priority Queue**: Analyze urgent feedback first
2. **Parallel Processing**: Multiple workers for faster throughput
3. **Retry Logic**: Automatically retry failed analysis
4. **Metrics**: Track analysis speed and success rate
5. **Notifications**: Alert when analysis queue is backing up
6. **Advanced Extraction**: Use AI/ML for feature request detection

## Dependencies

```
apscheduler==3.10.4
```

Required in `requirements.txt` for background job scheduling.

## Code Example

### Add a New Background Job

```python
# In src/background/scheduler.py

def my_custom_job():
    """Custom background task."""
    print("Running custom task...")

# In start_scheduler():
scheduler.add_job(
    func=my_custom_job,
    trigger=IntervalTrigger(hours=1),  # Every hour
    id='my_custom_job',
    name='My custom background job'
)
```

### Manually Trigger Analysis

```python
from src.background.scheduler import process_unanalyzed_feedback

# Run the analysis job immediately
process_unanalyzed_feedback()
```

## Best Practices

1. **Don't modify scheduler code** while the server is running
2. **Monitor logs** regularly for processing errors
3. **Adjust frequency** based on your volume of feedback
4. **Set batch size** based on your server capacity
5. **Use health check** in production monitoring
6. **Keep analysis fast** - complex ML should be async
