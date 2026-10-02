"""RBAC for assignment-rule CRUD and auto-assignment settings (mutation-route-rbac)."""

import pytest

from src.models.assignment_rule import AssignmentRule

ROLE_DETAIL = "This action requires admin or owner privileges"


@pytest.fixture
def rule(db, test_organization, test_user):
    r = AssignmentRule(
        organization_id=test_organization.id, rule_type="category", match_field="category",
        match_value="billing", assign_to_user_id=test_user.id, priority=1, is_active=True,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _routes(rule, assignee_id):
    base = "/api/v1/workflow"
    return [
        ("POST", f"{base}/assignment-rules", {"json": {
            "match_field": "category", "match_value": "bugs", "assign_to_user_id": assignee_id}}),
        ("PATCH", f"{base}/assignment-rules/{rule.id}", {"json": {"priority": 9}}),
        ("DELETE", f"{base}/assignment-rules/{rule.id}", {}),
        ("PATCH", f"{base}/auto-assignment-settings", {"json": {"auto_assignment_enabled": True}}),
    ]


@pytest.mark.parametrize("idx", range(4))
def test_member_gets_403(client, member_headers, rule, test_user, test_organization, db, idx):
    method, path, kw = _routes(rule, test_user.id)[idx]
    resp = client.request(method, path, headers=member_headers, **kw)
    assert resp.status_code == 403
    assert resp.json()["detail"] == ROLE_DETAIL
    assert db.query(AssignmentRule).count() == 1
    db.refresh(rule)
    assert rule.priority == 1
    db.refresh(test_organization)
    assert not test_organization.auto_assignment_enabled


@pytest.mark.parametrize("headers_fixture", ["auth_headers", "owner_headers"])
@pytest.mark.parametrize("idx", range(4))
def test_admin_and_owner_succeed(client, request, rule, test_user, headers_fixture, idx):
    method, path, kw = _routes(rule, test_user.id)[idx]
    resp = client.request(method, path, headers=request.getfixturevalue(headers_fixture), **kw)
    assert resp.status_code in (200, 201, 204), resp.text


def test_member_can_still_read_rules_and_settings(client, member_headers, rule):
    assert client.get("/api/v1/workflow/assignment-rules", headers=member_headers).status_code == 200
    assert client.get("/api/v1/workflow/auto-assignment-settings", headers=member_headers).status_code == 200


def test_cross_org_rule_still_404_for_admin(client, auth_headers, db):
    from src.models.organization import Organization
    from src.models.user import User

    other = Organization(name="Other", plan="pro")
    db.add(other)
    db.commit()
    u = User(email="o@other.com", password_hash="x", organization_id=other.id, role="admin")
    db.add(u)
    db.commit()
    r = AssignmentRule(organization_id=other.id, rule_type="category", match_field="category",
                       match_value="x", assign_to_user_id=u.id, priority=0, is_active=True)
    db.add(r)
    db.commit()
    assert client.delete(f"/api/v1/workflow/assignment-rules/{r.id}", headers=auth_headers).status_code == 404
