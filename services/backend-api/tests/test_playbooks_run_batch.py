"""
Characterization + extension tests — playbook-cohort-run aspect (segment-actions
feature), M4.1 run-batch extension.

Phase 1 pins the EXISTING `POST /playbooks/{id}/run-batch` behavior (probability
range selection, daily-limit, one execution per matching customer, celery
dispatch) before the endpoint is extended to accept a cohort (`emails`/`segment`).

Phase 2 adds cohort-based selection (`emails`, `segment`) with AND semantics
against probability filters.

Phase 3 adds the queue-safety cap (`RUN_BATCH_MAX_CUSTOMERS = 500`) and the
`count_only` dry-run / `matched` affected-count in the response.

See docs/planning/segment-actions/playbook-cohort-run/{plan_20260709.md,spec.md}.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.auth import create_access_token, hash_password
from src.models.churn_playbook import ChurnPlaybook, ChurnPlaybookExecution
from src.models.customer_health import CustomerHealth
from src.models.organization import Organization
from src.models.user import User


# ---------------------------------------------------------------------------
# Helpers (mirrors tests/test_playbooks_api.py style)
# ---------------------------------------------------------------------------

def _make_org(db: Session, plan: str = "business") -> Organization:
    org = Organization(name=f"RunBatchOrg-{plan}-{id(plan)}", plan=plan)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_user(db: Session, org: Organization, role: str = "admin") -> User:
    user = User(
        email=f"user-{org.id}-{role}@runbatch.test",
        password_hash=hash_password("pass1234"),
        organization_id=org.id,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _headers(user: User) -> dict:
    token = create_access_token(
        {"user_id": user.id, "organization_id": user.organization_id, "role": user.role}
    )
    return {"Authorization": f"Bearer {token}"}


def _make_playbook(
    db: Session,
    org: Optional[Organization] = None,
    name: str = "Run Batch Playbook",
    prob_min: float = 0.50,
    prob_max: float = 0.80,
    is_template: bool = False,
    is_active: bool = True,
    action_sequence: Optional[list] = None,
) -> ChurnPlaybook:
    if action_sequence is None:
        action_sequence = [{"type": "send_notification", "config": {"message": "test"}}]
    pb = ChurnPlaybook(
        organization_id=org.id if org else None,
        name=name,
        probability_min=prob_min,
        probability_max=prob_max,
        action_sequence=action_sequence,
        is_template=is_template,
        is_active=is_active,
    )
    db.add(pb)
    db.commit()
    db.refresh(pb)
    return pb


def _make_customer_health(
    db: Session,
    org: Organization,
    email: str,
    churn_probability: float = 0.60,
    time_to_churn_bucket: str = "2-4w",
    segment: Optional[str] = None,
    is_archived: bool = False,
) -> CustomerHealth:
    ch = CustomerHealth(
        organization_id=org.id,
        customer_email=email,
        health_score=40,
        churn_probability=churn_probability,
        time_to_churn_bucket=time_to_churn_bucket,
        segment=segment,
        is_archived=is_archived,
    )
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return ch


def _seed_executions_today(db: Session, playbook: ChurnPlaybook, org: Organization, n: int) -> None:
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(n):
        ex = ChurnPlaybookExecution(
            playbook_id=playbook.id,
            organization_id=org.id,
            customer_email=f"seed{i}@x.com",
            triggered_by="manual",
            status="queued",
            action_log=[],
            created_at=today + timedelta(minutes=i),
        )
        db.add(ex)
    db.commit()


def _mock_celery():
    return patch("src.background.celery_client.get_celery_app")


# ---------------------------------------------------------------------------
# Phase 1 — characterization (locks current behavior before extending)
# ---------------------------------------------------------------------------

class TestRunBatchCharacterization:
    def test_no_filters_uses_playbooks_own_probability_range(self, client: TestClient, db: Session):
        org = _make_org(db)
        user = _make_user(db, org)
        pb = _make_playbook(db, org=org, prob_min=0.50, prob_max=0.80)
        _make_customer_health(db, org, "in@x.com", churn_probability=0.60)
        _make_customer_health(db, org, "out@x.com", churn_probability=0.10)

        with _mock_celery() as mock_get_app:
            mock_get_app.return_value.send_task.return_value.id = "t"
            resp = client.post(
                f"/api/v1/playbooks/{pb.id}/run-batch",
                json={"filters": {}},
                headers=_headers(user),
            )

        assert resp.status_code == 200
        assert resp.json()["queued"] == 1

    def test_explicit_probability_range_overrides_playbook_range(self, client: TestClient, db: Session):
        org = _make_org(db)
        user = _make_user(db, org)
        pb = _make_playbook(db, org=org, prob_min=0.50, prob_max=0.80)
        _make_customer_health(db, org, "low@x.com", churn_probability=0.20)

        with _mock_celery() as mock_get_app:
            mock_get_app.return_value.send_task.return_value.id = "t"
            resp = client.post(
                f"/api/v1/playbooks/{pb.id}/run-batch",
                json={"filters": {"probability_min": 0.10, "probability_max": 0.30}},
                headers=_headers(user),
            )

        assert resp.status_code == 200
        assert resp.json()["queued"] == 1

    def test_time_to_churn_bucket_filter(self, client: TestClient, db: Session):
        org = _make_org(db)
        user = _make_user(db, org)
        pb = _make_playbook(db, org=org, prob_min=0.0, prob_max=1.0)
        _make_customer_health(db, org, "soon@x.com", churn_probability=0.5, time_to_churn_bucket="0-2w")
        _make_customer_health(db, org, "later@x.com", churn_probability=0.5, time_to_churn_bucket="4w+")

        with _mock_celery() as mock_get_app:
            mock_get_app.return_value.send_task.return_value.id = "t"
            resp = client.post(
                f"/api/v1/playbooks/{pb.id}/run-batch",
                json={"filters": {"time_to_churn_bucket": "0-2w"}},
                headers=_headers(user),
            )

        assert resp.status_code == 200
        assert resp.json()["queued"] == 1

    def test_org_scoped_selection(self, client: TestClient, db: Session):
        org = _make_org(db)
        other_org = _make_org(db)
        user = _make_user(db, org)
        pb = _make_playbook(db, org=org, prob_min=0.0, prob_max=1.0)
        _make_customer_health(db, org, "mine@x.com", churn_probability=0.5)
        _make_customer_health(db, other_org, "theirs@x.com", churn_probability=0.5)

        with _mock_celery() as mock_get_app:
            mock_get_app.return_value.send_task.return_value.id = "t"
            resp = client.post(
                f"/api/v1/playbooks/{pb.id}/run-batch",
                json={"filters": {}},
                headers=_headers(user),
            )

        assert resp.status_code == 200
        assert resp.json()["queued"] == 1

    def test_creates_one_execution_per_matching_customer_status_queued(self, client: TestClient, db: Session):
        org = _make_org(db)
        user = _make_user(db, org)
        pb = _make_playbook(db, org=org, prob_min=0.0, prob_max=1.0)
        _make_customer_health(db, org, "a@x.com", churn_probability=0.5)
        _make_customer_health(db, org, "b@x.com", churn_probability=0.6)

        with _mock_celery() as mock_get_app:
            mock_get_app.return_value.send_task.return_value.id = "t"
            resp = client.post(
                f"/api/v1/playbooks/{pb.id}/run-batch",
                json={"filters": {}},
                headers=_headers(user),
            )

        assert resp.status_code == 200
        ids = resp.json()["execution_ids"]
        assert len(ids) == 2
        rows = db.query(ChurnPlaybookExecution).filter(ChurnPlaybookExecution.id.in_(ids)).all()
        assert len(rows) == 2
        assert {r.status for r in rows} == {"queued"}
        assert {r.customer_email for r in rows} == {"a@x.com", "b@x.com"}

    def test_dispatches_celery_once_per_execution_with_execution_id(self, client: TestClient, db: Session):
        org = _make_org(db)
        user = _make_user(db, org)
        pb = _make_playbook(db, org=org, prob_min=0.0, prob_max=1.0)
        _make_customer_health(db, org, "a@x.com", churn_probability=0.5)
        _make_customer_health(db, org, "b@x.com", churn_probability=0.6)

        with _mock_celery() as mock_get_app:
            mock_send = mock_get_app.return_value.send_task
            mock_send.return_value.id = "t"
            resp = client.post(
                f"/api/v1/playbooks/{pb.id}/run-batch",
                json={"filters": {}},
                headers=_headers(user),
            )

        ids = resp.json()["execution_ids"]
        assert mock_send.call_count == 2
        dispatched_ids = {call.kwargs["args"][0] for call in mock_send.call_args_list}
        assert dispatched_ids == set(ids)

    def test_enforces_business_daily_limit_429(self, client: TestClient, db: Session):
        org = _make_org(db, plan="business")
        user = _make_user(db, org)
        pb = _make_playbook(db, org=org)
        _seed_executions_today(db, pb, org, 50)
        _make_customer_health(db, org, "new@x.com", churn_probability=0.60)

        with _mock_celery() as mock_get_app:
            mock_get_app.return_value.send_task.return_value.id = "z"
            resp = client.post(
                f"/api/v1/playbooks/{pb.id}/run-batch",
                json={"filters": {}},
                headers=_headers(user),
            )

        assert resp.status_code == 429
        assert "daily" in resp.json()["detail"].lower() or "limit" in resp.json()["detail"].lower()
        # Nothing should have been queued when the limit is hit.
        assert db.query(ChurnPlaybookExecution).filter(
            ChurnPlaybookExecution.customer_email == "new@x.com"
        ).count() == 0

    def test_no_daily_limit_for_enterprise(self, client: TestClient, db: Session):
        org = _make_org(db, plan="enterprise")
        user = _make_user(db, org)
        pb = _make_playbook(db, org=org, prob_min=0.50, prob_max=0.90)
        _seed_executions_today(db, pb, org, 50)
        _make_customer_health(db, org, "ent-new@x.com", churn_probability=0.70)

        with _mock_celery() as mock_get_app:
            mock_get_app.return_value.send_task.return_value.id = "z"
            resp = client.post(
                f"/api/v1/playbooks/{pb.id}/run-batch",
                json={"filters": {}},
                headers=_headers(user),
            )

        assert resp.status_code == 200
        assert resp.json()["queued"] >= 1

    def test_404_for_unknown_playbook(self, client: TestClient, db: Session):
        org = _make_org(db)
        user = _make_user(db, org)
        resp = client.post(
            "/api/v1/playbooks/99999/run-batch",
            json={"filters": {}},
            headers=_headers(user),
        )
        assert resp.status_code == 404

    def test_response_shape_has_queued_and_execution_ids(self, client: TestClient, db: Session):
        org = _make_org(db)
        user = _make_user(db, org)
        pb = _make_playbook(db, org=org, prob_min=0.0, prob_max=1.0)
        _make_customer_health(db, org, "a@x.com", churn_probability=0.5)

        with _mock_celery() as mock_get_app:
            mock_get_app.return_value.send_task.return_value.id = "t"
            resp = client.post(
                f"/api/v1/playbooks/{pb.id}/run-batch",
                json={"filters": {}},
                headers=_headers(user),
            )

        body = resp.json()
        assert "queued" in body
        assert "execution_ids" in body
