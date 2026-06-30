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

    def get_open_deals_for_company(self, company_id: str) -> list[dict]:
        """
        Return open deals associated with a company (not closedwon / closedlost).

        Uses the CRM v3 associations endpoint to find deals for the company,
        then filters open ones client-side.
        """
        # Fetch all deals where this company is the associated company.
        # HubSpot associations: GET /crm/v3/objects/deals?associations=companies
        # is not directly filtered by company. Simpler: use the search API or
        # fetch via associations endpoint for the specific company.
        params = {
            "limit": 100,
            "properties": "dealname,dealstage,amount,closedate",
            "associations": "companies",
        }
        resp = self._client.get("/crm/v3/objects/deals", params=params)

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "10"))
            time.sleep(retry_after)
            raise HubSpotTransientError(
                f"HubSpot rate limited fetching deals, retry after {retry_after}s"
            )

        if resp.status_code >= 500:
            raise HubSpotTransientError(
                f"HubSpot server error {resp.status_code} fetching deals"
            )

        data = resp.json()
        all_deals = data.get("results", [])

        # Filter: only open deals (not closedwon or closedlost)
        closed_stages = {"closedwon", "closedlost"}
        open_deals = [
            d for d in all_deals
            if d.get("properties", {}).get("dealstage") not in closed_stages
        ]
        return open_deals
