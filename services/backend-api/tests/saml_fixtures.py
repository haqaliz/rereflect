"""
Test fixtures for SAML provider tests.

Everything is generated in-test with a throwaway RSA key + self-signed X.509
cert (no network, no live IdP). `make_keypair_cert()` yields the PEM pair; the
cert PEM becomes the provider's configured `idp_x509_cert`. `make_signed_response`
assembles a minimal SAML Response and signs the *Assertion* with the library's
own `OneLogin_Saml2_Utils.add_sign`, so the bytes the provider validates are
signed exactly as a real IdP would sign them.

Every rejection case is a one-line `**overrides` tweak on the same template, and
`sign=False` / `sign_key/sign_cert` overrides drive the unsigned / wrong-cert /
XSW variants.
"""
import base64
from datetime import datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from onelogin.saml2.constants import OneLogin_Saml2_Constants
from onelogin.saml2.utils import OneLogin_Saml2_Utils

# Canonical identifiers shared between fixtures and the provider under test.
IDP_ENTITY_ID = "https://idp.example.com/metadata"
IDP_SSO_URL = "https://idp.example.com/sso"
SP_ENTITY_ID = "https://localhost:8000/api/v1/auth/saml/metadata"
ACS_URL = "https://localhost:8000/api/v1/auth/saml/callback"
DEFAULT_IN_RESPONSE_TO = "_req-fixture-0001"
DEFAULT_NAMEID = "user@example.com"


