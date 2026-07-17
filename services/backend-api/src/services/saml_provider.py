"""
SAML provider service: build an SP-initiated (unsigned) AuthnRequest and
validate a returned SAML Response/Assertion to a trusted identity.

No route wiring lives here — `src/api/routes/auth.py` (next aspect) calls this
service. Mirrors the shape of `oidc_provider.py` (module `_now()`, typed error,
one class built `from_config`).

Security posture (R2 / M8):
- ALL signature + condition validation is delegated to `python3-saml`
  (OneLogin) via `OneLogin_Saml2_Auth.process_response(request_id=...)` with
  `strict=True` and `wantAssertionsSigned=True`. This one call enforces the XML
  signature over the assertion (against the configured IdP cert), Issuer,
  Audience, Destination/Recipient, NotBefore/NotOnOrAfter, and InResponseTo.
- Identity (subject/email/attributes) is read ONLY from the library's validated
  getters (`get_nameid`, `get_nameid_format`, `get_attributes`) — the raw XML is
  NEVER re-parsed for identity. That is precisely how XML Signature Wrapping
  (XSW) slips in: a forged, unsigned assertion wrapped around a signed one would
  be picked up by a naive parser, but never by the validated getters.
- Unsigned assertions are rejected (`wantAssertionsSigned=True`); a
  response-signed-but-assertion-unsigned message is likewise rejected.
- The null-subject rejection is kept (a `NameID`-less assertion is refused
  before any identity is returned), mirroring the OIDC `sub` guard — without it
  a downstream `User.saml_subject == None` lookup would match every non-SAML
  account.
- The IdP SSO URL is SSRF-gated (`_require_https_public` -> `assert_host_not_ssrf`)
  at build time, re-gated on use (defense-in-depth vs the config-save gate).

Clock skew: `python3-saml` validates NotBefore/NotOnOrAfter against its own
`now()` with NO skew knob. We add a supplemental ±60s re-check (Option A): if
`process_response` fails purely on a timestamp condition, we re-read the
timestamps from the already-signature-validated assertion document and accept
iff within ±60s. Reading *timestamps* (not identity) after signature validation
does not reintroduce XSW, because those bytes were signature-checked.

Time is read through the module-level `_now()` so tests can monkeypatch it.
"""
import os
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.constants import OneLogin_Saml2_Constants
from onelogin.saml2.utils import OneLogin_Saml2_Utils

from src.utils.ssrf import SsrfError, assert_host_not_ssrf

# Routes the next aspect will mount; SP identifiers derive from these + BACKEND_URL.
SAML_ACS_PATH = "/api/v1/auth/saml/callback"
SAML_METADATA_PATH = "/api/v1/auth/saml/metadata"
SAML_REQUEST_TTL_SECONDS = int(os.getenv("SAML_REQUEST_TTL_SECONDS", "600"))
CLOCK_SKEW_SECONDS = 60  # ±60s tolerance on NotBefore/NotOnOrAfter (spec R5)

# sso_error codes this feature emits. The provider raises the first five
# directly; `unsolicited`/`replay` are raised by the replay store at the ACS
# boundary — the full set is defined here as the single source of truth.
SAML_ERROR_CODES = frozenset(
    {"signature", "assertion", "audience", "recipient", "expired", "unsolicited", "replay"}
)

# Default email-attribute chain (first present wins) when NameID is not an email.
_DEFAULT_EMAIL_ATTRS = (
    "email",
    "urn:oid:0.9.2342.19200300.100.1.3",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
)


def _now() -> float:
    """Wall-clock seconds. A thin wrapper so tests can monkeypatch skew/expiry."""
    return time.time()


def _backend_url() -> str:
    """Replicated from auth.py to keep this service route-free."""
    return os.getenv("BACKEND_URL", "http://localhost:8000")


class SamlValidationError(Exception):
    """Typed validation failure. `.code` is one of SAML_ERROR_CODES; the route
    maps it to `?sso_error=`."""

    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True)
class ValidatedAssertion:
    """The only thing `validate_response` returns. `subject` is never None
    (null-subject is rejected before construction)."""
    subject: str
    email: Optional[str]
    attributes: dict


# Error-reason substrings -> sso_error code, first match wins. Default is
# `assertion` so an unknown reason never fails open to success. Ordered so
# more specific phrasings win over generic ones.
_ERROR_REASON_MAP = (
    ("not signed", "assertion"),
    ("unsigned", "assertion"),
    ("no signature", "assertion"),
    ("is not signed", "assertion"),
    ("wantassertionssigned", "assertion"),
    ("signature validation failed", "signature"),
    ("invalid signature", "signature"),
    ("signature", "signature"),
    ("audience", "audience"),
    ("recipient", "recipient"),
    ("destination", "recipient"),
    ("received at", "recipient"),  # "The response was received at X instead of Y"
    ("notonorafter", "expired"),
    ("not on or after", "expired"),
    ("notbefore", "expired"),
    ("not yet valid", "expired"),
    ("is not yet valid", "expired"),
    ("is no longer valid", "expired"),
    ("timestamp", "expired"),
    ("expired", "expired"),
    ("inresponseto", "unsolicited"),
    ("in_response_to", "unsolicited"),
    ("issuer", "assertion"),
)


