"""
Salesforce writeback-field validation (writeback-config-api aspect).

Backend owns this validation (it cannot import the worker's write-client), so
it mints a short-lived access token server-side (reusing
`_refresh_access_token` from `src/api/routes/salesforce_integration.py`) and
calls the Contact sObject describe REST endpoint, mirroring the
(bool, reason) contract of `hubspot_writeback_validation.py`.
"""
import logging
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

SALESFORCE_API_VERSION = "v60.0"

# Salesforce field types that are safe to write a numeric health/churn score
# into. `updateable` must also be true (excludes formula/rollup fields).
NUMERIC_FIELD_TYPES = {"double", "int", "currency", "percent"}


def validate_writeback_field(
    refresh_token: str, instance_url: str, field_name: str
) -> Tuple[bool, Optional[str]]:
    """
    Validate that `field_name` is a writable, numeric-typed Salesforce
    Contact field for the org identified by `refresh_token`/`instance_url`.

    Returns (True, None) when the field exists, `updateable` is true, and
    its `type` is one of {double, int, currency, percent}.

    On failure, returns (False, reason) where reason is one of:
      - "field_not_found"      the field is absent from the describe response
      - "wrong_type"           the field exists but isn't a writable number
      - "missing_write_scope"  the token/user lacks permission (403)
      - "validation_error"     any other HTTP/network/unexpected failure

    Never raises.
    """
    try:
        # Imported lazily to avoid a hard import-time dependency between the
        # validation service and the integration route module.
        from src.api.routes.salesforce_integration import _refresh_access_token

        try:
            token_data = _refresh_access_token(refresh_token)
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code == 403:
                return False, "missing_write_scope"
            logger.warning(
                "Salesforce writeback field validation: token refresh failed with HTTP %s",
                status_code,
            )
            return False, "validation_error"
        except httpx.RequestError as exc:
            logger.warning(
                "Salesforce writeback field validation: token refresh network error: %s",
                exc,
            )
            return False, "validation_error"

        access_token = token_data.get("access_token")
        resolved_instance_url = (
            token_data.get("instance_url") or instance_url or ""
        ).rstrip("/")
        if not access_token or not resolved_instance_url:
            logger.warning(
                "Salesforce writeback field validation: token refresh response "
                "missing access_token/instance_url"
            )
            return False, "validation_error"

        describe_url = (
            f"{resolved_instance_url}/services/data/{SALESFORCE_API_VERSION}"
            "/sobjects/Contact/describe"
        )

        try:
            with httpx.Client(timeout=10.0) as http_client:
                resp = http_client.get(
                    describe_url,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code == 403:
                return False, "missing_write_scope"
            logger.warning(
                "Salesforce writeback field validation failed for '%s': HTTP %s",
                field_name,
                status_code,
            )
            return False, "validation_error"
        except httpx.RequestError as exc:
            logger.warning(
                "Salesforce writeback field validation could not reach Salesforce "
                "for '%s': %s",
                field_name,
                exc,
            )
            return False, "validation_error"

        fields = data.get("fields") or []
        field_def = next((f for f in fields if f.get("name") == field_name), None)
        if field_def is None:
            return False, "field_not_found"

        if not field_def.get("updateable"):
            return False, "wrong_type"

        if field_def.get("type") not in NUMERIC_FIELD_TYPES:
            return False, "wrong_type"

        return True, None
    except Exception as exc:  # pragma: no cover - defense-in-depth, never raise
        logger.warning(
            "Salesforce writeback field validation: unexpected error for '%s': %s",
            field_name,
            exc,
        )
        return False, "validation_error"
