import hmac
import json
import logging
import os
import secrets
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from pydantic import BaseModel
import httpx
from cryptography.fernet import InvalidToken
from src.database.session import get_db
from src.models.user import User
from src.models.organization import Organization
from src.models.oidc_config import OidcConfig
from src.models.saml_config import SamlConfig
from src.api.schemas import (
    SignupRequest, LoginRequest, TokenResponse, UserResponse,
    GoogleLoginRequest, GoogleSignupRequest,
    PreferencesResponse, PreferencesUpdateRequest,
)
from src.api.auth import hash_password, verify_password, create_access_token
from src.api.dependencies import get_current_user
from src.services.google_auth import verify_google_access_token
from src.services.oidc_provider import OidcProvider, OidcValidationError
from src.services.saml_provider import SamlProvider, SamlValidationError, SAML_ACS_PATH
from src.services.saml_replay import register_request, consume_request, ConsumeOutcome
from src.utils.ssrf import SsrfError
from src.api.routes._oidc_state import (
    sign_state, verify_state, hash_nonce, make_pkce, STATE_TTL_SECONDS,
)

logger = logging.getLogger(__name__)

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
    from src.config.plans import _is_self_hosted
    # In self-hosted mode every org is treated as enterprise — all features
    # unlocked, no plan gating on the frontend.
    effective_plan = "enterprise" if _is_self_hosted() else (
        current_user.organization.plan or "free"
    )
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        organization_id=current_user.organization_id,
        role=current_user.role,
        plan=effective_plan,
        created_at=current_user.created_at,
        weekly_digest_enabled=current_user.weekly_digest_enabled,
        is_system_admin=current_user.is_system_admin,
    )


# ============================================================================
# User Preferences Endpoints
# ============================================================================


@router.get("/me/preferences", response_model=PreferencesResponse)
def get_preferences(current_user: User = Depends(get_current_user)):
    """Get current user's notification preferences."""
    return PreferencesResponse(
        weekly_digest_enabled=current_user.weekly_digest_enabled,
        daily_digest_enabled=current_user.daily_digest_enabled,
        alert_channels=current_user.alert_channels,
        daily_digest_hour=current_user.daily_digest_hour,
        weekly_digest_day=current_user.weekly_digest_day,
        weekly_digest_hour=current_user.weekly_digest_hour,
    )


