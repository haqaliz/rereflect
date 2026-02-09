#!/bin/bash

# Master Startup Script - Starts All Services with tmux
# Services: Redis (background), Celery Worker, Backend API, Frontend, Landing
# Layout: 4 panes

set -e

SESSION_NAME="rereflect"
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "=========================================="
echo "  Customer Feedback Analyzer"
echo "  Starting All Services"
echo "=========================================="
echo ""

# Check if we're in the right directory
if [ ! -d "$PROJECT_ROOT/services/backend-api" ] || [ ! -d "$PROJECT_ROOT/services/frontend-web" ]; then
    echo "❌ Error: Please run this script from the project root directory"
    echo "Current directory: $(pwd)"
    exit 1
fi

# Check for tmux
if ! command -v tmux &> /dev/null; then
    echo "❌ tmux is not installed!"
    echo ""
    echo "Please install tmux:"
    echo "  Ubuntu/Debian: sudo apt install tmux"
    echo "  macOS: brew install tmux"
    echo ""
    exit 1
fi

# Check for Redis
if ! command -v redis-server &> /dev/null; then
    echo "❌ Redis is not installed!"
    echo ""
    echo "Please install Redis:"
    echo "  Ubuntu/Debian: sudo apt install redis-server"
    echo "  macOS: brew install redis"
    echo ""
    exit 1
fi

# Kill existing session if it exists
tmux kill-session -t $SESSION_NAME 2>/dev/null || true

# Start Redis in background if not already running
if ! redis-cli ping > /dev/null 2>&1; then
    echo "🔴 Starting Redis in background..."
    redis-server --daemonize yes
    sleep 1
    if redis-cli ping > /dev/null 2>&1; then
        echo "✅ Redis started"
    else
        echo "❌ Failed to start Redis"
        exit 1
    fi
else
    echo "✅ Redis already running"
fi

echo ""
echo "Starting services in tmux session: $SESSION_NAME"
echo ""

# Create new tmux session (top-left pane - Worker)
tmux new-session -d -s $SESSION_NAME -c "$PROJECT_ROOT/services/worker-service"
# Panes: {0=worker}

# Split horizontally: creates right pane (API)
tmux split-window -h -t $SESSION_NAME:0.0 -c "$PROJECT_ROOT/services/backend-api"
# Panes: {0=worker(left), 1=api(right)}

# Split left pane vertically: creates bottom-left (Landing)
tmux split-window -v -t $SESSION_NAME:0.0 -c "$PROJECT_ROOT/services/landing-web"
# Panes: {0=worker(top-left), 1=landing(bottom-left), 2=api(right)}
# NOTE: old pane 1 (api) shifted to pane 2

# Split right pane (now pane 2) vertically: creates bottom-right (Frontend)
tmux split-window -v -t $SESSION_NAME:0.2 -c "$PROJECT_ROOT/services/frontend-web"
# Panes: {0=worker(top-left), 1=landing(bottom-left), 2=api(top-right), 3=frontend(bottom-right)}

# Start Celery Worker in top-left pane (0)
tmux send-keys -t $SESSION_NAME:0.0 "echo '═══════════════════════════════════════'" Enter
tmux send-keys -t $SESSION_NAME:0.0 "echo '  ⚙️  CELERY WORKER + REDIS'" Enter
tmux send-keys -t $SESSION_NAME:0.0 "echo '═══════════════════════════════════════'" Enter
tmux send-keys -t $SESSION_NAME:0.0 "[ ! -d venv ] && python3 -m venv venv; source venv/bin/activate && python3 -m pip install -q -r requirements.txt && python3 -m celery -A src.celery_app worker --beat --loglevel=info" Enter

# Wait for worker to initialize
sleep 2

# Start Backend API in top-right pane (2)
tmux send-keys -t $SESSION_NAME:0.2 "echo '═══════════════════════════════════════'" Enter
tmux send-keys -t $SESSION_NAME:0.2 "echo '  🚀 BACKEND API (port 8000)'" Enter
tmux send-keys -t $SESSION_NAME:0.2 "echo '═══════════════════════════════════════'" Enter
tmux send-keys -t $SESSION_NAME:0.2 "[ ! -d venv ] && python3 -m venv venv; source venv/bin/activate && python3 -m pip install -q -r requirements.txt && python3 -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload" Enter

# Start Landing Page in bottom-left pane (1)
tmux send-keys -t $SESSION_NAME:0.1 "echo '═══════════════════════════════════════'" Enter
tmux send-keys -t $SESSION_NAME:0.1 "echo '  🏠 LANDING PAGE (port 3001)'" Enter
tmux send-keys -t $SESSION_NAME:0.1 "echo '═══════════════════════════════════════'" Enter
tmux send-keys -t $SESSION_NAME:0.1 "pnpm install --silent && pnpm dev" Enter

# Start Frontend in bottom-right pane (3)
tmux send-keys -t $SESSION_NAME:0.3 "echo '═══════════════════════════════════════'" Enter
tmux send-keys -t $SESSION_NAME:0.3 "echo '  🌐 FRONTEND APP (port 3000)'" Enter
tmux send-keys -t $SESSION_NAME:0.3 "echo '═══════════════════════════════════════'" Enter
tmux send-keys -t $SESSION_NAME:0.3 "pnpm install --silent && pnpm dev" Enter

# Select the API pane as the active one
tmux select-pane -t $SESSION_NAME:0.2

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ All services starting in tmux session!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Layout:"
echo "  ┌─────────────────┬─────────────────┐"
echo "  │  ⚙️  Worker      │  🚀 API         │"
echo "  │  (Celery+Beat)  │  (port 8000)    │"
echo "  ├─────────────────┼─────────────────┤"
echo "  │  🏠 Landing     │  🌐 Frontend    │"
echo "  │  (port 3001)    │  (port 3000)    │"
echo "  └─────────────────┴─────────────────┘"
echo ""
echo "  Services:"
echo "    Redis:    localhost:6379 (background)"
echo "    API:      http://localhost:8000"
echo "    Docs:     http://localhost:8000/docs"
echo "    Landing:  http://localhost:3001"
echo "    Frontend: http://localhost:3000"
echo ""
echo "  tmux commands:"
echo "    Attach:      tmux attach -t $SESSION_NAME"
echo "    Switch pane: Ctrl+b then arrow keys"
echo "    Detach:      Ctrl+b then d"
echo "    Stop all:    ./stop-all.sh"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Attach to tmux session
tmux attach -t $SESSION_NAME
