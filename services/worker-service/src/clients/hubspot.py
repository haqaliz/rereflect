"""
HubSpot CRM HTTP client for the hubspot-sync worker task.

Pulls Contacts, Companies, and Deals from HubSpot CRM v3 API.
Handles pagination (cursor-based), 429 rate limits (Retry-After sleep),
and 5xx transient errors.

R3: The access_token is stored in self._token but NEVER logged.
    Log messages use integration_id and org_id for identification only.

Usage:
    with HubSpotClient(access_token) as client:
        contacts = client.list_contacts()
        company = client.get_company(company_id)
        deals = client.get_open_deals_for_company(company_id)
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class HubSpotTransientError(Exception):
    """Raised on 429 / 5xx — Celery task should retry on this."""


class HubSpotScopeError(Exception):
    """Raised on 403 — permanent error, the token lacks the required scope."""


class HubSpotNotFoundError(Exception):
    """Raised on 404 — permanent error, the target contact/property doesn't exist."""


def _format_number(value) -> str:
    """
    Stringify a numeric value for HubSpot's number-property write API
    (HubSpot expects string values even for number properties).

    Raises ValueError on None so a missing score fails loud instead of
    silently writing an empty/garbage value.
    """
    if value is None:
        raise ValueError("_format_number: value must not be None")
    return str(value)


