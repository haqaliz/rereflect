#!/bin/bash

# Stop All Services Script

echo "=========================================="
echo "  Stopping All Services"
echo "=========================================="
echo ""

# Stop backend (port 8000)
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "🛑 Stopping Backend API (port 8000)..."
    pkill -f "uvicorn.*8000" 2>/dev/null || lsof -ti:8000 | xargs kill -9 2>/dev/null
    echo "✅ Backend stopped"
else
    echo "ℹ️  Backend not running"
fi

# Stop frontend (port 3000)
if lsof -Pi :3000 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "🛑 Stopping Frontend Web App (port 3000)..."
    pkill -f "next dev" 2>/dev/null || lsof -ti:3000 | xargs kill -9 2>/dev/null
    echo "✅ Frontend stopped"
else
    echo "ℹ️  Frontend not running"
fi

echo ""
echo "✅ All services stopped!"
echo ""
