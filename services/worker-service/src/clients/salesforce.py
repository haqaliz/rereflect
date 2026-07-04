"""
Salesforce REST/SOQL HTTP client for the salesforce-sync worker task.

Mints a short-lived access_token from a stored OAuth refresh_token before
each run (web-server OAuth 2.0 — mirrors src/api/routes/salesforce_integration.py
on the backend), then pulls Contacts / Accounts / Opportunities over the
SOQL query endpoint. Handles cursor-based pagination via `nextRecordsUrl`,
429 rate limits (Retry-After sleep), 5xx transient errors, and logs the
`Sforce-Limit-Info` daily API usage header (backing off before it's fully
exhausted).

R3: the access_token (and refresh_token) are stored on the instance but
    NEVER logged. Log messages use org/integration identifiers only.

Usage:
    with SalesforceClient(
        refresh_token=refresh_token,
        instance_url=integ.instance_url,
        client_id=client_id,
        client_secret=client_secret,
    ) as client:
        contacts = client.list_contacts()
        account = client.get_account(account_id)
        opps = client.get_open_opportunities(account_id)
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Salesforce record IDs are always 15 (case-sensitive) or 18
# (case-insensitive, with a checksum suffix) alphanumeric characters.
# Validated before interpolation into SOQL WHERE clauses — defense-in-depth
# against SOQL injection even though these ids originate from Salesforce's
# own API responses (Contact.AccountId), not end-user input.
_SFID_RE = re.compile(r"^[a-zA-Z0-9]{15,18}$")


class SalesforceTransientError(Exception):
    """Raised on 429 / 5xx — Celery task should retry on this."""


class SalesforceAuthError(Exception):
    """
    Raised when minting an access token from the refresh token fails with a
    non-transient error (e.g. `invalid_grant` — the refresh token was
    revoked/expired). Celery task must NOT retry on this; the integration
    should be marked disconnected instead.
    """


class SalesforceQueryError(Exception):
    """Raised on a non-transient SOQL query failure (e.g. malformed query)."""


class SalesforceScopeError(Exception):
    """
    Raised on 403 for a write/describe call — permanent error, the
    connected app/user lacks the required object/field access (mirrors
    HubSpotScopeError).
    """


class SalesforceNotFoundError(Exception):
    """Raised on 404 for a write call — permanent error, the target record doesn't exist."""


