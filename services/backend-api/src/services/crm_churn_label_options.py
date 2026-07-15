"""
CRM churn-label options seam (org-config-api-and-ui aspect, Phase 1).

`fetch_renewal_options(provider, integration) -> (options, reason)` is the
single backend-side CRM metadata call shared by both
`PATCH /api/v1/integrations/{provider}/churn-labels` (id validation) and
`GET /api/v1/integrations/{provider}/churn-labels/options` (the picker).

The backend cannot import the worker's CRM clients
(`services/worker-service/src/clients/*`), so this re-implements the two
metadata calls backend-side, mirroring the exact shape already proven by
`services/salesforce_writeback_validation.py` (lazy import of
`_refresh_access_token`, httpx.Client + Bearer, never raises) and
`services/hubspot_writeback_validation.py` (httpx Bearer GET + HTTPStatusError
/ RequestError -> reason ladder).

Returns (options, None) on success — `options` may be an empty list; an
empty portal/picklist is not an error (R-D, spec §8/§"Risks"). On failure
returns ([], reason) where reason is one of:
  - "missing_read_scope"    401/403 from the CRM
  - "options_fetch_failed"  429/5xx/network/unexpected error

Never raises.
"""
import logging
from typing import Dict, List, Optional, Tuple

import httpx

from src.utils.encryption import decrypt_api_key

logger = logging.getLogger(__name__)

HUBSPOT_PIPELINES_URL = "https://api.hubapi.com/crm/v3/pipelines/deals"
SALESFORCE_API_VERSION = "v60.0"

Option = Dict[str, str]


def fetch_renewal_options(
    provider: str, integration
) -> Tuple[List[Option], Optional[str]]:
    """
    Fetch the live CRM metadata used to populate the renewal-set picker
    (HubSpot deal pipelines / Salesforce Opportunity.Type picklist).

    `integration` is the org's active HubSpotIntegration / SalesforceIntegration
    row (decrypted token(s) are read from it). Never raises.
    """
    try:
        if provider == "hubspot":
            return _fetch_hubspot_pipelines(integration)
        if provider == "salesforce":
            return _fetch_salesforce_opportunity_types(integration)
        logger.warning("fetch_renewal_options: unknown provider '%s'", provider)
        return [], "options_fetch_failed"
    except Exception as exc:  # noqa: BLE001 - defense-in-depth, never raise
        logger.warning(
            "fetch_renewal_options: unexpected error for provider '%s': %s",
            provider,
            exc,
        )
        return [], "options_fetch_failed"


def _fetch_hubspot_pipelines(integration) -> Tuple[List[Option], Optional[str]]:
    access_token = decrypt_api_key(integration.access_token)
    try:
        with httpx.Client(timeout=10.0) as http_client:
            resp = http_client.get(
                HUBSPOT_PIPELINES_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code == 404:
                # Empty portal — not an error (mirrors clients/hubspot.py:410).
                return [], None
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        if status_code == 403:
            return [], "missing_read_scope"
        logger.warning(
            "fetch_renewal_options(hubspot): HTTP %s fetching deal pipelines",
            status_code,
        )
        return [], "options_fetch_failed"
    except httpx.RequestError as exc:
        logger.warning(
            "fetch_renewal_options(hubspot): could not reach HubSpot: %s", exc
        )
        return [], "options_fetch_failed"

    results = data.get("results") or []
    options = [
        {"id": str(pipeline.get("id")), "label": pipeline.get("label") or str(pipeline.get("id"))}
        for pipeline in results
    ]
    return options, None


def _fetch_salesforce_opportunity_types(integration) -> Tuple[List[Option], Optional[str]]:
    # Imported lazily to avoid a hard import-time dependency between this
    # service module and the integration route module (exact
    # salesforce_writeback_validation.py:45 precedent).
    from src.api.routes.salesforce_integration import _refresh_access_token

    refresh_token = decrypt_api_key(integration.refresh_token)

    try:
        token_data = _refresh_access_token(refresh_token)
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        if status_code == 403:
            return [], "missing_read_scope"
        logger.warning(
            "fetch_renewal_options(salesforce): token refresh failed with HTTP %s",
            status_code,
        )
        return [], "options_fetch_failed"
    except httpx.RequestError as exc:
        logger.warning(
            "fetch_renewal_options(salesforce): token refresh network error: %s", exc
        )
        return [], "options_fetch_failed"

    access_token = token_data.get("access_token")
    resolved_instance_url = (
        token_data.get("instance_url") or integration.instance_url or ""
    ).rstrip("/")
    if not access_token or not resolved_instance_url:
        logger.warning(
            "fetch_renewal_options(salesforce): token refresh response missing "
            "access_token/instance_url"
        )
        return [], "options_fetch_failed"

    describe_url = (
        f"{resolved_instance_url}/services/data/{SALESFORCE_API_VERSION}"
        "/sobjects/Opportunity/describe"
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
            return [], "missing_read_scope"
        logger.warning(
            "fetch_renewal_options(salesforce): describe failed with HTTP %s",
            status_code,
        )
        return [], "options_fetch_failed"
    except httpx.RequestError as exc:
        logger.warning(
            "fetch_renewal_options(salesforce): could not reach Salesforce describe: %s",
            exc,
        )
        return [], "options_fetch_failed"

    fields = data.get("fields") or []
    field = next((f for f in fields if f.get("name") == "Type"), None)
    if field is None:
        # Type is customizable and may be absent — not an error (R-D).
        return [], None

    picklist_values = field.get("picklistValues") or []
    options = [
        {"id": value.get("value"), "label": value.get("label") or value.get("value")}
        for value in picklist_values
        if value.get("active", True)
    ]
    return options, None