def make_keypair_cert(common_name: str = "idp.example.com"):
    """Return (private_key_pem, cert_pem) as PEM strings — a throwaway signer."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, common_name)]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow() - timedelta(days=1))
        .not_valid_after(datetime.utcnow() + timedelta(days=3650))
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    return key_pem, cert_pem


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _assertion_xml(
    *,
    assertion_id: str,
    issuer: str,
    audience: str,
    recipient: str,
    in_response_to: str,
    name_id: str,
    name_id_format: str,
    not_before: datetime,
    not_on_or_after: datetime,
    session_not_on_or_after: datetime,
    attributes: dict,
    include_subject: bool = True,
    sc_not_on_or_after: datetime = None,
) -> str:
    """One <saml:Assertion> element (string). Kept separate so the XSW variant
    can splice a *second*, forged, unsigned assertion around the signed one."""
    attr_statements = ""
    if attributes:
        attrs = "".join(
            (
                f'<saml:Attribute Name="{name}" '
                f'NameFormat="urn:oasis:names:tc:SAML:2.0:attrname-format:uri">'
                + "".join(
                    f'<saml:AttributeValue xmlns:xs="http://www.w3.org/2001/XMLSchema" '
                    f'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                    f'xsi:type="xs:string">{v}</saml:AttributeValue>'
                    for v in values
                )
                + "</saml:Attribute>"
            )
            for name, values in attributes.items()
        )
        attr_statements = f"<saml:AttributeStatement>{attrs}</saml:AttributeStatement>"

    # SubjectConfirmationData NotOnOrAfter is a *strict* (no-drift) bearer check
    # in python3-saml; keep it independently controllable so skew tests can hold
    # it generously in the future while moving the Conditions window.
    sc_nooa = sc_not_on_or_after if sc_not_on_or_after is not None else not_on_or_after
    subject = ""
    if include_subject:
        subject = (
            "<saml:Subject>"
            f'<saml:NameID Format="{name_id_format}">{name_id}</saml:NameID>'
            '<saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">'
            f'<saml:SubjectConfirmationData NotOnOrAfter="{_iso(sc_nooa)}" '
            f'Recipient="{recipient}" InResponseTo="{in_response_to}"/>'
            "</saml:SubjectConfirmation>"
            "</saml:Subject>"
        )

    return (
        f'<saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
        f'ID="{assertion_id}" Version="2.0" IssueInstant="{_iso(not_before)}">'
        f"<saml:Issuer>{issuer}</saml:Issuer>"
        f"{subject}"
        f'<saml:Conditions NotBefore="{_iso(not_before)}" '
        f'NotOnOrAfter="{_iso(not_on_or_after)}">'
        f"<saml:AudienceRestriction><saml:Audience>{audience}</saml:Audience>"
        "</saml:AudienceRestriction></saml:Conditions>"
        f'<saml:AuthnStatement AuthnInstant="{_iso(not_before)}" '
        f'SessionNotOnOrAfter="{_iso(session_not_on_or_after)}" '
        f'SessionIndex="_session-idx-1">'
        "<saml:AuthnContext><saml:AuthnContextClassRef>"
        "urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport"
        "</saml:AuthnContextClassRef></saml:AuthnContext></saml:AuthnStatement>"
        f"{attr_statements}"
        "</saml:Assertion>"
    )


def _response_xml(*, response_id: str, issuer: str, destination: str,
                  in_response_to: str, assertion_block: str) -> str:
    return (
        '<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
        'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
        f'ID="{response_id}" Version="2.0" IssueInstant="{_iso(datetime.utcnow())}" '
        f'Destination="{destination}" InResponseTo="{in_response_to}">'
        f"<saml:Issuer>{issuer}</saml:Issuer>"
        "<samlp:Status><samlp:StatusCode "
        'Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>'
        f"{assertion_block}"
        "</samlp:Response>"
    )


def make_signed_response(
    key_pem: str,
    cert_pem: str,
    *,
    sign: bool = True,
    sign_key_pem: str = None,
    sign_cert_pem: str = None,
    issuer: str = IDP_ENTITY_ID,
    audience: str = SP_ENTITY_ID,
    recipient: str = ACS_URL,
    destination: str = ACS_URL,
    in_response_to: str = DEFAULT_IN_RESPONSE_TO,
    name_id: str = DEFAULT_NAMEID,
    name_id_format: str = OneLogin_Saml2_Constants.NAMEID_UNSPECIFIED,
    not_before_delta_seconds: int = -30,
    not_on_or_after_delta_seconds: int = 300,
    sc_not_on_or_after_delta_seconds: int = None,
    attributes: dict = None,
    include_subject: bool = True,
    xsw: bool = False,
    sign_response: bool = False,
) -> str:
    """Build a base64-encoded SAMLResponse.

    - `sign=True` signs the *Assertion* (trust anchor). `sign=False` leaves it
      unsigned. `sign_key_pem`/`sign_cert_pem` override the signer (wrong-cert).
    - `sign_response=True` signs the *Response* element instead of/in addition
      to the assertion — used to prove that requiring an assertion signature
      (not merely a response signature) is load-bearing.
    - `xsw=True` wraps a forged, *unsigned* second assertion (evil NameID) around
      the legitimately-signed one — the classic XML Signature Wrapping attack.
    """
    now = datetime.utcnow()
    not_before = now + timedelta(seconds=not_before_delta_seconds)
    not_on_or_after = now + timedelta(seconds=not_on_or_after_delta_seconds)
    sc_nooa = (
        now + timedelta(seconds=sc_not_on_or_after_delta_seconds)
        if sc_not_on_or_after_delta_seconds is not None
        else not_on_or_after
    )
    session_expiry = now + timedelta(hours=8)
    attrs = attributes if attributes is not None else {}

    real_assertion_id = "_assertion-real-0001"
    assertion = _assertion_xml(
        assertion_id=real_assertion_id,
        issuer=issuer,
        audience=audience,
        recipient=recipient,
        in_response_to=in_response_to,
        name_id=name_id,
        name_id_format=name_id_format,
        not_before=not_before,
        not_on_or_after=not_on_or_after,
        session_not_on_or_after=session_expiry,
        attributes=attrs,
        include_subject=include_subject,
        sc_not_on_or_after=sc_nooa,
    )

    if sign:
        skey = sign_key_pem or key_pem
        scert = sign_cert_pem or cert_pem
        signed = OneLogin_Saml2_Utils.add_sign(
            assertion,
            skey,
            scert,
            sign_algorithm=OneLogin_Saml2_Constants.RSA_SHA256,
            digest_algorithm=OneLogin_Saml2_Constants.SHA256,
        )
        assertion = signed.decode() if isinstance(signed, bytes) else signed

    if xsw:
        # Forge an UNSIGNED second assertion carrying an attacker NameID and
        # place it alongside the signed one. A naive parser that reads "the"
        # assertion may pick the forged subject; the delegated validator must
        # only ever trust the signed assertion (or reject outright).
        forged = _assertion_xml(
            assertion_id="_assertion-forged-evil",
            issuer=issuer,
            audience=audience,
            recipient=recipient,
            in_response_to=in_response_to,
            name_id="attacker@evil.example.com",
            name_id_format=name_id_format,
            not_before=not_before,
            not_on_or_after=not_on_or_after,
            session_not_on_or_after=session_expiry,
            attributes=attrs,
            include_subject=include_subject,
        )
        assertion_block = forged + assertion
    else:
        assertion_block = assertion

    response = _response_xml(
        response_id="_response-0001",
        issuer=issuer,
        destination=destination,
        in_response_to=in_response_to,
        assertion_block=assertion_block,
    )

    if sign_response:
        skey = sign_key_pem or key_pem
        scert = sign_cert_pem or cert_pem
        signed_resp = OneLogin_Saml2_Utils.add_sign(
            response,
            skey,
            scert,
            sign_algorithm=OneLogin_Saml2_Constants.RSA_SHA256,
            digest_algorithm=OneLogin_Saml2_Constants.SHA256,
        )
        response = signed_resp.decode() if isinstance(signed_resp, bytes) else signed_resp

    return base64.b64encode(response.encode("utf-8")).decode("ascii")
