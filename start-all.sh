#!/bin/bash

# Master Startup Script - Starts Both Backend and Frontend

echo "=========================================="
echo "  Customer Feedback Analyzer"
echo "  Starting All Services"
echo "=========================================="
echo ""

# Check if we're in the right directory
if [ ! -d "services/backend-api" ] || [ ! -d "services/frontend-web" ]; then
    echo "❌ Error: Please run this script from the project root directory"
    echo "Current directory: $(pwd)"
    exit 1
fi

echo "This will start:"
echo "  1. Backend API (http://localhost:8000)"
echo "  2. Frontend Web App (http://localhost:3000)"
echo ""
echo "Press Enter to continue or Ctrl+C to cancel..."
read

# Function to open terminal
open_terminal() {
    local cmd="$1"
    local title="$2"

    # Try gnome-terminal first (Ubuntu/GNOME)
    if command -v gnome-terminal &> /dev/null; then
        gnome-terminal --title="$title" -- bash -c "$cmd; exec bash" 2>/dev/null
        return 0
    fi

    # Try konsole (KDE)
    if command -v konsole &> /dev/null; then
        konsole --title="$title" -e bash -c "$cmd; exec bash" &
        return 0
    fi

    # Try xfce4-terminal (XFCE)
    if command -v xfce4-terminal &> /dev/null; then
        xfce4-terminal --title="$title" -e "bash -c '$cmd; exec bash'" &
        return 0
    fi

    # Try xterm (fallback)
    if command -v xterm &> /dev/null; then
        xterm -title "$title" -e "bash -c '$cmd; exec bash'" &
        return 0
    fi

    # Try alacritty (modern terminal)
    if command -v alacritty &> /dev/null; then
        alacritty --title "$title" -e bash -c "$cmd; exec bash" &
        return 0
    fi

    echo "❌ No supported terminal emulator found!"
    echo "Please install: gnome-terminal, konsole, xfce4-terminal, xterm, or alacritty"
    return 1
}

# Start backend
echo "🚀 Starting Backend API..."
backend_cmd="cd $(pwd)/services/backend-api && ./start.sh"
if open_terminal "$backend_cmd" "Backend API"; then
    echo "✅ Backend terminal opened"
else
    echo "❌ Failed to open backend terminal"
    exit 1
fi

sleep 2

# Start frontend
echo "🚀 Starting Frontend Web App..."
frontend_cmd="cd $(pwd)/services/frontend-web && ./start.sh"
if open_terminal "$frontend_cmd" "Frontend Web App"; then
    echo "✅ Frontend terminal opened"
else
    echo "❌ Failed to open frontend terminal"
    exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ All services are starting!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Backend API:  http://localhost:8000"
echo "  API Docs:     http://localhost:8000/docs"
echo "  Frontend App: http://localhost:3000"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "To stop the servers:"
echo "  - Close the terminal windows, or"
echo "  - Press Ctrl+C in each terminal"
echo ""
