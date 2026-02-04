from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from src.database.session import get_db
from src.models.user import User
from src.models.organization import Organization
from src.api.schemas import (
    SignupRequest, LoginRequest, TokenResponse, UserResponse,
    GoogleLoginRequest, GoogleSignupRequest
)
from src.api.auth import hash_password, verify_password, create_access_token
from src.api.dependencies import get_current_user
from src.services.google_auth import verify_google_token

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
        role="owner",  # Organization creator is always owner
        joined_at=datetime.utcnow()
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

    # Check if user has a password set (Google-only users don't)
    if not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This account uses Google Sign-In. Please sign in with Google."
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


# ============================================================================
# Google OAuth Endpoints
# ============================================================================


@router.post("/google/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def google_signup(data: GoogleSignupRequest, db: Session = Depends(get_db)):
    """Create a new user and organization using Google account."""

    # Verify Google token
    google_user = verify_google_token(data.id_token)
    if not google_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token"
        )

    email = google_user['email']

    # Check if email already exists
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        # If user exists but hasn't linked Google, suggest login instead
        if not existing_user.google_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account with this email already exists. Please sign in and link your Google account."
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered. Please sign in instead."
        )

    # Create organization
    organization = Organization(
        name=data.organization_name,
        plan="free"
    )
    db.add(organization)
    db.flush()

    # Create user with Google info
    user = User(
        email=email,
        password_hash=None,  # No password for Google-only users
        google_id=google_user['google_id'],
        auth_provider="google",
        organization_id=organization.id,
        role="owner",
        joined_at=datetime.utcnow()
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


@router.post("/google/login", response_model=TokenResponse)
def google_login(data: GoogleLoginRequest, db: Session = Depends(get_db)):
    """Login with Google account."""

    # Verify Google token
    google_user = verify_google_token(data.id_token)
    if not google_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token"
        )

    email = google_user['email']
    google_id = google_user['google_id']

    # Find user by email
    user = db.query(User).filter(User.email == email).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found with this email. Please sign up first."
        )

    # Link Google account if not already linked
    if not user.google_id:
        user.google_id = google_id
        if user.auth_provider == "email":
            user.auth_provider = "both"  # Now has both email and Google
        db.commit()
    # Verify Google ID matches (security check)
    elif user.google_id != google_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This email is associated with a different Google account."
        )

    # Create JWT token
    access_token = create_access_token({
        "user_id": user.id,
        "organization_id": user.organization_id,
        "role": user.role
    })

    return TokenResponse(access_token=access_token)
