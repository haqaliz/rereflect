"""
Cross-provider single-SSO guard (saml-sso M6).

At most ONE SSO protocol may be enabled per deployment. Enabling SAML must
fail if any OIDC config is enabled, and vice-versa. This is the CROSS-provider
half only; each provider's SAME-provider single-enabled D5 check stays in its
own route (oidc_config._assert_no_other_enabled / saml_config._assert_no_other_enabled)
so the shipped OIDC route's existing behavior + error string stay byte-stable.
"""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.models.oidc_config import OidcConfig
from src.models.saml_config import SamlConfig

_LABELS = {"oidc": "OIDC", "saml": "SAML"}


def assert_no_other_provider_enabled(db: Session, *, enabling: str) -> None:
    """Raise 422 if the OTHER SSO provider has any enabled config anywhere in
    the deployment. `enabling` is 'oidc' or 'saml'."""
    if enabling not in {"oidc", "saml"}:
        # Guard against a silent fallthrough: without this, any typo/unknown
        # value would fall into the `else` branch below and be treated as
        # "saml" (checking OidcConfig), which is exactly the wrong guard for
        # an unrecognized caller. Fail loudly instead.
        raise ValueError(f"assert_no_other_provider_enabled: invalid enabling={enabling!r}; expected 'oidc' or 'saml'")
    other_model = SamlConfig if enabling == "oidc" else OidcConfig
    other_label = _LABELS["saml" if enabling == "oidc" else "oidc"]
    row = db.query(other_model).filter(other_model.enabled.is_(True)).first()
    if row is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(f"A {other_label} SSO config is already enabled; "
                    f"only one SSO protocol may be active per deployment."),
        )
