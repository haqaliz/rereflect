# Week 1 Implementation Guide

**Week**: Month 1, Week 1-2
**Focus**: Backend API - Authentication & Multi-tenancy
**Duration**: 5-10 days
**Goal**: Working auth system with organization isolation

---

## 📋 Week Overview

By end of this week, you'll have:
- ✅ PostgreSQL database with multi-tenant schema
- ✅ FastAPI backend with authentication
- ✅ JWT token-based auth
- ✅ Organization-based data isolation
- ✅ Signup and login endpoints working
- ✅ Tests for tenant isolation

---

## Day 1: Database Setup

### Step 1: Install PostgreSQL

**macOS**:
```bash
brew install postgresql@14
brew services start postgresql@14

# Verify
psql --version  # Should show PostgreSQL 14.x
```

**Ubuntu/Debian**:
```bash
sudo apt-get update
sudo apt-get install postgresql postgresql-contrib

# Start service
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Verify
psql --version
```

---

### Step 2: Create Database

```bash
# Create database
createdb customer_feedback_saas

# Connect to verify
psql customer_feedback_saas

# You should see: customer_feedback_saas=#

# Exit with \q
```

---

### Step 3: Set Up Backend API Project

```bash
cd services/backend-api

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Create requirements.txt
cat > requirements.txt << 'EOF'
fastapi==0.115.0
uvicorn[standard]==0.30.0
sqlalchemy==2.0.32
alembic==1.13.2
psycopg2-binary==2.9.9
pydantic==2.8.2
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.9
pytest==7.4.3
pytest-asyncio==0.21.1
httpx==0.25.2
EOF

# Install dependencies
pip install -r requirements.txt
```

---

### Step 4: Create Project Structure

```bash
mkdir -p src/api/routes
mkdir -p src/models
mkdir -p src/database
mkdir -p tests

touch src/__init__.py
touch src/api/__init__.py
touch src/models/__init__.py
touch src/database/__init__.py
```

---

### Step 5: Set Up Alembic

```bash
# Initialize Alembic
alembic init alembic

# This creates:
# - alembic/ folder
# - alembic.ini file
```

**Edit `alembic.ini`** - Update database URL:
```ini
# Line 63 - change from:
# sqlalchemy.url = driver://user:pass@localhost/dbname

# To:
sqlalchemy.url = postgresql://localhost/customer_feedback_saas
```

**Edit `alembic/env.py`** - Import your models:
```python
# Add after imports (around line 7)
from src.models.base import Base
target_metadata = Base.metadata
```

---

### Step 6: Create Base Model

**File**: `src/models/base.py`

```python
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()
```

---

### Step 7: Create Organization Model

**File**: `src/models/organization.py`

```python
from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from .base import Base


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    plan = Column(String, nullable=False, default="free")  # free, starter, professional, business, enterprise
    stripe_customer_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Organization(id={self.id}, name='{self.name}', plan='{self.plan}')>"
```

---

### Step 8: Create User Model

**File**: `src/models/user.py`

```python
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    role = Column(String, nullable=False, default="member")  # admin, member, viewer
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationship
    organization = relationship("Organization", backref="users")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', role='{self.role}')>"
```

---

### Step 9: Create Feedback Item Model

**File**: `src/models/feedback.py`

```python
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey, Index
from datetime import datetime
from .base import Base


class FeedbackItem(Base):
    __tablename__ = "feedback_items"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    text = Column(Text, nullable=False)
    source = Column(String, nullable=True)  # intercom, zendesk, manual, etc
    sentiment_score = Column(Float, nullable=True)
    sentiment_label = Column(String, nullable=True)  # positive, neutral, negative
    extracted_issue = Column(Text, nullable=True)
    is_urgent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Index for fast queries
    __table_args__ = (
        Index('ix_feedback_org_date', 'organization_id', 'created_at'),
    )

    def __repr__(self):
        return f"<FeedbackItem(id={self.id}, org={self.organization_id}, sentiment='{self.sentiment_label}')>"
```

