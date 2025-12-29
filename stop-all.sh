#!/bin/bash

# Stop All Services Script

SESSION_NAME="rereflect"

echo "=========================================="
echo "  Stopping All Services"
echo "=========================================="
echo ""

# Kill tmux session if it exists
if tmux has-session -t $SESSION_NAME 2>/dev/null; then
    echo "🛑 Stopping tmux session: $SESSION_NAME"
    tmux kill-session -t $SESSION_NAME
    echo "✅ tmux session stopped"
else
    echo "ℹ️  No tmux session found"
fi

# Stop any remaining processes on ports
echo ""

# Stop backend (port 8000)
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "🛑 Stopping Backend API (port 8000)..."
    pkill -f "uvicorn.*8000" 2>/dev/null || lsof -ti:8000 | xargs kill -9 2>/dev/null
    echo "✅ Backend stopped"
else
    echo "ℹ️  Backend not running on port 8000"
fi

# Stop frontend (port 3000)
if lsof -Pi :3000 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "🛑 Stopping Frontend Web App (port 3000)..."
    pkill -f "next dev" 2>/dev/null || lsof -ti:3000 | xargs kill -9 2>/dev/null
    echo "✅ Frontend stopped"
else
    echo "ℹ️  Frontend not running on port 3000"
fi

# Stop Celery workers
if pgrep -f "celery.*worker" >/dev/null 2>&1 ; then
    echo "🛑 Stopping Celery workers..."
    pkill -f "celery.*worker" 2>/dev/null
    echo "✅ Celery workers stopped"
else
    echo "ℹ️  Celery workers not running"
fi

# Stop Redis (only if started by us, not system service)
if pgrep -f "redis-server" >/dev/null 2>&1 ; then
    echo ""
    read -p "Stop Redis server? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        pkill -f "redis-server" 2>/dev/null
        echo "✅ Redis stopped"
    else
        echo "ℹ️  Redis left running"
    fi
fi

echo ""
echo "✅ All services stopped!"
echo ""