class HubSpotClient:
    """Thin httpx wrapper for the HubSpot CRM v3 API."""

    BASE_URL = "https://api.hubapi.com"
    PAGE_SIZE = 100
    # Cap at 100 pages × 100 contacts = 10,000 contacts per run.
    # Override in tests or via env var for portals that need more.
    PER_RUN_PAGE_CAP = 100

    def __init__(self, access_token: str, arr_property_name: str = "annualrevenue") -> None:
        # R3: token stored but NEVER logged
        self._token = access_token
        self._arr_property = arr_property_name
        self._client = httpx.Client(
            base_url=self.BASE_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15.0,
        )

    def __enter__(self) -> "HubSpotClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------------
    # Contacts
    # ------------------------------------------------------------------

    def list_contacts(self) -> list[dict]:
        """
        Return all contacts (paginated) with email, lifecyclestage,
        and associatedcompanyid properties.

        Stops at PER_RUN_PAGE_CAP pages and emits a WARNING if capped.
        Raises HubSpotTransientError on 429 or 5xx.
        """
        properties = "email,lifecyclestage,associatedcompanyid"
        results: list[dict] = []
        after: Optional[str] = None
        page_count = 0

        while True:
            if page_count >= self.PER_RUN_PAGE_CAP:
                logger.warning(
                    "hubspot_client: per-run cap reached — "
                    "stopped after %d pages (%d contacts); "
                    "some contacts may not have been synced",
                    page_count,
                    len(results),
                )
                break

            params: dict = {
                "limit": self.PAGE_SIZE,
                "properties": properties,
            }
            if after:
                params["after"] = after

            resp = self._client.get("/crm/v3/objects/contacts", params=params)

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "10"))
                logger.warning(
                    "hubspot_client: 429 rate limited; sleeping %ss", retry_after
                )
                time.sleep(retry_after)
                raise HubSpotTransientError(
                    f"HubSpot rate limited, retry after {retry_after}s"
                )

            if resp.status_code >= 500:
                raise HubSpotTransientError(
                    f"HubSpot server error {resp.status_code}"
                )

            data = resp.json()
            results.extend(data.get("results", []))
            page_count += 1

            paging = data.get("paging", {})
            after = paging.get("next", {}).get("after")
            if not after:
                break

        return results

    # ------------------------------------------------------------------
    # Companies
    # ------------------------------------------------------------------

    def get_company(self, company_id: str) -> Optional[dict]:
        """
        Fetch company by ID. Returns a flat dict with name and the ARR
        property value (using the configured arr_property_name).

        Returns None on 404. Raises HubSpotTransientError on 5xx.
        """
        params = {"properties": f"name,{self._arr_property}"}
        resp = self._client.get(
            f"/crm/v3/objects/companies/{company_id}", params=params
        )

        if resp.status_code == 404:
            return None

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "10"))
            time.sleep(retry_after)
            raise HubSpotTransientError(
                f"HubSpot rate limited fetching company, retry after {retry_after}s"
            )

        if resp.status_code >= 500:
            raise HubSpotTransientError(
                f"HubSpot server error {resp.status_code} fetching company {company_id}"
            )

        data = resp.json()
        props = data.get("properties", {})
        return {
            "name": props.get("name"),
            self._arr_property: props.get(self._arr_property),
            # convenience alias so callers can use "annualrevenue" regardless
            "annualrevenue": props.get(self._arr_property),
        }

    # ------------------------------------------------------------------
    # Deals
    # ------------------------------------------------------------------

    def _fetch_deals_for_company(self, company_id: str) -> list[dict]:
        """
        Return ALL deals associated with a company, unfiltered by stage.

        Step 1: GET /crm/v3/objects/companies/{company_id}/associations/deals
                — retrieves deal IDs scoped to this company (paginated).
        Step 2: POST /crm/v3/objects/deals/batch/read
                — fetches deal properties for those IDs in one call.
        """
        # ------------------------------------------------------------------
        # Step 1: Collect deal IDs via the company-scoped associations endpoint
        # ------------------------------------------------------------------
        deal_ids: list[str] = []
        after: Optional[str] = None

        while True:
            params: dict = {"limit": 100}
            if after:
                params["after"] = after

            resp = self._client.get(
                f"/crm/v3/objects/companies/{company_id}/associations/deals",
                params=params,
            )

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "10"))
                logger.warning(
                    "hubspot_client: 429 rate limited fetching associations; sleeping %ss",
                    retry_after,
                )
                time.sleep(retry_after)
                raise HubSpotTransientError(
                    f"HubSpot rate limited fetching associations, retry after {retry_after}s"
                )

            if resp.status_code >= 500:
                raise HubSpotTransientError(
                    f"HubSpot server error {resp.status_code} "
                    f"fetching associations for company {company_id}"
                )

            if resp.status_code == 404:
                return []

            data = resp.json()
            for result in data.get("results", []):
                deal_ids.append(result["id"])

            paging = data.get("paging", {})
            after = paging.get("next", {}).get("after")
            if not after:
                break

        if not deal_ids:
            return []

        # ------------------------------------------------------------------
        # Step 2: Batch-read deal properties for the collected IDs
        # ------------------------------------------------------------------
        batch_payload = {
            "inputs": [{"id": did} for did in deal_ids],
            "properties": ["dealname", "dealstage", "amount", "closedate", "pipeline"],
        }
        resp = self._client.post(
            "/crm/v3/objects/deals/batch/read",
            json=batch_payload,
        )

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "10"))
            logger.warning(
                "hubspot_client: 429 rate limited batch-reading deals; sleeping %ss",
                retry_after,
            )
            time.sleep(retry_after)
            raise HubSpotTransientError(
                f"HubSpot rate limited batch-reading deals, retry after {retry_after}s"
            )

        if resp.status_code >= 500:
            raise HubSpotTransientError(
                f"HubSpot server error {resp.status_code} batch-reading deals"
            )

        return resp.json().get("results", [])

    def get_open_deals_for_company(self, company_id: str) -> list[dict]:
        """
        Return open deals associated with a company (not closedwon / closedlost).

        Step 3: Filter open stages client-side (exclude closedwon / closedlost).
        """
        all_deals = self._fetch_deals_for_company(company_id)

        # ------------------------------------------------------------------
        # Step 3: Filter open deals (exclude closedwon / closedlost)
        # ------------------------------------------------------------------
        closed_stages = {"closedwon", "closedlost"}
        return [
            d for d in all_deals
            if d.get("properties", {}).get("dealstage") not in closed_stages
        ]

    def get_closed_lost_deals_for_company(self, company_id: str) -> list[dict]:
        """
        Return closedlost deals associated with a company — the sibling
        accessor that retains what get_open_deals_for_company drops.
        """
        all_deals = self._fetch_deals_for_company(company_id)
        return [
            d for d in all_deals
            if d.get("properties", {}).get("dealstage") == "closedlost"
        ]

    # ------------------------------------------------------------------
    # Writeback (contact property updates)
    # ------------------------------------------------------------------

    def update_contact_property(
        self, contact_id: str, property_name: str, value
    ) -> None:
        """
        PATCH a single contact property (e.g. a churn/health score).

        HubSpot number properties must be sent as strings, so `value` is
        passed through `_format_number` before being placed in the body.

        Raises:
            HubSpotTransientError: on 429 or 5xx (caller/task should retry).
            HubSpotScopeError: on 403 (token lacks the required scope).
            HubSpotNotFoundError: on 404 (contact not found).
        """
        body = {"properties": {property_name: _format_number(value)}}
        resp = self._client.patch(
            f"/crm/v3/objects/contacts/{contact_id}", json=body
        )

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "10"))
            logger.warning(
                "hubspot_client: 429 rate limited updating contact %s; sleeping %ss",
                contact_id,
                retry_after,
            )
            time.sleep(retry_after)
            raise HubSpotTransientError(
                f"HubSpot rate limited updating contact {contact_id}, "
                f"retry after {retry_after}s"
            )

        if resp.status_code >= 500:
            raise HubSpotTransientError(
                f"HubSpot server error {resp.status_code} updating contact {contact_id}"
            )

        if resp.status_code == 403:
            raise HubSpotScopeError(
                f"HubSpot scope error updating contact {contact_id} property {property_name}"
            )

        if resp.status_code == 404:
            raise HubSpotNotFoundError(
                f"HubSpot contact {contact_id} not found"
            )

    def get_contact_property_def(self, name: str) -> Optional[dict]:
        """
        Fetch the definition of a contact property, to validate its type
        and writability before a writeback attempt.

        Returns the parsed def dict (including `type`, `fieldType`,
        `calculated`, `readOnlyValue`) on 200; returns None on 404.

        Raises:
            HubSpotTransientError: on 429 or 5xx.
            HubSpotScopeError: on 403.
        """
        resp = self._client.get(f"/crm/v3/properties/contacts/{name}")

        if resp.status_code == 404:
            return None

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "10"))
            logger.warning(
                "hubspot_client: 429 rate limited fetching property def %s; sleeping %ss",
                name,
                retry_after,
            )
            time.sleep(retry_after)
            raise HubSpotTransientError(
                f"HubSpot rate limited fetching property def {name}, "
                f"retry after {retry_after}s"
            )

        if resp.status_code >= 500:
            raise HubSpotTransientError(
                f"HubSpot server error {resp.status_code} fetching property def {name}"
            )

        if resp.status_code == 403:
            raise HubSpotScopeError(
                f"HubSpot scope error fetching property def {name}"
            )

        return resp.json()