---

### Step 10: Create Migration

```bash
# Generate migration
alembic revision -m "Initial schema - organizations, users, feedback"

# Edit the generated file in alembic/versions/
# It should auto-detect your models
```

The generated migration should look like:

```python
def upgrade():
    # Creates organizations, users, feedback_items tables
    op.create_table(...)
    ...

def downgrade():
    op.drop_table('feedback_items')
    op.drop_table('users')
    op.drop_table('organizations')
```

**Run migration**:
```bash
alembic upgrade head
```

**Verify**:
```bash
psql customer_feedback_saas

\dt  # List tables - should show organizations, users, feedback_items

\d organizations  # Describe organizations table

\q  # Exit
```

---

## Day 2: Database Session & Config

### Step 11: Create Database Session

**File**: `src/database/session.py`

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://localhost/customer_feedback_saas"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Dependency for FastAPI routes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

---

### Step 12: Create .env File

**File**: `services/backend-api/.env`

```bash
DATABASE_URL=postgresql://localhost/customer_feedback_saas
JWT_SECRET=your-secret-key-change-this-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRATION_DAYS=7
```

**File**: `services/backend-api/.env.example`

```bash
DATABASE_URL=postgresql://localhost/customer_feedback_saas
JWT_SECRET=change-this-to-a-random-secret-key
JWT_ALGORITHM=HS256
JWT_EXPIRATION_DAYS=7
```

---

## Day 3: Authentication Logic

### Step 13: Create Auth Utilities

**File**: `src/api/auth.py`

```python
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import os

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_DAYS = int(os.getenv("JWT_EXPIRATION_DAYS", "7"))


def hash_password(password: str) -> str:
    """Hash a plain password."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=JWT_EXPIRATION_DAYS)
    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """Decode and verify a JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        return None
```

---

### Step 14: Create Pydantic Schemas

**File**: `src/api/schemas.py`

```python
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional


# Auth schemas
class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=100)
    organization_name: str = Field(min_length=2, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# User schemas
class UserResponse(BaseModel):
    id: int
    email: str
    organization_id: int
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


# Organization schemas
class OrganizationResponse(BaseModel):
    id: int
    name: str
    plan: str
    created_at: datetime

    class Config:
        from_attributes = True
```

---

## Day 4: API Endpoints - Auth Routes

### Step 15: Create Auth Routes

**File**: `src/api/routes/auth.py`

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from src.database.session import get_db
from src.models.user import User
from src.models.organization import Organization
from src.api.schemas import SignupRequest, LoginRequest, TokenResponse, UserResponse
from src.api.auth import hash_password, verify_password, create_access_token, decode_access_token

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(data: SignupRequest, db: Session = Depends(get_db)):
    """Create a new user and organization."""

    # Check if email already exists
    existing_user = db.query(User).filter(User.email == data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Create organization
    organization = Organization(
        name=data.organization_name,
        plan="free"
    )
    db.add(organization)
    db.flush()  # Get organization.id

    # Create user
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        organization_id=organization.id,
        role="admin"  # First user is admin
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Create JWT token
    access_token = create_access_token({
        "user_id": user.id,
        "organization_id": user.organization_id,
        "role": user.role
    })

    return TokenResponse(access_token=access_token)


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    """Login with email and password."""

    # Find user
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # Verify password
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # Create JWT token
    access_token = create_access_token({
        "user_id": user.id,
        "organization_id": user.organization_id,
        "role": user.role
    })

    return TokenResponse(access_token=access_token)


@router.get("/me", response_model=UserResponse)
def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information."""
    return current_user
```

---

### Step 16: Create Dependencies

**File**: `src/api/dependencies.py`

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthCredentials
from sqlalchemy.orm import Session
from src.database.session import get_db
from src.models.user import User
from src.models.organization import Organization
from src.api.auth import decode_access_token

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Get current authenticated user from JWT token."""

    token = credentials.credentials
    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    return user


def get_current_org(current_user: User = Depends(get_current_user)) -> Organization:
    """Get current user's organization (for multi-tenant isolation)."""
    return current_user.organization
```

---

### Step 17: Create Main FastAPI App

**File**: `src/api/main.py`

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes import auth

app = FastAPI(
    title="Customer Feedback Analyzer API",
    version="1.0.0",
    description="Multi-tenant SaaS API for customer feedback analysis"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)


@app.get("/")
async def root():
    return {
        "message": "Customer Feedback Analyzer API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

## Day 5: Testing

### Step 18: Run the API

```bash
cd services/backend-api
source venv/bin/activate

uvicorn src.api.main:app --reload --port 8000
```

Visit: http://localhost:8000/docs

---

### Step 19: Test Signup

**Using curl**:
```bash
curl -X POST http://localhost:8000/api/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "password123",
    "organization_name": "Test Org"
  }'
