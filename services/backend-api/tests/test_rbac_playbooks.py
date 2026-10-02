"""RBAC for playbook mutations: admin/owner only (mutation-route-rbac, backend-gating)."""

from unittest.mock import patch

import pytest

from src.models.churn_playbook import ChurnPlaybook, ChurnPlaybookExecution
from src.models.customer_health import CustomerHealth

ROLE_DETAIL = "This action requires admin or owner privileges"
PAYLOAD = {
    "name": "RBAC Playbook",
    "probability_min": 0.5,
    "probability_max": 0.7,
    "action_sequence": [{"type": "send_notification", "config": {"message": "hi"}}],
}


@pytest.fixture(autouse=True)
def business_org(db, test_organization):
    test_organization.plan = "business"
    db.commit()


@pytest.fixture
def playbook(db, test_organization):
    pb = ChurnPlaybook(
        organization_id=test_organization.id,
        name="Existing",
        probability_min=0.5,
        probability_max=0.7,
        action_sequence=PAYLOAD["action_sequence"],
        is_template=False,
        is_active=True,
    )
    db.add(pb)
    db.commit()
    db.refresh(pb)
    return pb


def _call(client, method, path, headers, **kw):
    with patch("src.background.celery_client.get_celery_app") as app_mock:
        app_mock.return_value.send_task.return_value.id = "t"
        return client.request(method, path, headers=headers, **kw)


def _routes(pb):
    return [
        ("POST", "/api/v1/playbooks", {"json": PAYLOAD}),
        ("PUT", f"/api/v1/playbooks/{pb.id}", {"json": {"name": "Renamed"}}),
        ("POST", f"/api/v1/playbooks/{pb.id}/run", {"json": {"customer_email": "c@example.com"}}),
        ("POST", f"/api/v1/playbooks/{pb.id}/run-batch", {"json": {}}),
        ("DELETE", f"/api/v1/playbooks/{pb.id}", {}),
    ]


@pytest.mark.parametrize("idx", range(5))
def test_member_gets_403_on_every_mutation(client, member_headers, playbook, db, idx):
    method, path, kw = _routes(playbook)[idx]
    resp = _call(client, method, path, member_headers, **kw)
    assert resp.status_code == 403
    assert resp.json()["detail"] == ROLE_DETAIL
    # no side effects
    assert db.query(ChurnPlaybookExecution).count() == 0
    assert db.query(ChurnPlaybook).count() == 1
    db.refresh(playbook)
    assert playbook.name == "Existing"


@pytest.mark.parametrize("headers_fixture", ["auth_headers", "owner_headers"])
@pytest.mark.parametrize("idx", range(5))
def test_admin_and_owner_succeed(client, request, playbook, headers_fixture, idx):
    headers = request.getfixturevalue(headers_fixture)
    method, path, kw = _routes(playbook)[idx]
    resp = _call(client, method, path, headers, **kw)
    assert resp.status_code in (200, 201, 204), resp.text


def test_member_can_still_read(client, member_headers, playbook):
    assert client.get("/api/v1/playbooks", headers=member_headers).status_code == 200
    assert client.get(f"/api/v1/playbooks/{playbook.id}", headers=member_headers).status_code == 200


def test_cross_org_still_404_for_admin(client, auth_headers, db):
    from src.models.organization import Organization

    other = Organization(name="Other", plan="business")
    db.add(other)
    db.commit()
    pb = ChurnPlaybook(
        organization_id=other.id, name="Theirs", probability_min=0.1, probability_max=0.2,
        action_sequence=PAYLOAD["action_sequence"], is_template=False, is_active=True,
    )
    db.add(pb)
    db.commit()
    assert client.delete(f"/api/v1/playbooks/{pb.id}", headers=auth_headers).status_code == 404


def test_demoted_user_is_gated_immediately(client, auth_headers, test_user, db):
    """Role is read from the DB row, so a still-valid admin token stops working after demotion."""
    test_user.role = "member"
    db.commit()
    resp = client.post("/api/v1/playbooks", json=PAYLOAD, headers=auth_headers)
    assert resp.status_code == 403
    assert resp.json()["detail"] == ROLE_DETAIL