def _map_error_reason(reason: str) -> str:
    r = (reason or "").lower()
    for needle, code in _ERROR_REASON_MAP:
        if needle in r:
            return code
    return "assertion"


class SamlProvider:
    """One instance per login attempt, built from an org's enabled `SamlConfig` row."""

    def __init__(
        self,
        *,
        sp_entity_id: str,
        acs_url: str,
        idp_entity_id: str,
        idp_sso_url: str,
        idp_x509_cert: str,
        email_attribute: Optional[str] = None,
    ):
        self.sp_entity_id = sp_entity_id
        self.acs_url = acs_url
        self.idp_entity_id = idp_entity_id
        self.idp_sso_url = idp_sso_url
        # PUBLIC signing cert (PEM) — NOT decrypted (contrast OIDC client_secret).
        self.idp_x509_cert = idp_x509_cert
        self.email_attribute = email_attribute
        self._settings_cache: Optional[dict] = None

    @classmethod
    def from_config(cls, cfg) -> "SamlProvider":
        backend_url = _backend_url()
        return cls(
            sp_entity_id=f"{backend_url}{SAML_METADATA_PATH}",
            acs_url=f"{backend_url}{SAML_ACS_PATH}",
            idp_entity_id=cfg.idp_entity_id,
            idp_sso_url=cfg.idp_sso_url,
            idp_x509_cert=cfg.idp_x509_cert,
            email_attribute=getattr(cfg, "email_attribute", None),
        )

    # ── settings ────────────────────────────────────────────────────────

    @staticmethod
    def _cert_body(pem: str) -> str:
        """Strip PEM header/footer lines — OneLogin wants the base64 body only."""
        if not pem:
            return ""
        lines = [
            ln.strip()
            for ln in pem.strip().splitlines()
            if ln.strip() and not ln.strip().startswith("-----")
        ]
        return "".join(lines)

    def _build_settings(self) -> dict:
        if self._settings_cache is not None:
            return self._settings_cache
        self._settings_cache = {
            "strict": True,
            "debug": False,
            "sp": {
                "entityId": self.sp_entity_id,
                "assertionConsumerService": {
                    "url": self.acs_url,
                    "binding": OneLogin_Saml2_Constants.BINDING_HTTP_POST,
                },
                "NameIDFormat": OneLogin_Saml2_Constants.NAMEID_UNSPECIFIED,
            },
            "idp": {
                "entityId": self.idp_entity_id,
                "singleSignOnService": {
                    "url": self.idp_sso_url,
                    "binding": OneLogin_Saml2_Constants.BINDING_HTTP_REDIRECT,
                },
                "x509cert": self._cert_body(self.idp_x509_cert),
            },
            "security": {
                "wantAssertionsSigned": True,
                # `wantMessagesSigned` is intentionally False: we don't require
                # the outer Response element itself to be signed, only the
                # Assertion (wantAssertionsSigned=True, above). This is safe
                # because request<->response binding — the control that stops
                # an attacker from replaying/substituting a validly-signed
                # assertion from an unrelated flow — is enforced independently
                # via the signed assertion's own SubjectConfirmationData/
                # @InResponseTo, which python3-saml checks against the request
                # id we pass to process_response() (see onelogin's response.py
                # get_in_response_to / subject confirmation validation). Since
                # that binding lives inside the signed assertion, requiring
                # message-level signing on top would add no additional
                # anti-substitution guarantee for mainstream IdPs that sign
                # assertions (Okta, Azure AD/Entra, OneLogin, ADFS, Google
                # Workspace, Keycloak all do).
                "wantMessagesSigned": False,
                "wantAssertionsEncrypted": False,
                "wantNameId": True,
                "wantNameIdEncrypted": False,
                # We accept NameID-email with no AttributeStatement, so don't
                # force attributes (a NameID Format=emailAddress carries the email).
                "wantAttributeStatement": False,
                "authnRequestsSigned": False,
                "rejectUnsolicitedResponsesWithInResponseTo": False,
                "requestedAuthnContext": False,
                "signatureAlgorithm": OneLogin_Saml2_Constants.RSA_SHA256,
                "digestAlgorithm": OneLogin_Saml2_Constants.SHA256,
            },
        }
        return self._settings_cache

    # ── SSRF gate ───────────────────────────────────────────────────────

    def _require_https_public(self, url: str) -> str:
        """https-only + non-loopback/private/link-local host. Raises SsrfError."""
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise SsrfError(f"URL {url!r} must use https, got scheme {parsed.scheme!r}")
        host = parsed.hostname
        assert_host_not_ssrf(host)
        return host

    # ── AuthnRequest (SP-initiated, HTTP-Redirect, UNSIGNED) ────────────

    def build_authn_request(self, relay_state: str) -> tuple:
        """Return (redirect_url, request_id). The caller persists request_id via
        the replay store so the ACS can match InResponseTo."""
        self._require_https_public(self.idp_sso_url)

        backend = urlparse(_backend_url())
        request_data = {
            "https": "on",
            "http_host": backend.netloc,
            "script_name": SAML_ACS_PATH,
            "get_data": {},
            "post_data": {},
        }
        auth = OneLogin_Saml2_Auth(request_data, old_settings=self._build_settings())
        redirect_url = auth.login(return_to=relay_state)
        request_id = auth.get_last_request_id()
        return redirect_url, request_id

    # ── Response validation (delegated) ─────────────────────────────────

    def validate_response(
        self,
        saml_response_b64: str,
        *,
        expected_in_response_to: str,
        acs_url: str,
    ) -> ValidatedAssertion:
        acs = urlparse(acs_url)
        request_data = {
            "https": "on",
            "http_host": acs.netloc,
            "script_name": acs.path,
            "get_data": {},
            "post_data": {"SAMLResponse": saml_response_b64},
        }
        auth = OneLogin_Saml2_Auth(request_data, old_settings=self._build_settings())

        try:
            auth.process_response(request_id=expected_in_response_to)
        except Exception as exc:  # library may raise on malformed input
            raise SamlValidationError("assertion", str(exc)) from exc

        errors = auth.get_errors()
        if errors:
            reason = auth.get_last_error_reason() or ""
            raise SamlValidationError(_map_error_reason(reason), f"{errors}: {reason}")

        # Identity read ONLY from the validated getters — never the raw XML.
        name_id = auth.get_nameid()
        if not name_id:
            raise SamlValidationError("assertion", "missing or empty NameID (null subject)")
        name_id_format = auth.get_nameid_format() or ""
        attributes = auth.get_attributes() or {}

        # ±60s clock-skew supplement (Option A). The installed python3-saml
        # 1.16.0 has a *native* ALLOWED_CLOCK_DRIFT of 300s on the Conditions
        # window — contrary to the plan's premise of "no knob". To honour the
        # spec's ±60s exactly (and be strictly MORE secure than the library
        # default), we re-check the Conditions NotBefore/NotOnOrAfter of the
        # already-signature-validated single assertion and reject anything
        # outside ±60s. XSW-safe: only timestamps are read (never identity), the
        # bytes were signature-checked, and the library already rejected any
        # multi-assertion (wrapping) document above.
        self._enforce_skew_tolerance(saml_response_b64)

        email = self._extract_email(name_id, name_id_format, attributes)
        return ValidatedAssertion(subject=name_id, email=email, attributes=attributes)

    # ── helpers ─────────────────────────────────────────────────────────

    def _enforce_skew_tolerance(self, saml_response_b64: str) -> None:
        """Reject the validated assertion if `now` is outside
        [NotBefore - 60s, NotOnOrAfter + 60s] on the Conditions element.

        Runs only after the library's full validation succeeded, so exactly one
        signed assertion exists; reading its Conditions timestamps here does not
        reintroduce XSW. Raises SamlValidationError("expired") on violation."""
        from onelogin.saml2.xml_utils import OneLogin_Saml2_XML

        raw = OneLogin_Saml2_Utils.b64decode(saml_response_b64)
        doc = OneLogin_Saml2_XML.to_etree(raw)
        conditions = OneLogin_Saml2_XML.query(doc, "//saml:Assertion/saml:Conditions")
        now = _now()
        for cond in conditions:
            nb = cond.get("NotBefore")
            nooa = cond.get("NotOnOrAfter")
            if nb:
                nb_t = OneLogin_Saml2_Utils.parse_SAML_to_time(nb)
                if now < nb_t - CLOCK_SKEW_SECONDS:
                    raise SamlValidationError(
                        "expired", "assertion not yet valid beyond ±60s skew"
                    )
            if nooa:
                nooa_t = OneLogin_Saml2_Utils.parse_SAML_to_time(nooa)
                if now > nooa_t + CLOCK_SKEW_SECONDS:
                    raise SamlValidationError(
                        "expired", "assertion expired beyond ±60s skew"
                    )

    def _extract_email(self, name_id: str, name_id_format: str, attributes: dict) -> Optional[str]:
        # 1. NameID when Format=emailAddress and it looks like an email.
        if name_id_format.endswith("emailAddress") and "@" in name_id:
            return name_id.lower()
        # 2. Configured override attribute.
        if self.email_attribute and self.email_attribute in attributes:
            vals = attributes[self.email_attribute]
            if vals:
                return str(vals[0]).lower()
        # 3. Default chain.
        for attr in _DEFAULT_EMAIL_ATTRS:
            vals = attributes.get(attr)
            if vals:
                return str(vals[0]).lower()
        return None
