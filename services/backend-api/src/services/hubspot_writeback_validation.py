"""
HubSpot writeback-field validation (writeback-config-api aspect).

Backend owns this validation (it cannot import the worker's write-client), so
it mirrors the same httpx-Bearer GET pattern used by _validate_hubspot_token
in src/api/routes/hubspot_integration.py, hitting the property-definition
endpoint instead of account-info.
"""
import logging
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

HUBSPOT_CONTACT_PROPERTY_URL = "https://api.hubapi.com/crm/v3/properties/contacts/{name}"


def validate_writeback_field(access_token: str, field_name: str) -> Tuple[bool, Optional[str]]:
    """
    Validate that `field_name` is a writable, number-typed HubSpot contact
    property for the org identified by `access_token`.

    Returns (True, None) when the field exists, is type "number", and is not
    read-only/calculated.

    On failure, returns (False, reason) where reason is one of:
      - "field_not_found"      the property does not exist (404)
      - "wrong_type"           the property exists but isn't a writable number
      - "missing_write_scope"  the token lacks permission (403)
      - "validation_error"     any other HTTP or network failure
    """
    try:
        with httpx.Client(timeout=10.0) as http_client:
            resp = http_client.get(
                HUBSPOT_CONTACT_PROPERTY_URL.format(name=field_name),
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        if status_code == 404:
            return False, "field_not_found"
        if status_code == 403:
            return False, "missing_write_scope"
        logger.warning(
            "HubSpot writeback field validation failed for '%s': HTTP %s",
            field_name,
            status_code,
        )
        return False, "validation_error"
    except httpx.RequestError as exc:
        logger.warning(
            "HubSpot writeback field validation could not reach HubSpot for '%s': %s",
            field_name,
            exc,
        )
        return False, "validation_error"

    field_type = data.get("type")
    if field_type != "number":
        return False, "wrong_type"

    if data.get("calculated"):
        return False, "wrong_type"

    modification_metadata = data.get("modificationMetadata") or {}
    if modification_metadata.get("readOnlyValue"):
        return False, "wrong_type"

    return True, None