@router.patch("/me/preferences", response_model=PreferencesResponse)
def update_preferences(
    data: PreferencesUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update current user's notification preferences."""
    if data.weekly_digest_enabled is not None:
        current_user.weekly_digest_enabled = data.weekly_digest_enabled

    if data.daily_digest_enabled is not None:
        current_user.daily_digest_enabled = data.daily_digest_enabled

    if data.alert_channels is not None:
        current_user.alert_channels = data.alert_channels.model_dump()

    if data.daily_digest_hour is not None:
        current_user.daily_digest_hour = data.daily_digest_hour

    if data.weekly_digest_day is not None:
        current_user.weekly_digest_day = data.weekly_digest_day

    if data.weekly_digest_hour is not None:
        current_user.weekly_digest_hour = data.weekly_digest_hour

    db.commit()
    db.refresh(current_user)

    return PreferencesResponse(
        weekly_digest_enabled=current_user.weekly_digest_enabled,
        daily_digest_enabled=current_user.daily_digest_enabled,
        alert_channels=current_user.alert_channels,
        daily_digest_hour=current_user.daily_digest_hour,
        weekly_digest_day=current_user.weekly_digest_day,
        weekly_digest_hour=current_user.weekly_digest_hour,
    )


# ============================================================================
# Google OAuth Endpoints
# ============================================================================


@router.post("/google/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def google_signup(data: GoogleSignupRequest, db: Session = Depends(get_db)):
    """Create a new user and organization using Google account."""

    # Verify Google access token
    google_user = await verify_google_access_token(data.access_token)
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
async def google_login(data: GoogleLoginRequest, db: Session = Depends(get_db)):
    """Login with Google account."""

    # Verify Google access token
    google_user = await verify_google_access_token(data.access_token)
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


# ============================================================================
# OIDC SSO Status Probe
# ============================================================================


DEFAULT_OIDC_BUTTON_LABEL = "Sign in with SSO"


class OidcStatusResponse(BaseModel):
    enabled: bool
    button_label: str


@router.get("/oidc/status", response_model=OidcStatusResponse)
def get_oidc_status(db: Session = Depends(get_db)):
    """
    Public, unauthenticated probe the login page polls before showing an SSO
    button. Leaks nothing beyond enabled/button_label — never issuer_url,
    client_id, allowed_email_domains, or org id. Never 500s when unconfigured.
    """
    config = db.query(OidcConfig).filter(OidcConfig.enabled.is_(True)).first()
    if not config:
        return OidcStatusResponse(enabled=False, button_label=DEFAULT_OIDC_BUTTON_LABEL)
    return OidcStatusResponse(enabled=True, button_label=config.button_label)


# ============================================================================
# SAML SSO Status Probe (saml-sso: config-model-and-crud aspect)
# ============================================================================


DEFAULT_SAML_BUTTON_LABEL = "Sign in with SSO"


class SamlStatusResponse(BaseModel):
    enabled: bool
    button_label: str


@router.get("/saml/status", response_model=SamlStatusResponse)
def get_saml_status(db: Session = Depends(get_db)):
    """
    Public, unauthenticated probe the login page polls before showing a SAML
    SSO button. Leaks nothing beyond enabled/button_label. Never 500s when
    unconfigured.
    """
    config = db.query(SamlConfig).filter(SamlConfig.enabled.is_(True)).first()
    if not config:
        return SamlStatusResponse(enabled=False, button_label=DEFAULT_SAML_BUTTON_LABEL)
    return SamlStatusResponse(enabled=True, button_label=config.button_label)


# ============================================================================
# OIDC SSO Login Flow — /start
# ============================================================================
#
# No prior session: this endpoint is hit by an UNAUTHENTICATED browser. The
# signed `state` carries ONLY a CSRF nonce hash — never a user/org id (see
# docs/planning/oidc-sso/oidc-login-flow/spec.md, "load-bearing divergence
# from the Salesforce precedent"). Identity is resolved later, in /callback,
# from the validated ID token.
#
# The callback-path-scoped HttpOnly+Secure cookie set below carries the
# PKCE verifier + OIDC nonce + session nonce needed by /callback — it never
# leaves the browser<->this backend and carries no long-lived secret.

OIDC_CALLBACK_PATH = "/api/v1/auth/oidc/callback"
OIDC_SESSION_COOKIE = "oidc_session"


def _frontend_url() -> str:
    return os.getenv("FRONTEND_URL", "http://localhost:3000")


def _backend_url() -> str:
    return os.getenv("BACKEND_URL", "http://localhost:8000")


@router.get("/oidc/start")
def oidc_start(db: Session = Depends(get_db)):
    """
    Redirect an unauthenticated user to the enabled OIDC IdP to start SSO
    login. Never 500s: a missing/disabled config or any discovery/SSRF
    failure redirects to the frontend login page with a generic error
    instead of raising or leaking issuer/validation internals.
    """
    config = db.query(OidcConfig).filter(OidcConfig.enabled.is_(True)).first()
    if not config:
        return RedirectResponse(
            url=f"{_frontend_url()}/login?sso_error=disabled",
            status_code=status.HTTP_302_FOUND,
        )

    try:
        provider = OidcProvider.from_config(config)
        code_verifier, code_challenge = make_pkce()
        oidc_nonce = secrets.token_urlsafe(32)
        session_nonce = secrets.token_urlsafe(32)
        state = sign_state(hash_nonce(session_nonce))
        redirect_uri = f"{_backend_url()}{OIDC_CALLBACK_PATH}"
        auth_url = provider.authorization_url(state, oidc_nonce, code_challenge, redirect_uri)
    except (SsrfError, OidcValidationError, httpx.HTTPError, KeyError, ValueError, InvalidToken) as exc:
        logger.error("OIDC start failed for config %s: %s", config.id, exc)
        return RedirectResponse(
            url=f"{_frontend_url()}/login?sso_error=config",
            status_code=status.HTTP_302_FOUND,
        )

    redirect = RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)
    cookie_payload = json.dumps({
        "session_nonce": session_nonce,
        "code_verifier": code_verifier,
        "oidc_nonce": oidc_nonce,
    })
    redirect.set_cookie(
        key=OIDC_SESSION_COOKIE,
        value=cookie_payload,
        max_age=STATE_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
        path=OIDC_CALLBACK_PATH,
    )
    return redirect


# ============================================================================
# OIDC SSO Login Flow — /callback
# ============================================================================
#
# THE SECURITY CORE of this feature. This endpoint is hit by an
# UNAUTHENTICATED browser returning from the IdP. Every failure path below
# redirects to a GENERIC `{FRONTEND_URL}/login?sso_error=<code>` — never an
# HTTPException with IdP/validation detail — and creates/links no user.
# Identity is resolved solely from the validated ID token (never from
# `state`, which carries only a CSRF nonce hash — see spec.md's
# "load-bearing divergence from the Salesforce precedent").


@router.get("/oidc/callback")
def oidc_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Complete OIDC login: verify the CSRF state + nonce-cookie binding,
    exchange the authorization code, validate the ID token, enforce
    `email_verified` and the M12 domain allowlist, resolve identity
    (oidc_sub then email) to link or JIT-provision a `User`, mint an
    internal JWT, and redirect to the frontend with the token in a URL
    FRAGMENT (never a query param — never logged/referred).
    """

    def _error_redirect(error_code: str) -> RedirectResponse:
        redirect = RedirectResponse(
            url=f"{_frontend_url()}/login?sso_error={error_code}",
            status_code=status.HTTP_302_FOUND,
        )
        redirect.delete_cookie(OIDC_SESSION_COOKIE, path=OIDC_CALLBACK_PATH)
        return redirect

    # (1) User denied consent at the IdP.
    if error:
        return _error_redirect("denied")

    # (2) Read + parse the callback-path-scoped session cookie set by /start.
    cookie_raw = request.cookies.get(OIDC_SESSION_COOKIE)
    if not cookie_raw:
        return _error_redirect("state")
    try:
        session_data = json.loads(cookie_raw)
        session_nonce = session_data["session_nonce"]
        code_verifier = session_data["code_verifier"]
        oidc_nonce = session_data["oidc_nonce"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return _error_redirect("state")

    # (3) Verify the signed `state` and bind it to the session-nonce cookie
    # (CSRF protection, AC9). hmac.compare_digest guards against timing leaks.
    payload = verify_state(state) if state else None
    if payload is None:
        return _error_redirect("state")
    if not hmac.compare_digest(str(payload.get("nonce_hash", "")), hash_nonce(session_nonce)):
        return _error_redirect("state")

    if not code:
        return _error_redirect("state")

    config = db.query(OidcConfig).filter(OidcConfig.enabled.is_(True)).first()
    if not config:
        return _error_redirect("disabled")

    redirect_uri = f"{_backend_url()}{OIDC_CALLBACK_PATH}"

    # (4) Exchange the code server-side. Any network/SSRF/token-endpoint
    # failure maps to a single generic error — detail stays server-side.
    try:
        provider = OidcProvider.from_config(config)
        tokens = provider.exchange_code(code, code_verifier, redirect_uri)
    except (SsrfError, OidcValidationError, httpx.HTTPError, KeyError, ValueError, InvalidToken) as exc:
        logger.error("OIDC code exchange failed for config %s: %s", config.id, exc)
        return _error_redirect("exchange")

    # (5) Validate the ID token (signature vs JWKS, iss, aud, exp/nbf, nonce).
    try:
        claims = provider.validate_id_token(tokens["id_token"], oidc_nonce)
    except (OidcValidationError, KeyError) as exc:
        logger.error("OIDC id_token validation failed for config %s: %s", config.id, exc)
        return _error_redirect("token")

    # (6) email_verified gate (M9/D6) — required to link or provision.
    if claims.get("email_verified") is not True:
        return _error_redirect("unverified")

    email = claims.get("email")
    if not email:
        return _error_redirect("unverified")
    email = email.lower()
    sub = claims.get("sub")
    if not sub:
        # `sub` is OIDC-mandatory. Without it, `User.oidc_sub == sub` would
        # compile to `WHERE oidc_sub IS NULL`, matching every existing
        # password/Google user and letting `.first()` mint a token for the
        # lowest-id row (account takeover) — reject before any
        # identity-resolution query runs.
        return _error_redirect("token")

    # (7) M12 domain allowlist — empty/absent list is deny-all.
    allowed_domains = [d.lower() for d in (config.allowed_email_domains or [])]
    email_domain = email.rsplit("@", 1)[-1]
    if email_domain not in allowed_domains:
        return _error_redirect("domain")

    # (8) Identity resolution — oidc_sub first (a returning SSO user may have
    # since changed their IdP-side email), then email (link an existing
    # password/Google user), else JIT-provision a new member.
    # NOTE (follow-up): oidc_sub is globally unique but OIDC 'sub' is only
    # unique per-issuer; if the enabled config is ever repointed to a
    # different IdP that reuses a sub, bind identity to issuer (e.g.
    # store/compare oidc_iss or scope on organization_id). Not exploitable
    # today — D5 pins one enabled config and iss is validated.
    user = db.query(User).filter(User.oidc_sub == sub).first()
    if not user:
        # Case-insensitive: existing password/Google users may be stored
        # with mixed-case emails; `email` here is already lowercased.
        user = db.query(User).filter(func.lower(User.email) == email).first()
        if user:
            user.oidc_sub = sub
            if user.auth_provider in ("email", "google"):
                user.auth_provider = "both"
            db.commit()
            db.refresh(user)
        else:
            user = User(
                email=email,
                password_hash=None,
                oidc_sub=sub,
                auth_provider="oidc",
                organization_id=config.organization_id,
                role="member",
                joined_at=datetime.utcnow(),
            )
            db.add(user)
            db.commit()
            db.refresh(user)

    access_token = create_access_token({
        "user_id": user.id,
        "organization_id": user.organization_id,
        "role": user.role,
    })

    # (9) Token to an unauthenticated browser via URL FRAGMENT, never query —
    # the redirect base is always the fixed configured FRONTEND_URL, never
    # request/IdP-derived (open-redirect guard, spec R3).
    redirect = RedirectResponse(
        url=f"{_frontend_url()}/login/callback#token={access_token}",
        status_code=status.HTTP_302_FOUND,
    )
    redirect.delete_cookie(OIDC_SESSION_COOKIE, path=OIDC_CALLBACK_PATH)
    return redirect


# ============================================================================
# SAML 2.0 SSO Login Flow (saml-sso: login-routes-and-identity aspect)
# ============================================================================
#
# Two routes, both riding the existing `auth.router` (prefix /api/v1/auth):
#   GET  /saml/login     — SP-initiated start; 302 to the IdP.
#   POST /saml/callback  — the Assertion Consumer Service (ACS).
#
# Unlike OIDC, there is NO session cookie: the browser POSTs the SAMLResponse
# back cross-site, so a SameSite=Lax cookie would not be sent. RelayState is an
# HMAC-signed nonce hash (freshness/HMAC proof only — no identity, no trust
# weight); the real anti-forgery controls live at the ACS (see below).
#
# `SAML_SSO_ERROR_CODES` documents every `sso_error` this flow can emit; the
# frontend `getSsoErrorMessage` map (next aspect) is the human-facing copy.
SAML_SSO_ERROR_CODES = frozenset({
    "disabled",     # no enabled SamlConfig at /login or ACS
    "config",       # SamlProvider.from_config / build_authn_request raised SsrfError/ValueError
    "state",        # RelayState missing / bad HMAC / TTL-expired at ACS
    "signature",    # assertion unsigned / wrong cert / XSW
    "assertion",    # malformed response, missing InResponseTo, or any UNEXPECTED provider error
    "audience",     # Audience != SP entity id
    "recipient",    # Destination/Recipient != ACS URL
    "expired",      # NotBefore/NotOnOrAfter outside skew, OR replay-store expired
    "replay",       # InResponseTo already consumed
    "unsolicited",  # InResponseTo unknown to the replay store
    "unverified",   # assertion carries no email (SAML has no email_verified)
    "domain",       # email domain not in allowed_email_domains (empty = deny-all)
    "token",        # null/empty NameID subject — the account-takeover guard
})


@router.get("/saml/login")
def saml_login(db: Session = Depends(get_db)):
    """
    SP-initiated SAML start. Redirect an unauthenticated user to the enabled
    SAML IdP. Never 500s: a missing/disabled config or any provider/SSRF/value
    error (including a replay-store write failure) redirects to the frontend
    login page with a generic error instead of raising or leaking IdP internals.
    """
    config = db.query(SamlConfig).filter(SamlConfig.enabled.is_(True)).first()
    if not config:
        return RedirectResponse(
            url=f"{_frontend_url()}/login?sso_error=disabled",
            status_code=status.HTTP_302_FOUND,
        )

    try:
        provider = SamlProvider.from_config(config)
        # RelayState = signed(hash(random)) — HMAC/freshness proof, carries no
        # identity (mirrors the OIDC `state`, minus the session-nonce cookie).
        relay_state = sign_state(hash_nonce(secrets.token_urlsafe(32)))
        redirect_url, request_id = provider.build_authn_request(relay_state)
        # Persist the issued request_id as PENDING so the ACS can one-time
        # consume its InResponseTo. Inside the try: a DB error also degrades to
        # sso_error=config, never a 500.
        register_request(db, request_id=request_id, organization_id=config.organization_id)
    except (SsrfError, ValueError) as exc:
        logger.error("SAML login start failed for config %s: %s", config.id, exc)
        return RedirectResponse(
            url=f"{_frontend_url()}/login?sso_error=config",
            status_code=status.HTTP_302_FOUND,
        )

    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)


def _extract_saml_in_response_to(saml_response_b64: str) -> Optional[str]:
    """Read the SAML Response `@InResponseTo` — a NON-identity field — so the
    ACS can key it into the server-side replay store.

    Read from the raw XML BEFORE signature validation, which is safe: the value
    is used ONLY as a lookup key into the pending-request store (a forged /
    attacker-chosen value simply resolves to unsolicited or replay, and the
    consume happens only AFTER the assertion is cryptographically validated).
    Identity (subject/email) is NEVER read here — it comes solely from the
    provider's validated `ValidatedAssertion`, closing the XSW door. Returns
    None if the body is unparseable (never raises)."""
    try:
        from onelogin.saml2.utils import OneLogin_Saml2_Utils
        from onelogin.saml2.xml_utils import OneLogin_Saml2_XML

        raw = OneLogin_Saml2_Utils.b64decode(saml_response_b64)
        doc = OneLogin_Saml2_XML.to_etree(raw)
        return doc.get("InResponseTo") or None
    except Exception:  # noqa: BLE001 - parse failure is not fatal; -> unsolicited
        return None


@router.post("/saml/callback")
def saml_callback(
    SAMLResponse: str = Form(...),
    RelayState: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """
    SAML Assertion Consumer Service (ACS).

    AUTH-EXEMPT and CSRF-EXEMPT **by design**. A browser returning from the IdP
    POSTs cross-site, so a SameSite=Lax session cookie would not be sent — a
    cookie-based CSRF token is structurally impossible here. The trust controls
    are instead:
      (1) the XML SIGNATURE over the assertion, verified against the
          operator-configured IdP cert (an attacker cannot mint a valid
          signature); and
      (2) the one-time `InResponseTo` CONSUME against the server-side replay
          store (a captured assertion cannot be replayed; an unsolicited
          response with an unknown InResponseTo is rejected).
    `RelayState` is an HMAC-signed nonce hash with NO identity and NO trust
    weight — it only proves the redirect was minted by our /saml/login within
    the TTL (defense in depth). Forging/omitting it yields sso_error=state;
    forging the assertion yields signature; replaying yields replay.

    Never 500s: every failure path redirects to the FIXED FRONTEND_URL with a
    generic ?sso_error= (detail stays server-side in logs), and creates/links
    no user. Validation runs BEFORE the replay consume so a forged POST can
    never burn a legitimate user's pending request_id.
    """

    def _err(code: str) -> RedirectResponse:
        # Base is ALWAYS the fixed configured FRONTEND_URL — never request/IdP/
        # RelayState-derived (open-redirect guard). No user created/linked here.
        return RedirectResponse(
            url=f"{_frontend_url()}/login?sso_error={code}",
            status_code=status.HTTP_302_FOUND,
        )

    try:
        # (1) RelayState: HMAC + TTL only. Carries a nonce hash, no identity.
        if not RelayState or verify_state(RelayState) is None:
            return _err("state")

        # (2) Enabled config required to know the cert/entityId to validate against.
        config = db.query(SamlConfig).filter(SamlConfig.enabled.is_(True)).first()
        if not config:
            return _err("disabled")

        # (3) Validate the SAML Response (signature, XSW-resistance, Audience,
        #     Recipient/Destination, NotBefore/NotOnOrAfter, Issuer,
        #     InResponseTo). Pure crypto — no DB. ANY unexpected (non-typed)
        #     exception maps to a generic `assertion` error, NEVER a 500 / stack
        #     trace on this unauthenticated endpoint.
        in_response_to = _extract_saml_in_response_to(SAMLResponse)
        acs_url = f"{_backend_url()}{SAML_ACS_PATH}"
        try:
            provider = SamlProvider.from_config(config)
            assertion = provider.validate_response(
                SAMLResponse,
                expected_in_response_to=in_response_to,
                acs_url=acs_url,
            )
        except SamlValidationError as exc:
            logger.error(
                "SAML assertion validation failed for config %s: code=%s",
                config.id, exc.code,
            )
            return _err(exc.code)
        except SsrfError as exc:
            logger.error("SAML provider SSRF for config %s: %s", config.id, exc)
            return _err("config")
        except Exception as exc:  # noqa: BLE001 - unauthenticated ACS must never 500
            logger.error(
                "SAML ACS unexpected validation error for config %s: %s",
                config.id, exc,
            )
            return _err("assertion")

        # (4) Replay/unsolicited/expired: one-time conditional consume of the
        #     InResponseTo. Runs only AFTER the assertion is cryptographically
        #     trusted, so a forged POST cannot consume a real pending request.
        outcome = consume_request(db, request_id=in_response_to or "")
        if outcome != ConsumeOutcome.OK:
            return _err(outcome.value)  # "replay" | "unsolicited" | "expired"

        # (5) Identity resolution — mirrors the OIDC callback in shape. SAML has
        #     no email_verified field: a validly-signed assertion's email is
        #     trusted (the IdP asserts it), so `unverified` here means "no email".
        email = assertion.email
        if not email:
            return _err("unverified")
        email = email.lower()
        subject = assertion.subject
        if not subject:
            # KEEP the null-subject rejection: `User.saml_subject == None`
            # compiles to `WHERE saml_subject IS NULL`, matching every existing
            # password/Google/OIDC user; `.first()` would then mint a token for
            # the lowest-id row (the org owner) — account takeover. Reject before
            # any identity-resolution query runs.
            return _err("token")

        # Domain allowlist — empty/absent list is deny-all (matches OIDC).
        allowed_domains = [d.lower() for d in (config.allowed_email_domains or [])]
        if email.rsplit("@", 1)[-1] not in allowed_domains:
            return _err("domain")

        # saml_subject first (a returning SSO user whose IdP email changed), then
        # case-insensitive email link, else JIT-provision a new member.
        user = db.query(User).filter(User.saml_subject == subject).first()
        if not user:
            user = db.query(User).filter(func.lower(User.email) == email).first()
            if user:
                user.saml_subject = subject
                if user.auth_provider in ("email", "google", "oidc"):
                    user.auth_provider = "both"
                db.commit()
                db.refresh(user)
            else:
                user = User(
                    email=email,
                    password_hash=None,
                    saml_subject=subject,
                    auth_provider="saml",
                    organization_id=config.organization_id,
                    role="member",
                    joined_at=datetime.utcnow(),
                )
                db.add(user)
                db.commit()
                db.refresh(user)

        access_token = create_access_token({
            "user_id": user.id,
            "organization_id": user.organization_id,
            "role": user.role,
        })
        # (6) Token via URL FRAGMENT on the FIXED FRONTEND_URL — reuse the
        #     existing public /login/callback route (open-redirect guard); never
        #     reflect an attacker/IdP/RelayState-derived URL.
        return RedirectResponse(
            url=f"{_frontend_url()}/login/callback#token={access_token}",
            status_code=status.HTTP_302_FOUND,
        )
    except Exception as exc:  # noqa: BLE001 - belt-and-braces: the ACS never 500s
        logger.error("SAML ACS unhandled error: %s", exc)
        return _err("assertion")
