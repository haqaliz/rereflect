# Quick Start Commands

## 🚀 Starting the Application

### Option 1: Start Everything (Recommended)
```bash
./start-all.sh
```
This will open two terminal windows - one for backend, one for frontend.

### Option 2: Start Services Individually

**Backend Only:**
```bash
cd services/backend-api
./start.sh
```

**Frontend Only:**
```bash
cd services/frontend-web
./start.sh
```

## 🛑 Stopping the Application

### Stop Everything
```bash
./stop-all.sh
```

### Stop Individual Services
Just press `Ctrl+C` in the terminal running the service.

## 🌐 Access URLs

- **Frontend App**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

## 🔑 Test Account

- **Email**: test@example.com
- **Password**: password123

## 📝 Manual Commands

If you prefer to run commands manually:

**Backend:**
```bash
cd services/backend-api
source venv/bin/activate
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

**Frontend:**
```bash
cd services/frontend-web
npm run dev
```

## 🔧 Troubleshooting

**Port already in use:**
- Run `./stop-all.sh` to stop all services
- Or manually kill the process: `lsof -ti:8000 | xargs kill` (for backend) or `lsof -ti:3000 | xargs kill` (for frontend)

**Dependencies not installed:**
- Backend: `cd services/backend-api && pip install -r requirements.txt`
- Frontend: `cd services/frontend-web && npm install`

**Database not set up:**
```bash
createdb customer_feedback_saas
cd services/backend-api
source venv/bin/activate
alembic upgrade head
```

## 📚 More Information

See [STARTUP_GUIDE.md](STARTUP_GUIDE.md) for detailed setup instructions and troubleshooting.
