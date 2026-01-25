#!/bin/bash

# Worker Service Startup Script

echo "========================================"
echo "Starting Celery Worker Service"
echo "========================================"
echo ""

# Check if Redis is running
if ! redis-cli ping > /dev/null 2>&1; then
    echo "❌ Redis is not running!"
    echo ""
    echo "Please start Redis first:"
    echo "  redis-server"
    echo ""
    exit 1
fi

echo "✅ Redis is running"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo ""
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Check if dependencies are installed
if ! python3 -c "import celery" 2>/dev/null; then
    echo "⚠️  Dependencies not installed. Installing now..."
    python3 -m pip install -r requirements.txt
fi

echo ""
echo "✅ Starting Celery worker..."
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Celery Worker Service"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Broker:   redis://localhost:6379/0"
echo "  Tasks:    analysis, alerts, integrations"
echo ""
echo "  Scheduled Tasks (via Celery Beat):"
echo "    - process_unanalyzed_feedback: every 30s"
echo "    - check_urgent_alerts: every 5 min"
echo "    - sync_integrations: daily at 2 AM"
echo ""
echo "  Monitor with Flower (optional):"
echo "    celery -A src.celery_app flower --port=5555"
echo "    http://localhost:5555"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Press Ctrl+C to stop the worker"
echo ""

# Start Celery worker with beat scheduler
python3 -m celery -A src.celery_app worker --beat --loglevel=info
