"""
Tests for the `write` API-key scope (Aspect `write-scope`, Phase 1).

TDD: RED -> GREEN -> REFACTOR.

Coverage:
  - Creating a key with scopes=["write"] persists a scope string containing "write"
  - Creating a key with scopes=["read", "write"] persists sorted "read,write"
  - Unknown scopes still 422 (regression)
  - Empty scopes still 422 (regression)
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.api_key import ApiKey
from src.models.organization import Organization


class TestApiKeyWriteScope:
    def test_create_with_write_scope(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
    ):
        """Creating a key with scopes=["write"] returns 201 and persists "write"."""
        resp = client.post(
            "/api/v1/api-keys",
            json={"name": "write key", "scopes": ["write"]},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        row = (
            db.query(ApiKey)
            .filter(ApiKey.organization_id == test_organization.id)
            .order_by(ApiKey.id.desc())
            .first()
        )
        assert row is not None
        assert "write" in row.scopes

    def test_create_with_read_and_write_scopes_sorted(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
    ):
        """Creating a key with scopes=["read", "write"] persists sorted "read,write"."""
        resp = client.post(
            "/api/v1/api-keys",
            json={"name": "read+write key", "scopes": ["read", "write"]},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        row = (
            db.query(ApiKey)
            .filter(ApiKey.organization_id == test_organization.id)
            .order_by(ApiKey.id.desc())
            .first()
        )
        assert row is not None
        assert row.scopes == "read,write"

    def test_create_with_unknown_scope_still_422(
        self,
        client: TestClient,
        auth_headers: dict,
    ):
        """Unknown scopes must still be rejected (regression)."""
        resp = client.post(
            "/api/v1/api-keys",
            json={"name": "bad scope key", "scopes": ["delete"]},
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text

    def test_create_with_empty_scopes_still_422(
        self,
        client: TestClient,
        auth_headers: dict,
    ):
        """Empty scopes list must still be rejected (regression)."""
        resp = client.post(
            "/api/v1/api-keys",
            json={"name": "no scope key", "scopes": []},
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text
