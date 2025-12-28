# Customer Feedback Analyzer - Startup Guide

This guide will help you run both the backend API and frontend web application.

## Prerequisites

- Python 3.12+ installed
- Node.js 18+ installed
- PostgreSQL 14+ installed and running
- Git installed

## Quick Start (Run Everything)

### Option 1: Use the Startup Script (Easiest!)

```bash
cd /home/aliz/dev/at/customer-feedback-analyzer
./start-all.sh
```

This will automatically open two terminal windows - one for backend and one for frontend!

To stop everything:
```bash
./stop-all.sh
```

### Option 2: Start Services Individually

**Backend API:**
```bash
cd services/backend-api
./start.sh
```

**Frontend Web App:**
```bash
cd services/frontend-web
./start.sh
```

### Option 3: Manual Commands

**Terminal 1 - Backend API:**
```bash
cd services/backend-api
source venv/bin/activate
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2 - Frontend Web App:**
```bash
cd services/frontend-web
npm run dev
```

### Access URLs

The services will be available at:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs (Swagger)**: http://localhost:8000/docs
- **OpenAPI JSON**: http://localhost:8000/openapi.json

## Step-by-Step Setup

### 1. Database Setup

If you haven't set up the database yet:

```bash
# Create the database
createdb customer_feedback_saas

# Navigate to backend directory
cd /home/aliz/dev/at/customer-feedback-analyzer/services/backend-api

# Activate virtual environment
source venv/bin/activate

# Run migrations
alembic upgrade head
```

###  2. Backend API Setup

```bash
# Navigate to backend directory
cd /home/aliz/dev/at/customer-feedback-analyzer/services/backend-api

# Create/activate virtual environment (if not already done)
python3 -m venv venv
source venv/bin/activate

# Install dependencies (if not already installed)
pip install -r requirements.txt

# Also install analysis-engine dependencies
pip install -r ../analysis-engine/requirements.txt

# Create .env file (if needed)
cat > .env << EOF
DATABASE_URL=postgresql:///customer_feedback_saas
JWT_SECRET=dev-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRATION_DAYS=7
EOF

# Start the server
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Frontend Web App Setup

```bash
# Navigate to frontend directory
cd /home/aliz/dev/at/customer-feedback-analyzer/services/frontend-web

# Install dependencies (if not already installed)
npm install

# Create .env.local file (optional - defaults to localhost:8000)
cat > .env.local << EOF
NEXT_PUBLIC_API_URL=http://localhost:8000
EOF

# Start the development server
npm run dev
```

## Using the Application

### 1. Create an Account

1. Open http://localhost:3000 in your browser
2. Click "Sign Up"
3. Fill in:
   - **Organization Name**: Your company name
   - **Email**: Your email address
   - **Password**: Choose a password
4. Click "Create account"

You'll be automatically logged in and redirected to the dashboard.

### 2. Dashboard

The dashboard shows:
- **Sentiment Statistics**: Positive, neutral, and negative feedback counts
- **Pain Points**: Top customer complaints
- **Feature Requests**: Most requested features
- **Urgent Feedback**: Items flagged as urgent

### 3. Manage Feedback

1. Click "Feedback" in the header
2. **Add Feedback**: Click "Add Feedback" button
3. **Analyze Feedback**:
   - Select feedback items using checkboxes
   - Click "Analyze Selected" to run AI analysis
   - Refresh to see results

### 4. Organization Settings

Click "Settings" to view:
- Organization details
- Usage statistics
- Current plan

## Testing the API Directly

You can test the backend API independently:

```bash
cd /home/aliz/dev/at/customer-feedback-analyzer/services/backend-api

# Run the Week 2 test script
./test_week2.sh
```

This will test all API endpoints including:
- Authentication (signup/login)
- Organization endpoints
- Feedback CRUD operations
- Dashboard analytics
- Analysis engine integration

## Stopping the Servers

### Stop Backend API
- Press `Ctrl+C` in the terminal running the backend
- Or: `pkill -f "uvicorn.*8000"`

### Stop Frontend
- Press `Ctrl+C` in the terminal running the frontend
- Or: `lsof -ti:3000 | xargs kill`

## Troubleshooting

### Backend Issues

**Port 8000 already in use:**
```bash
# Kill process on port 8000
pkill -f "uvicorn.*8000"
# Or find and kill specific PID
lsof -ti:8000 | xargs kill
```

**Database connection errors:**
```bash
# Check if PostgreSQL is running
sudo systemctl status postgresql

# Create database if it doesn't exist
createdb customer_feedback_saas

# Run migrations
alembic upgrade head
```

**Import errors:**
```bash
# Reinstall dependencies
pip install -r requirements.txt
pip install -r ../analysis-engine/requirements.txt
```

### Frontend Issues

**Port 3000 already in use:**
```bash
# Kill process on port 3000
lsof -ti:3000 | xargs kill
```

**API connection errors:**
- Make sure backend is running on http://localhost:8000
- Check CORS settings in backend (should allow http://localhost:3000)
- Verify `NEXT_PUBLIC_API_URL` in `.env.local`

**Build errors:**
```bash
# Clear Next.js cache and reinstall
rm -rf .next node_modules
npm install
npm run dev
```

## Production Build

### Backend
```bash
# Use production WSGI server (gunicorn)
pip install gunicorn
gunicorn src.api.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Frontend
```bash
# Build for production
npm run build

# Start production server
npm start
```

## Default Test Account

The test scripts create a default account:
- **Email**: test@example.com
- **Password**: password123
- **Organization**: Test Organization

You can use this to login or create a new account.

## API Documentation

Once the backend is running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

These provide interactive API documentation where you can test endpoints directly.

## Architecture Overview

```
┌─────────────────┐
│   Frontend      │  http://localhost:3000
│   (Next.js)     │  - React components
│                 │  - Tailwind CSS
└────────┬────────┘  - TypeScript
         │
         │ HTTP/REST
         │
┌────────▼────────┐
│   Backend API   │  http://localhost:8000
│   (FastAPI)     │  - JWT authentication
│                 │  - PostgreSQL database
└────────┬────────┘  - Multi-tenant
         │
         │
┌────────▼────────┐
│ Analysis Engine │
│   (Python ML)   │  - Sentiment analysis
│                 │  - Issue extraction
└─────────────────┘  - VADER + Transformers
```

## Next Steps

1. **Add more feedback** via the web interface or API
2. **Analyze feedback** to get sentiment scores and extract issues
3. **Review dashboard** to see analytics
4. **Explore the API** using Swagger UI at http://localhost:8000/docs

## Need Help?

- Check the [ROADMAP.md](ROADMAP.md) for planned features
- Review [docs/guides/week1-backend-setup.md](docs/guides/week1-backend-setup.md) for backend details
- Review [docs/guides/week2-crud-endpoints.md](docs/guides/week2-crud-endpoints.md) for API endpoints
