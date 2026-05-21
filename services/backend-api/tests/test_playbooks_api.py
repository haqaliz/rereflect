"""
Tests for Churn Playbook API (M4.1 Phase 5.1) — strict TDD (RED first).

Covers: auth/gating, CRUD, run, run-batch, executions list.
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
# Helpers
# ---------------------------------------------------------------------------

def _make_org(db: Session, plan: str = "business") -> Organization:
    org = Organization(name=f"PlaybookOrg-{plan}-{id(plan)}", plan=plan)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_user(db: Session, org: Organization, role: str = "admin") -> User:
    user = User(
        email=f"user-{org.id}-{role}@playbooks.test",
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
    name: str = "Test Playbook",
    prob_min: float = 0.50,
    prob_max: float = 0.70,
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


def _make_execution(
    db: Session,
    playbook: ChurnPlaybook,
    org: Organization,
    email: str = "customer@example.com",
    status: str = "queued",
    created_at: Optional[datetime] = None,
) -> ChurnPlaybookExecution:
    ex = ChurnPlaybookExecution(
        playbook_id=playbook.id,
        organization_id=org.id,
        customer_email=email,
        triggered_by="manual",
        status=status,
        action_log=[],
        created_at=created_at or datetime.utcnow(),
    )
    db.add(ex)
    db.commit()
    db.refresh(ex)
    return ex


def _make_customer_health(
    db: Session,
    org: Organization,
    email: str,
    churn_probability: float = 0.60,
    time_to_churn_bucket: str = "2-4w",
) -> CustomerHealth:
    ch = CustomerHealth(
        organization_id=org.id,
        customer_email=email,
        health_score=40,
        churn_probability=churn_probability,
        time_to_churn_bucket=time_to_churn_bucket,
    )
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return ch


VALID_PLAYBOOK_PAYLOAD = {
    "name": "My Playbook",
    "description": "Test",
    "probability_min": 0.50,
    "probability_max": 0.70,
    "action_sequence": [{"type": "send_notification", "config": {"message": "hi"}}],
}


# ---------------------------------------------------------------------------
# Auth / gating
# ---------------------------------------------------------------------------

def test_list_returns_403_for_pro_plan(client: TestClient, db: Session):
    org = _make_org(db, plan="pro")
    user = _make_user(db, org)
    resp = client.get("/api/v1/playbooks", headers=_headers(user))
    assert resp.status_code == 403
    assert resp.json()["detail"]["feature"] == "churn_playbooks"


def test_list_returns_200_for_business_plan(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    resp = client.get("/api/v1/playbooks", headers=_headers(user))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_list_includes_system_templates_alongside_org_playbooks(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    # One org playbook
    _make_playbook(db, org=org, name="Org Playbook")
    # One system template (organization_id=None)
    _make_playbook(db, org=None, name="System Template", is_template=True, prob_min=0.30, prob_max=0.50)

    resp = client.get("/api/v1/playbooks", headers=_headers(user))
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()]
    assert "Org Playbook" in names
    assert "System Template" in names


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def test_create_persists_playbook(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    resp = client.post("/api/v1/playbooks", json=VALID_PLAYBOOK_PAYLOAD, headers=_headers(user))
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "My Playbook"
    assert body["organization_id"] == org.id
    assert body["is_template"] is False


def test_create_from_template_copies_action_sequence(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    template_actions = [{"type": "assign", "config": {"role": "cs_lead"}}]
    tmpl = _make_playbook(
        db, org=None, name="Tmpl", is_template=True,
        prob_min=0.70, prob_max=0.85, action_sequence=template_actions
    )
    payload = {
        "name": "Clone of Tmpl",
        "probability_min": 0.70,
        "probability_max": 0.85,
        "action_sequence": template_actions,
        "source_template_id": tmpl.id,
    }
    resp = client.post("/api/v1/playbooks", json=payload, headers=_headers(user))
    assert resp.status_code == 201
    body = resp.json()
    assert body["source_template_id"] == tmpl.id
    assert body["action_sequence"] == template_actions


def test_create_validates_probability_range_inverted_400(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    payload = {**VALID_PLAYBOOK_PAYLOAD, "probability_min": 0.80, "probability_max": 0.20}
    resp = client.post("/api/v1/playbooks", json=payload, headers=_headers(user))
    assert resp.status_code == 422


def test_create_enforces_business_limit_of_20_playbooks(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    # Seed 20 active org playbooks
    for i in range(20):
        _make_playbook(db, org=org, name=f"Playbook {i}", prob_min=0.10 + i * 0.01, prob_max=0.20 + i * 0.01)
    resp = client.post("/api/v1/playbooks", json=VALID_PLAYBOOK_PAYLOAD, headers=_headers(user))
    assert resp.status_code == 409
    assert "limit" in resp.json()["detail"].lower()


def test_create_no_limit_for_enterprise_plan(client: TestClient, db: Session):
    org = _make_org(db, plan="enterprise")
    user = _make_user(db, org)
    for i in range(20):
        _make_playbook(db, org=org, name=f"Ent Playbook {i}", prob_min=0.10 + i * 0.01, prob_max=0.20 + i * 0.01)
    resp = client.post("/api/v1/playbooks", json=VALID_PLAYBOOK_PAYLOAD, headers=_headers(user))
    assert resp.status_code == 201


def test_create_rejects_empty_action_sequence_422(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    payload = {**VALID_PLAYBOOK_PAYLOAD, "action_sequence": []}
    resp = client.post("/api/v1/playbooks", json=payload, headers=_headers(user))
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Get detail
# ---------------------------------------------------------------------------

def test_get_detail_returns_recent_executions(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    pb = _make_playbook(db, org=org)
    _make_execution(db, pb, org, email="a@x.com")
    _make_execution(db, pb, org, email="b@x.com")

    resp = client.get(f"/api/v1/playbooks/{pb.id}", headers=_headers(user))
    assert resp.status_code == 200
    body = resp.json()
    assert "recent_executions" in body
    assert len(body["recent_executions"]) == 2


def test_get_detail_caps_recent_executions_at_20(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    pb = _make_playbook(db, org=org)
    for i in range(25):
        _make_execution(db, pb, org, email=f"c{i}@x.com")

    resp = client.get(f"/api/v1/playbooks/{pb.id}", headers=_headers(user))
    assert resp.status_code == 200
    assert len(resp.json()["recent_executions"]) == 20


def test_get_detail_returns_404_for_unknown_id(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    resp = client.get("/api/v1/playbooks/99999", headers=_headers(user))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

def test_update_modifies_playbook_fields(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    pb = _make_playbook(db, org=org, name="Old Name")

    resp = client.put(
        f"/api/v1/playbooks/{pb.id}",
        json={"name": "New Name", "is_active": False},
        headers=_headers(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "New Name"
    assert body["is_active"] is False


def test_update_template_returns_403(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    tmpl = _make_playbook(db, org=None, name="System", is_template=True, prob_min=0.30, prob_max=0.50)

    resp = client.put(
        f"/api/v1/playbooks/{tmpl.id}",
        json={"name": "Hacked"},
        headers=_headers(user),
    )
    assert resp.status_code == 403


def test_update_cross_org_returns_404(client: TestClient, db: Session):
    org1 = _make_org(db, plan="business")
    org2 = _make_org(db, plan="business")
    user1 = _make_user(db, org1)
    pb2 = _make_playbook(db, org=org2, name="Org2 Playbook")

    resp = client.put(
        f"/api/v1/playbooks/{pb2.id}",
        json={"name": "Cross"},
        headers=_headers(user1),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def test_delete_removes_playbook(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    pb = _make_playbook(db, org=org)

    resp = client.delete(f"/api/v1/playbooks/{pb.id}", headers=_headers(user))
    assert resp.status_code == 204

    remaining = db.query(ChurnPlaybook).filter(ChurnPlaybook.id == pb.id).first()
    assert remaining is None


def test_delete_template_returns_403(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    tmpl = _make_playbook(db, org=None, name="System Del", is_template=True, prob_min=0.10, prob_max=0.30)

    resp = client.delete(f"/api/v1/playbooks/{tmpl.id}", headers=_headers(user))
    assert resp.status_code == 403


def test_delete_cross_org_returns_404(client: TestClient, db: Session):
    org1 = _make_org(db, plan="business")
    org2 = _make_org(db, plan="business")
    user1 = _make_user(db, org1)
    pb2 = _make_playbook(db, org=org2, name="Org2 Del")

    resp = client.delete(f"/api/v1/playbooks/{pb2.id}", headers=_headers(user1))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Run single
# ---------------------------------------------------------------------------

def test_run_creates_execution_row_with_status_queued(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    pb = _make_playbook(db, org=org)

    with patch("src.background.celery_client.get_celery_app") as mock_get_app:
        mock_get_app.return_value.send_task.return_value.id = "fake-task-id"
        resp = client.post(
            f"/api/v1/playbooks/{pb.id}/run",
            json={"customer_email": "cust@example.com"},
            headers=_headers(user),
        )

    assert resp.status_code == 201
    ex_id = resp.json()["id"]
    ex = db.query(ChurnPlaybookExecution).filter(ChurnPlaybookExecution.id == ex_id).first()
    assert ex is not None
    assert ex.status == "queued"


def test_run_dispatches_celery_task_with_execution_id(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    pb = _make_playbook(db, org=org)

    with patch("src.background.celery_client.get_celery_app") as mock_get_app:
        mock_send = mock_get_app.return_value.send_task
        mock_send.return_value.id = "fake-task-id"
        resp = client.post(
            f"/api/v1/playbooks/{pb.id}/run",
            json={"customer_email": "cust@example.com"},
            headers=_headers(user),
        )

    assert resp.status_code == 201
    ex_id = resp.json()["id"]
    mock_send.assert_called_once_with(
        "tasks.churn_playbooks.run_playbook",
        args=[ex_id],
    )


def test_run_returns_execution_response_with_id(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    pb = _make_playbook(db, org=org)

    with patch("src.background.celery_client.get_celery_app") as mock_get_app:
        mock_get_app.return_value.send_task.return_value.id = "x"
        resp = client.post(
            f"/api/v1/playbooks/{pb.id}/run",
            json={"customer_email": "cust@example.com"},
            headers=_headers(user),
        )

    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    assert body["status"] == "queued"
    assert body["customer_email"] == "cust@example.com"


def test_run_404_for_unknown_playbook(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    resp = client.post(
        "/api/v1/playbooks/99999/run",
        json={"customer_email": "x@y.com"},
        headers=_headers(user),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Run batch
# ---------------------------------------------------------------------------

def test_run_batch_creates_execution_per_matching_customer(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    pb = _make_playbook(db, org=org, prob_min=0.50, prob_max=0.80)
    # 2 matching customers
    _make_customer_health(db, org, "a@x.com", churn_probability=0.60)
    _make_customer_health(db, org, "b@x.com", churn_probability=0.70)
    # 1 non-matching
    _make_customer_health(db, org, "c@x.com", churn_probability=0.20)

    with patch("src.background.celery_client.get_celery_app") as mock_get_app:
        mock_get_app.return_value.send_task.return_value.id = "task-x"
        resp = client.post(
            f"/api/v1/playbooks/{pb.id}/run-batch",
            json={"filters": {}},
            headers=_headers(user),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["queued"] == 2
    assert len(body["execution_ids"]) == 2


def test_run_batch_filters_by_probability_range(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    pb = _make_playbook(db, org=org, prob_min=0.60, prob_max=0.90)
    _make_customer_health(db, org, "in@x.com", churn_probability=0.75)
    _make_customer_health(db, org, "out@x.com", churn_probability=0.30)

    with patch("src.background.celery_client.get_celery_app") as mock_get_app:
        mock_get_app.return_value.send_task.return_value.id = "y"
        resp = client.post(
            f"/api/v1/playbooks/{pb.id}/run-batch",
            json={"filters": {"probability_min": 0.60, "probability_max": 0.90}},
            headers=_headers(user),
        )

    assert resp.status_code == 200
    assert resp.json()["queued"] == 1


def test_run_batch_enforces_business_50_daily_limit(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    pb = _make_playbook(db, org=org)
    # Seed 50 executions today
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(50):
        ex = ChurnPlaybookExecution(
            playbook_id=pb.id,
            organization_id=org.id,
            customer_email=f"daily{i}@x.com",
            triggered_by="manual",
            status="queued",
            action_log=[],
            created_at=today + timedelta(minutes=i),
        )
        db.add(ex)
    db.commit()

    # Add 1 customer to try batching
    _make_customer_health(db, org, "new@x.com", churn_probability=0.60)

    with patch("src.background.celery_client.get_celery_app") as mock_get_app:
        mock_get_app.return_value.send_task.return_value.id = "z"
        resp = client.post(
            f"/api/v1/playbooks/{pb.id}/run-batch",
            json={"filters": {}},
            headers=_headers(user),
        )

    assert resp.status_code == 429
    assert "daily" in resp.json()["detail"].lower() or "limit" in resp.json()["detail"].lower()


def test_run_batch_no_limit_for_enterprise(client: TestClient, db: Session):
    org = _make_org(db, plan="enterprise")
    user = _make_user(db, org)
    pb = _make_playbook(db, org=org, prob_min=0.50, prob_max=0.90)
    # Seed 50 executions today
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(50):
        ex = ChurnPlaybookExecution(
            playbook_id=pb.id,
            organization_id=org.id,
            customer_email=f"ent{i}@x.com",
            triggered_by="manual",
            status="queued",
            action_log=[],
            created_at=today + timedelta(minutes=i),
        )
        db.add(ex)
    db.commit()

    _make_customer_health(db, org, "ent-new@x.com", churn_probability=0.70)

    with patch("src.background.celery_client.get_celery_app") as mock_get_app:
        mock_get_app.return_value.send_task.return_value.id = "z"
        resp = client.post(
            f"/api/v1/playbooks/{pb.id}/run-batch",
            json={"filters": {}},
            headers=_headers(user),
        )

    assert resp.status_code == 200
    assert resp.json()["queued"] >= 1


# ---------------------------------------------------------------------------
# Executions list
# ---------------------------------------------------------------------------

def test_list_executions_paginates(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    pb = _make_playbook(db, org=org)
    for i in range(15):
        _make_execution(db, pb, org, email=f"p{i}@x.com")

    resp = client.get(
        "/api/v1/playbooks/executions?page=1&page_size=10",
        headers=_headers(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 10
    assert body["total"] == 15


def test_list_executions_filters_by_playbook_id(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    pb1 = _make_playbook(db, org=org, name="PB1")
    pb2 = _make_playbook(db, org=org, name="PB2", prob_min=0.60, prob_max=0.80)
    _make_execution(db, pb1, org, email="x@x.com")
    _make_execution(db, pb2, org, email="y@x.com")

    resp = client.get(
        f"/api/v1/playbooks/executions?playbook_id={pb1.id}&page=1&page_size=20",
        headers=_headers(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["playbook_id"] == pb1.id


def test_list_executions_filters_by_status(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    pb = _make_playbook(db, org=org)
    _make_execution(db, pb, org, email="q1@x.com", status="queued")
    _make_execution(db, pb, org, email="q2@x.com", status="done")

    resp = client.get(
        "/api/v1/playbooks/executions?status=queued&page=1&page_size=20",
        headers=_headers(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "queued"
