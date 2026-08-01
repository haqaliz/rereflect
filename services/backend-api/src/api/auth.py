import bcrypt
from jose import JWTError, jwt
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# JWT settings
#
# JWT_SECRET has NO default, deliberately. It used to fall back to the literal
# "dev-secret-key" -- a string published in this repository -- while
# .env.example kept the variable commented out. On a default install every auth
# token, OIDC state value and Salesforce OAuth state value was therefore signed
# with a key anyone could read off GitHub, and forging a token for any
# organization needed nothing but the URL.
#
# Same class as INTERNAL_EVENTS_SECRET's "dev-secret" default, fixed on
# feat/integration-auth-tenancy-hardening. That one could fail closed by
# rejecting requests; this one cannot, because a JWT key that refuses to work
# means nobody can log in. So it fails LOUD: refuse to start, with an
# actionable message, rather than starting up quietly forgeable.
#
# Do not restore a default here. tests/test_jwt_secret_required.py fails if you do.
_JWT_SECRET_ENV = os.getenv("JWT_SECRET")

# The historical default, rejected explicitly: it is public, so accepting it
# would let an operator "fix" the startup error by pasting the exact value that
# made their install forgeable in the first place.
_LEAKED_DEFAULT = "dev-secret-key"

_HOW_TO_GENERATE = (
    "Generate one with:  openssl rand -hex 32\n"
    "  (or: python -c 'import secrets; print(secrets.token_hex(32))')\n"
    "then set JWT_SECRET in your environment or .env file and restart."
)

if not _JWT_SECRET_ENV:
    raise RuntimeError(
        "JWT_SECRET is not set.\n"
        "Rereflect signs authentication tokens with it and will not start "
        "without one, because the previous fallback was a value published in "
        "this repository.\n" + _HOW_TO_GENERATE
    )

if _JWT_SECRET_ENV == _LEAKED_DEFAULT:
    raise RuntimeError(
        f"JWT_SECRET is set to {_LEAKED_DEFAULT!r}, which is no longer accepted.\n"
        "That was this project's old built-in default and is public, so any "
        "token signed with it can be forged by anyone.\n" + _HOW_TO_GENERATE
    )

JWT_SECRET = _JWT_SECRET_ENV
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_DAYS = int(os.getenv("JWT_EXPIRATION_DAYS", "7"))


def hash_password(password: str) -> str:
    """Hash a plain password."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )


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
