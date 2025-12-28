# Setup Guide

This guide will help you set up and run the Customer Feedback Analyzer.

## Prerequisites

- Python 3.9 or higher
- pip (Python package manager)
- Virtual environment (recommended)

## Installation

### 1. Clone the Repository

```bash
cd /home/aliz/dev/at/customer-feedback-analyzer
```

### 2. Create Virtual Environment

```bash
python -m venv venv
```

### 3. Activate Virtual Environment

**Linux/Mac:**
```bash
source venv/bin/activate
```

**Windows:**
```bash
venv\Scripts\activate
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

### 5. Download NLTK Data (First Time Only)

```bash
python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"
```

## Configuration

### 1. Create Environment File

Copy the example environment file:

```bash
cp .env.example .env
```

### 2. Edit Configuration

Edit `.env` file with your preferences:

```bash
# API Configuration
API_HOST=0.0.0.0
API_PORT=8000

# Analysis Settings
ENABLE_CLUSTERING=false  # Set to true for topic clustering (requires more resources)
MIN_CLUSTER_SIZE=3
MAX_CLUSTERS=10

# Sentiment Thresholds
URGENT_SENTIMENT_THRESHOLD=-0.7
VERY_NEGATIVE_THRESHOLD=-0.5
```

## Running the Application

### Option 1: Run as Python Module (Standalone)

```bash
python examples/usage_example.py
```

This will analyze the sample data and display results in the terminal.

### Option 2: Run API Server

```bash
python -m src.api.main
```

Or using uvicorn directly:

```bash
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at: `http://localhost:8000`

### Option 3: Run API Example

In a separate terminal (with API running):

```bash
python examples/api_example.py
```

## Testing

Run the test suite:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_analyzer.py

# Run with verbose output
pytest -v
```

## Verifying Installation

### 1. Check API Health

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "clustering_enabled": false
}
```

### 2. Quick Test Analysis

```bash
curl -X POST http://localhost:8000/api/v1/analyze/quick \
  -H "Content-Type: application/json" \
  -d @examples/sample_data.json
```

## Troubleshooting

### Issue: ModuleNotFoundError

**Solution:** Make sure you're in the project root directory and virtual environment is activated.

```bash
pwd  # Should show: /home/aliz/dev/at/customer-feedback-analyzer
which python  # Should show virtual environment path
```

### Issue: API Not Starting

**Solution:** Check if port 8000 is already in use:

```bash
lsof -i :8000  # Linux/Mac
netstat -ano | findstr :8000  # Windows
```

Change port in `.env` file if needed.

### Issue: NLTK Data Not Found

**Solution:** Download required NLTK data:

```bash
python -c "import nltk; nltk.download('all')"
```

### Issue: Out of Memory (Topic Clustering)

**Solution:** Disable clustering in `.env`:

```bash
ENABLE_CLUSTERING=false
```

Or reduce dataset size for testing.

## Next Steps

- Read [USAGE.md](USAGE.md) for detailed usage instructions
- Check [API.md](API.md) for API documentation
- See [examples/](examples/) for code examples
- Review [ARCHITECTURE.md](ARCHITECTURE.md) for system design

## Development Setup

For development, install additional tools:

```bash
pip install black flake8 mypy isort
```

Run code formatting:

```bash
black src/ tests/
isort src/ tests/
flake8 src/ tests/
```

## Docker Setup (Optional)

Create a Dockerfile:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"

EXPOSE 8000

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run:

```bash
docker build -t feedback-analyzer .
docker run -p 8000:8000 feedback-analyzer
```