class SalesforceClient:
    """Thin httpx wrapper for the Salesforce REST/SOQL API."""

    # Cap pagination at 100 pages per run (mirrors HubSpotClient).
    PER_RUN_PAGE_CAP = 100

    # Stop pulling more pages once the daily API call budget has this many
    # (or fewer) calls remaining, per Sforce-Limit-Info.
    DAILY_LIMIT_STOP_THRESHOLD = 50

    def __init__(
        self,
        refresh_token: str,
        instance_url: str,
        client_id: str,
        client_secret: str,
        login_base: str = "https://login.salesforce.com",
        api_version: str = "v60.0",
    ) -> None:
        # R3: tokens stored but NEVER logged.
        self._refresh_token = refresh_token
        self._client_id = client_id
        self._client_secret = client_secret
        self._login_base = login_base.rstrip("/")
        self._api_version = api_version
        self._instance_url = (instance_url or "").rstrip("/")
        self._access_token: Optional[str] = None
        self._client = httpx.Client(timeout=15.0)

    def __enter__(self) -> "SalesforceClient":
        self._refresh()
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        """
        Exchange the stored refresh_token for a short-lived access_token.

        Raises SalesforceAuthError on `invalid_grant` (non-retrying — caller
        should disconnect the integration) or any other non-2xx response.
        Raises SalesforceTransientError on 429 / 5xx (retryable).
        """
        resp = self._client.post(
            f"{self._login_base}/services/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": self._refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if resp.status_code == 200:
            data = resp.json()
            self._access_token = data.get("access_token")
            # Salesforce may return a (re-affirmed) instance_url on refresh.
            if data.get("instance_url"):
                self._instance_url = data["instance_url"].rstrip("/")
            return

        error_code = None
        try:
            error_code = resp.json().get("error")
        except Exception:
            pass

        if error_code == "invalid_grant":
            raise SalesforceAuthError("invalid_grant")

        if resp.status_code == 429 or resp.status_code >= 500:
            raise SalesforceTransientError(
                f"Salesforce token refresh error {resp.status_code}"
            )

        raise SalesforceAuthError(
            f"Salesforce token refresh failed: {resp.status_code} {error_code}"
        )

    # ------------------------------------------------------------------
    # SOQL query (paginated, limit-aware)
    # ------------------------------------------------------------------

    def query(self, soql: str) -> list[dict]:
        """
        Run a SOQL query and return all records, following `nextRecordsUrl`.

        Stops at PER_RUN_PAGE_CAP pages (WARNING logged) or when the
        Sforce-Limit-Info header shows the daily budget is nearly exhausted.
        Raises SalesforceTransientError on 429 / 5xx.
        """
        results: list[dict] = []
        url = f"{self._instance_url}/services/data/{self._api_version}/query"
        params: Optional[dict] = {"q": soql}
        page_count = 0

        while True:
            if page_count >= self.PER_RUN_PAGE_CAP:
                logger.warning(
                    "salesforce_client: per-run page cap reached — "
                    "stopped after %d pages (%d records); "
                    "some records may not have been synced",
                    page_count,
                    len(results),
                )
                break

            headers = {"Authorization": f"Bearer {self._access_token}"}
            resp = self._client.get(url, params=params, headers=headers)

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "10"))
                logger.warning(
                    "salesforce_client: 429 rate limited; sleeping %ss", retry_after
                )
                time.sleep(retry_after)
                raise SalesforceTransientError(
                    f"Salesforce rate limited, retry after {retry_after}s"
                )

            if resp.status_code >= 500:
                raise SalesforceTransientError(
                    f"Salesforce server error {resp.status_code}"
                )

            if resp.status_code != 200:
                raise SalesforceQueryError(
                    f"Salesforce query failed with status {resp.status_code}: {soql}"
                )

            near_exhaustion = self._log_limit_info(resp.headers)

            data = resp.json()
            results.extend(data.get("records", []))
            page_count += 1

            if near_exhaustion:
                logger.warning(
                    "salesforce_client: daily API limit nearly exhausted — "
                    "stopping pagination after %d pages (%d records)",
                    page_count,
                    len(results),
                )
                break

            next_url = data.get("nextRecordsUrl")
            if not next_url:
                break
            url = f"{self._instance_url}{next_url}"
            params = None

        return results

    @staticmethod
    def _validate_sf_id(sf_id: str) -> str:
        """
        Validate that `sf_id` looks like a genuine Salesforce record ID
        (15 or 18 alphanumeric characters) before it is interpolated into a
        SOQL WHERE clause.

        Raises SalesforceQueryError (no HTTP request issued) on anything
        that doesn't match — defense-in-depth against SOQL injection.
        """
        if not sf_id or not _SFID_RE.match(sf_id):
            raise SalesforceQueryError(
                f"Refusing to interpolate malformed Salesforce id into SOQL: {sf_id!r}"
            )
        return sf_id

    def _log_limit_info(self, headers) -> bool:
        """
        Parse the `Sforce-Limit-Info` header (e.g. "api-usage=18000/20000"),
        log the remaining call budget, and return True if it's near zero
        (caller should stop pulling more pages).
        """
        info = headers.get("Sforce-Limit-Info")
        if not info:
            return False

        try:
            _, usage = info.split("=", 1)
            used_str, total_str = usage.split("/", 1)
            used, total = int(used_str), int(total_str)
        except (ValueError, AttributeError):
            return False

        remaining = total - used
        logger.info(
            "salesforce_client: daily API limit remaining=%d/%d", remaining, total
        )
        return remaining <= self.DAILY_LIMIT_STOP_THRESHOLD

    # ------------------------------------------------------------------
    # Typed helpers
    # ------------------------------------------------------------------

    def list_contacts(self) -> list[dict]:
        """Return all Contacts that have an email address."""
        soql = "SELECT Id, Email, AccountId, Name FROM Contact WHERE Email != null"
        return self.query(soql)

    def get_account(self, account_id: str) -> Optional[dict]:
        """Fetch a single Account by Id. Returns None if not found."""
        account_id = self._validate_sf_id(account_id)
        soql = (
            "SELECT Id, Name, AnnualRevenue, Type FROM Account "
            f"WHERE Id = '{account_id}' LIMIT 1"
        )
        records = self.query(soql)
        return records[0] if records else None

    def get_open_opportunities(self, account_id: str) -> list[dict]:
        """Return all open (not-closed) Opportunities for the given Account."""
        account_id = self._validate_sf_id(account_id)
        soql = (
            "SELECT Id, Name, StageName, Amount, CloseDate, IsClosed "
            f"FROM Opportunity WHERE AccountId = '{account_id}' AND IsClosed = false"
        )
        return self.query(soql)

    # ------------------------------------------------------------------
    # Writeback (Contact field updates)
    # ------------------------------------------------------------------

    def update_contact_field(self, contact_id: str, field_name: str, value) -> None:
        """
        PATCH a single Contact field (e.g. a churn/health score).

        Unlike HubSpot (which requires stringified numbers), Salesforce's
        REST API expects the raw JSON number — `value` is placed directly
        in the body with NO stringification.

        Raises:
            SalesforceQueryError: if `contact_id` fails `_validate_sf_id`
                (no HTTP call is made — SOQL/URL-injection defense-in-depth).
            SalesforceTransientError: on 429 or 5xx (caller/task should retry).
            SalesforceScopeError: on 403 (connected app/user lacks object/field access).
            SalesforceNotFoundError: on 404 (contact not found).
            SalesforceAuthError: on 401 that persists after one refresh+retry.
        """
        contact_id = self._validate_sf_id(contact_id)
        url = (
            f"{self._instance_url}/services/data/{self._api_version}"
            f"/sobjects/Contact/{contact_id}"
        )
        body = {field_name: value}

        def _patch():
            headers = {"Authorization": f"Bearer {self._access_token}"}
            return self._client.patch(url, json=body, headers=headers)

        resp = _patch()

        if resp.status_code == 401:
            logger.info(
                "salesforce_client: 401 updating contact %s — "
                "refreshing token and retrying once",
                contact_id,
            )
            self._refresh()
            resp = _patch()
            if resp.status_code == 401:
                raise SalesforceAuthError(
                    f"Salesforce auth error updating contact {contact_id} "
                    "(persisted after refresh retry)"
                )

        if resp.status_code == 429 or resp.status_code >= 500:
            raise SalesforceTransientError(
                f"Salesforce transient error {resp.status_code} updating contact {contact_id}"
            )

        if resp.status_code == 403:
            raise SalesforceScopeError(
                f"Salesforce scope error updating contact {contact_id} field {field_name}"
            )

        if resp.status_code == 404:
            raise SalesforceNotFoundError(f"Salesforce contact {contact_id} not found")

        if 200 <= resp.status_code < 300:
            return None

        raise SalesforceQueryError(
            f"Salesforce update failed with status {resp.status_code} for contact {contact_id}"
        )

    def describe_object(self, sobject: str = "Contact") -> dict:
        """
        GET the sObject describe metadata (field list, types, `updateable`
        flags) for `sobject`, used to validate a writeback field before
        enabling scoring writeback.

        Raises:
            SalesforceTransientError: on 429 or 5xx.
            SalesforceScopeError: on 403 (no object access).
            SalesforceAuthError: on 401 that persists after one refresh+retry.
            SalesforceQueryError: on any other non-2xx response.
        """
        url = f"{self._instance_url}/services/data/{self._api_version}/sobjects/{sobject}/describe"

        def _get():
            headers = {"Authorization": f"Bearer {self._access_token}"}
            return self._client.get(url, headers=headers)

        resp = _get()

        if resp.status_code == 401:
            self._refresh()
            resp = _get()
            if resp.status_code == 401:
                raise SalesforceAuthError(
                    f"Salesforce auth error describing {sobject} "
                    "(persisted after refresh retry)"
                )

        if resp.status_code == 429 or resp.status_code >= 500:
            raise SalesforceTransientError(
                f"Salesforce transient error {resp.status_code} describing {sobject}"
            )

        if resp.status_code == 403:
            raise SalesforceScopeError(f"Salesforce scope error describing {sobject}")

        if resp.status_code != 200:
            raise SalesforceQueryError(
                f"Salesforce describe failed with status {resp.status_code} for {sobject}"
            )

        return resp.json()
