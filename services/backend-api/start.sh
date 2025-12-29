#!/bin/bash

# Backend API Startup Script
# Requires Redis and Celery worker to be running

echo "========================================"
echo "Starting Backend API Server"
echo "========================================"
echo ""

# Check if Redis is running
if ! redis-cli ping > /dev/null 2>&1; then
    echo "❌ Redis is not running!"
    echo ""
    echo "Please start Redis first:"
    echo "  redis-server"
    echo ""
    echo "Or use the master script from project root:"
    echo "  ./start-all.sh"
    echo ""
    exit 1
fi

echo "✅ Redis is running"

# Check if Celery worker is running
if ! pgrep -f "celery.*worker" > /dev/null 2>&1; then
    echo "⚠️  Celery worker not detected"
    echo ""
    echo "Start the worker in another terminal:"
    echo "  cd ../worker-service && ./start.sh"
    echo ""
    echo "Or use the master script from project root:"
    echo "  ./start-all.sh"
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check if port 8000 is already in use
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "⚠️  Port 8000 is already in use!"
    echo ""
    read -p "Do you want to kill the existing process? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]
    then
        echo "Stopping existing process on port 8000..."
        pkill -f "uvicorn.*8000" || lsof -ti:8000 | xargs kill -9
        sleep 2
        echo "✅ Stopped existing process"
        echo ""
    else
        echo "❌ Cancelled. Please stop the existing process manually."
        exit 1
    fi
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found!"
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Check if dependencies are installed
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo "⚠️  Dependencies not installed. Installing now..."
    python3 -m pip install -r requirements.txt
fi

echo ""
echo "✅ Starting server..."
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Backend API Server"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  API:    http://localhost:8000"
echo "  Docs:   http://localhost:8000/docs"
echo "  Worker: http://localhost:8000/worker/status"
echo ""
echo "  Background processing: Celery + Redis"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Start the server
python3 -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
