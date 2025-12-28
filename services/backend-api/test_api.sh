#!/bin/bash

# Kill any existing servers
pkill -f "uvicorn.*8000" 2>/dev/null || true
sleep 2

# Start server in background
source venv/bin/activate
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 > /tmp/backend-api.log 2>&1 &
SERVER_PID=$!

# Wait for server to start
sleep 5

echo "Testing API endpoints..."
echo ""

# Test root endpoint
echo "1. Testing root endpoint:"
curl -s http://localhost:8000/ | python3 -m json.tool
echo ""

# Test signup
echo "2. Testing signup:"
TOKEN_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password123","organization_name":"Test Organization"}')

echo "$TOKEN_RESPONSE" | python3 -m json.tool
TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))")
echo ""

# Test login
echo "3. Testing login:"
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password123"}' | python3 -m json.tool
echo ""

# Test /me endpoint with token
if [ -n "$TOKEN" ]; then
    echo "4. Testing /me endpoint with token:"
    curl -s -X GET http://localhost:8000/api/v1/auth/me \
      -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
    echo ""
fi

echo "API server is running at http://localhost:8000"
echo "API docs available at http://localhost:8000/docs"
echo "Server PID: $SERVER_PID"
echo ""
echo "To stop the server: kill $SERVER_PID"
