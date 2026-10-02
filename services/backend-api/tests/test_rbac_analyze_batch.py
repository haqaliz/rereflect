"""RBAC for POST /analyze/batch (org-wide LLM analysis); POST /analyze/ stays member-open."""

from unittest.mock import patch

ROLE_DETAIL = "This action requires admin or owner privileges"


def test_member_cannot_analyze_batch(client, member_headers, test_feedback):
    with patch("src.api.routes.analyze.celery_app") as celery:
        resp = client.post("/api/v1/analyze/batch", headers=member_headers)
    assert resp.status_code == 403
    assert resp.json()["detail"] == ROLE_DETAIL
    celery.send_task.assert_not_called()


def test_admin_and_owner_can_analyze_batch(client, auth_headers, owner_headers, test_feedback, db):
    test_feedback.sentiment_label = None
    db.commit()
    for headers in (auth_headers, owner_headers):
        with patch("src.api.routes.analyze.celery_app"):
            resp = client.post("/api/v1/analyze/batch", headers=headers)
        assert resp.status_code == 200, resp.text


def test_member_can_still_analyze_selected(client, member_headers, test_feedback):
    with patch("src.api.routes.analyze.celery_app") as celery:
        resp = client.post("/api/v1/analyze/", json={"feedback_ids": [test_feedback.id]},
                           headers=member_headers)
    assert resp.status_code == 200, resp.text
    celery.send_task.assert_called_once()
