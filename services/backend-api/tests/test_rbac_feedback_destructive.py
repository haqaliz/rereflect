"""RBAC for destructive feedback routes; member-open feedback routes stay open."""

import pytest

from src.models.feedback import FeedbackItem

ROLE_DETAIL = "This action requires admin or owner privileges"


def test_member_cannot_delete_feedback(client, member_headers, test_feedback, db):
    resp = client.delete(f"/api/v1/feedback/{test_feedback.id}", headers=member_headers)
    assert resp.status_code == 403
    assert resp.json()["detail"] == ROLE_DETAIL
    assert db.query(FeedbackItem).filter_by(id=test_feedback.id).first() is not None


def test_member_cannot_bulk_delete_feedback(client, member_headers, test_feedback, db):
    resp = client.post("/api/v1/feedback/bulk-delete",
                       json={"feedback_ids": [test_feedback.id]}, headers=member_headers)
    assert resp.status_code == 403
    assert resp.json()["detail"] == ROLE_DETAIL
    assert db.query(FeedbackItem).filter_by(id=test_feedback.id).first() is not None


@pytest.mark.parametrize("headers_fixture", ["auth_headers", "owner_headers"])
def test_admin_and_owner_can_delete_feedback(client, request, test_feedback, db, headers_fixture):
    fb_id = test_feedback.id
    resp = client.delete(f"/api/v1/feedback/{fb_id}",
                         headers=request.getfixturevalue(headers_fixture))
    assert resp.status_code == 204
    assert db.query(FeedbackItem).filter_by(id=fb_id).first() is None


@pytest.mark.parametrize("headers_fixture", ["auth_headers", "owner_headers"])
def test_admin_and_owner_can_bulk_delete_feedback(client, request, test_feedback, db, headers_fixture):
    fb_id = test_feedback.id
    resp = client.post("/api/v1/feedback/bulk-delete", json={"feedback_ids": [fb_id]},
                       headers=request.getfixturevalue(headers_fixture))
    assert resp.status_code == 200
    assert db.query(FeedbackItem).filter_by(id=fb_id).first() is None


def test_cross_org_delete_still_404_for_admin(client, auth_headers, db):
    from src.models.organization import Organization

    other = Organization(name="Other", plan="pro")
    db.add(other)
    db.commit()
    fb = FeedbackItem(organization_id=other.id, text="x", source="email")
    db.add(fb)
    db.commit()
    assert client.delete(f"/api/v1/feedback/{fb.id}", headers=auth_headers).status_code == 404


# --- member-open regression -------------------------------------------------


def test_member_can_still_create_and_update_feedback(client, member_headers, test_feedback):
    resp = client.post("/api/v1/feedback/", json={"text": "member feedback", "source": "email"},
                       headers=member_headers)
    assert resp.status_code in (200, 201), resp.text
    resp = client.patch(f"/api/v1/feedback/{test_feedback.id}", json={"text": "edited by member"},
                        headers=member_headers)
    assert resp.status_code == 200, resp.text


def test_member_can_still_change_status_and_assign(client, member_headers, test_feedback, member_user):
    resp = client.post("/api/v1/workflow/status",
                       json={"feedback_ids": [test_feedback.id], "new_status": "in_review"},
                       headers=member_headers)
    assert resp.status_code == 200, resp.text
    resp = client.post("/api/v1/workflow/assign",
                       json={"feedback_ids": [test_feedback.id], "assign_to_user_id": member_user.id},
                       headers=member_headers)
    assert resp.status_code == 200, resp.text
