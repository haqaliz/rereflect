#!/bin/bash

# Customer Feedback Analyzer - Quick Start Script
# This script helps you start both frontend and backend servers

echo "========================================"
echo "Customer Feedback Analyzer - Quick Start"
echo "========================================"
echo ""

# Check if we're in the right directory
if [ ! -d "services/backend-api" ] || [ ! -d "services/frontend-web" ]; then
    echo "Error: Please run this script from the project root directory"
    echo "Current directory: $(pwd)"
    exit 1
fi

echo "This script will open two terminal windows:"
echo "1. Backend API (http://localhost:8000)"
echo "2. Frontend Web App (http://localhost:3000)"
echo ""
echo "Press Enter to continue or Ctrl+C to cancel..."
read

# Start backend in a new terminal
echo "Starting Backend API..."
gnome-terminal -- bash -c "
    cd $(pwd)/services/backend-api
    source venv/bin/activate
    echo '========================================';
    echo 'Backend API Server';
    echo '========================================';
    echo 'API: http://localhost:8000';
    echo 'Docs: http://localhost:8000/docs';
    echo '========================================';
    echo '';
    python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload;
    exec bash
" 2>/dev/null || \
xterm -e "
    cd $(pwd)/services/backend-api;
    source venv/bin/activate;
    echo '========================================';
    echo 'Backend API Server';
    echo '========================================';
    echo 'API: http://localhost:8000';
    echo 'Docs: http://localhost:8000/docs';
    echo '========================================';
    echo '';
    python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload;
    exec bash
" 2>/dev/null

sleep 2

# Start frontend in a new terminal
echo "Starting Frontend Web App..."
gnome-terminal -- bash -c "
    cd $(pwd)/services/frontend-web
    echo '========================================';
    echo 'Frontend Web Application';
    echo '========================================';
    echo 'App: http://localhost:3000';
    echo '========================================';
    echo '';
    npm run dev;
    exec bash
" 2>/dev/null || \
xterm -e "
    cd $(pwd)/services/frontend-web;
    echo '========================================';
    echo 'Frontend Web Application';
    echo '========================================';
    echo 'App: http://localhost:3000';
    echo '========================================';
    echo '';
    npm run dev;
    exec bash
" 2>/dev/null

echo ""
echo "✅ Servers starting..."
echo ""
echo "Backend API:  http://localhost:8000"
echo "API Docs:     http://localhost:8000/docs"
echo "Frontend App: http://localhost:3000"
echo ""
echo "To stop the servers, close the terminal windows or press Ctrl+C in each"
echo ""
