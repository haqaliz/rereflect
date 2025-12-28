#!/bin/bash

# Week 2 API Testing Script
# Tests organization, feedback, dashboard, and analyze endpoints

echo "==================================================="
echo "Week 2 API Endpoints Test"
echo "==================================================="
echo ""

# Start server
echo "Starting API server..."
pkill -f "uvicorn.*8000" 2>/dev/null
sleep 2

source venv/bin/activate
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 > /tmp/week2-api.log 2>&1 &
SERVER_PID=$!
sleep 5

# Check if server started
if ! curl -s http://localhost:8000/ > /dev/null; then
    echo "ERROR: Server failed to start. Check /tmp/week2-api.log"
    tail -20 /tmp/week2-api.log
    exit 1
fi

echo "✅ Server started (PID: $SERVER_PID)"
echo ""

# Login to get token
echo "1. Logging in..."
TOKEN_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password123"}')

TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
    echo "❌ Failed to get token"
    echo "$TOKEN_RESPONSE"
    kill $SERVER_PID
    exit 1
fi

echo "✅ Got authentication token"
echo ""

# Test Organization endpoints
echo "2. Testing Organization Endpoints"
echo "-----------------------------------"

echo "GET /api/v1/organizations/me"
curl -s -X GET http://localhost:8000/api/v1/organizations/me \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo ""

echo "GET /api/v1/organizations/me/stats"
curl -s -X GET http://localhost:8000/api/v1/organizations/me/stats \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo ""

# Test Feedback endpoints
echo "3. Testing Feedback Endpoints"
echo "-------------------------------"

echo "POST /api/v1/feedback (create)"
FB1=$(curl -s --location-trusted -X POST http://localhost:8000/api/v1/feedback \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"The app crashes when I export data","source":"manual"}')
echo "$FB1" | python3 -m json.tool
FB1_ID=$(echo "$FB1" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)
echo ""

echo "POST /api/v1/feedback (create another)"
FB2=$(curl -s --location-trusted -X POST http://localhost:8000/api/v1/feedback \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"Love the new dashboard design!","source":"manual"}')
echo "$FB2" | python3 -m json.tool
FB2_ID=$(echo "$FB2" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)
echo ""

echo "GET /api/v1/feedback (list with pagination)"
curl -s --location-trusted -X GET "http://localhost:8000/api/v1/feedback?page=1&page_size=10" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo ""

if [ -n "$FB1_ID" ]; then
    echo "GET /api/v1/feedback/$FB1_ID (get single)"
    curl -s --location-trusted -X GET "http://localhost:8000/api/v1/feedback/$FB1_ID" \
      -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
    echo ""
fi

# Test Dashboard
echo "4. Testing Dashboard Endpoint"
echo "-------------------------------"
echo "GET /api/v1/dashboard?days=30"
curl -s --location-trusted -X GET "http://localhost:8000/api/v1/dashboard?days=30" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo ""

# Test Analyze (if feedback IDs exist)
if [ -n "$FB1_ID" ] && [ -n "$FB2_ID" ]; then
    echo "5. Testing Analysis Engine Integration"
    echo "---------------------------------------"
    echo "POST /api/v1/analyze (analyze feedback)"
    curl -s --location-trusted -X POST http://localhost:8000/api/v1/analyze \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"feedback_ids\":[$FB1_ID,$FB2_ID]}" | python3 -m json.tool
    echo ""

    echo "Getting analyzed feedback..."
    curl -s --location-trusted -X GET "http://localhost:8000/api/v1/feedback/$FB1_ID" \
      -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
    echo ""
fi

echo "==================================================="
echo "✅ All tests complete!"
echo "==================================================="
echo ""
echo "API server is still running at http://localhost:8000"
echo "API docs: http://localhost:8000/docs"
echo "Server PID: $SERVER_PID"
echo ""
echo "To stop: kill $SERVER_PID"
