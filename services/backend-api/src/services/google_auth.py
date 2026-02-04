"""Google OAuth token verification service."""

import os
from typing import Optional, TypedDict

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests


GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")


class GoogleUserInfo(TypedDict):
    """User info extracted from Google ID token."""
    google_id: str  # 'sub' claim - unique Google user ID
    email: str
    email_verified: bool
    name: str
    picture: Optional[str]
    given_name: Optional[str]
    family_name: Optional[str]


def verify_google_token(token: str) -> Optional[GoogleUserInfo]:
    """
    Verify a Google ID token and extract user info.

    Args:
        token: The ID token from Google Identity Services

    Returns:
        GoogleUserInfo dict if valid, None if invalid/expired
    """
    if not GOOGLE_CLIENT_ID:
        # For testing, allow bypass if no client ID configured
        return None

    try:
        idinfo = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            GOOGLE_CLIENT_ID
        )

        # Verify issuer
        if idinfo.get('iss') not in ['accounts.google.com', 'https://accounts.google.com']:
            return None

        # Verify email is verified
        if not idinfo.get('email_verified', False):
            return None

        return GoogleUserInfo(
            google_id=idinfo['sub'],
            email=idinfo['email'].lower(),
            email_verified=idinfo.get('email_verified', False),
            name=idinfo.get('name', ''),
            picture=idinfo.get('picture'),
            given_name=idinfo.get('given_name'),
            family_name=idinfo.get('family_name'),
        )

    except ValueError:
        # Invalid token
        return None