```

**Expected response**:
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

---

### Step 20: Test Login

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "password123"
  }'
```

---

### Step 21: Test Protected Endpoint

```bash
# Get token from signup/login response
TOKEN="eyJ..."

curl -X GET http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

**Expected response**:
```json
{
  "id": 1,
  "email": "test@example.com",
  "organization_id": 1,
  "role": "admin",
  "created_at": "2025-12-27T..."
}
```

---

## Day 6: Write Tests

### Step 22: Create Test File

**File**: `tests/test_auth.py`

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.api.main import app
from src.database.session import get_db
from src.models.base import Base

# Test database
SQLALCHEMY_DATABASE_URL = "postgresql://localhost/customer_feedback_saas_test"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


def test_signup():
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "email": "test@example.com",
            "password": "password123",
            "organization_name": "Test Org"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_signup_duplicate_email():
    # First signup
    client.post(
        "/api/v1/auth/signup",
        json={
            "email": "duplicate@example.com",
            "password": "password123",
            "organization_name": "Test Org"
        }
    )

    # Second signup with same email
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "email": "duplicate@example.com",
            "password": "password123",
            "organization_name": "Another Org"
        }
    )
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"]


def test_login():
    # Create user first
    client.post(
        "/api/v1/auth/signup",
        json={
            "email": "login@example.com",
            "password": "password123",
            "organization_name": "Test Org"
        }
    )

    # Login
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "login@example.com",
            "password": "password123"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data


def test_login_wrong_password():
    # Create user
    client.post(
        "/api/v1/auth/signup",
        json={
            "email": "wrong@example.com",
            "password": "correct_password",
            "organization_name": "Test Org"
        }
    )

    # Login with wrong password
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "wrong@example.com",
            "password": "wrong_password"
        }
    )
    assert response.status_code == 401
```

**Run tests**:
```bash
pytest tests/test_auth.py -v
```

---

## ✅ Week 1 Checklist

Mark these as you complete:

- [ ] PostgreSQL installed and running
- [ ] Database `customer_feedback_saas` created
- [ ] Alembic set up for migrations
- [ ] Database models created (Organization, User, FeedbackItem)
- [ ] Migrations run successfully
- [ ] Authentication utilities implemented (JWT, password hashing)
- [ ] POST /api/v1/auth/signup endpoint working
- [ ] POST /api/v1/auth/login endpoint working
- [ ] GET /api/v1/auth/me endpoint working
- [ ] Multi-tenant dependencies created
- [ ] Tests passing (5+ tests)

---

## 🎯 Success Criteria

By end of Week 1, you should be able to:

1. **Signup**: Create new user + organization
2. **Login**: Get JWT token
3. **Protected Routes**: Access with Bearer token
4. **Multi-tenancy**: Users are scoped to their organization

---

## 📚 Next Steps (Week 2)

Once Week 1 is complete, move to Week 2:
- Organization CRUD endpoints
- Feedback CRUD endpoints
- Multi-tenant query filtering
- More comprehensive tests

See [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md) for Week 2 details.

---

**Update [DEVELOPMENT_TRACKER.md](DEVELOPMENT_TRACKER.md) as you complete tasks!**
