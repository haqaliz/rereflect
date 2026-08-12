"""
TDD tests — bulk-campaign-api aspect, Phase 2 (route) + Phase 3 (list/retry).

Route contract (consumed by bulk-campaign-ui):

  POST /api/v1/customers/bulk/outreach      (admin/owner)
      body  {cohort: Cohort, subject: str, body: str}   (extra="forbid")
      ?count_only=true
      → 202 {matched, queued, skipped, errors}   (real run)
      → 200 {matched, queued: 0, skipped, errors: []}  (count_only, zero mutation)
      422: subject 1..200 / body 1..20000 / extra field / Cohort not-exactly-one
           / cohort > 500 (real run) / matched == 0 (real run)
      403 member · 401 unauthenticated

  GET  /api/v1/outreach/campaigns          (admin/owner)
      ?page&page_size (1..100) → {items: [CampaignSummary], total, page, page_size}
      CampaignSummary: {id, subject, status, recipient_count,
                        counts: {queued, sent, skipped, failed}, created_at}

  POST /api/v1/outreach/campaigns/{id}/retry  (admin/owner)
      → 200 BulkOutreachResponse {matched: queued-found, queued: dispatched,
                                  skipped: 0, errors: []}
      404 cross-org campaign id

Celery is always mocked via `src.background.celery_client.get_celery_app` —
assert dispatch name/args, never real sends.
"""

import pytest
from sqlalchemy.orm import Session

from src.models.customer_health import CustomerHealth
from src.models.organization import Organization
from src.models.user import User
from src.api.auth import hash_password, create_access_token

BULK_OUTREACH_URL = "/api/v1/customers/bulk/outreach"
CAMPAIGNS_URL = "/api/v1/outreach/campaigns"
TASK_NAME = "tasks.outreach.send_outreach_email"


# ---------------------------------------------------------------------------
# Fixtures (mirror tests/test_customers_bulk.py)
# ---------------------------------------------------------------------------

@pytest.fixture
def org(db: Session) -> Organization:
    o = Organization(name="Bulk Co", plan="business")
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


@pytest.fixture
def other_org(db: Session) -> Organization:
    o = Organization(name="Other Bulk Co", plan="business")
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


def _make_user(db, org, email, role="owner", is_deactivated=False):
    u = User(
        email=email,
        password_hash=hash_password("password123"),
        organization_id=org.id,
        role=role,
        is_deactivated=is_deactivated,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _headers_for(u: User) -> dict:
    token = create_access_token({"user_id": u.id, "organization_id": u.organization_id, "role": u.role})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def owner_user(db, org):
    return _make_user(db, org, "owner@bulk.com", role="owner")


@pytest.fixture
def member_user(db, org):
    return _make_user(db, org, "member@bulk.com", role="member")


@pytest.fixture
def owner_headers(owner_user):
    return _headers_for(owner_user)


@pytest.fixture
def member_headers(member_user):
    return _headers_for(member_user)


def _make_health(db, org, email, *, opted_out=False, archived=False, segment=None):
    ch = CustomerHealth(
        organization_id=org.id,
        customer_email=email,
        health_score=50,
        outreach_opt_out=opted_out,
        is_archived=archived,
        segment=segment,
    )
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return ch


def _mock_celery(mock_get_app):
    mock_get_app.return_value.send_task.return_value.id = "t"
    return mock_get_app.return_value


def _body(cohort, subject="Hello there", body="We'd love your feedback."):
    return {"cohort": cohort, "subject": subject, "body": body}


# ---------------------------------------------------------------------------
# Phase 2 — POST /customers/bulk/outreach, real run (AC1)
# ---------------------------------------------------------------------------

class TestBulkOutreachRealRun:
    def test_real_run_202_shape_rows_and_dispatch(self, client, db, org, owner_headers):
        _make_health(db, org, "a@test.com")
        _make_health(db, org, "b@test.com")
        _make_health(db, org, "c@test.com")

        with __import__("unittest.mock").mock.patch(
            "src.background.celery_client.get_celery_app"
        ) as mock_get_app:
            app = _mock_celery(mock_get_app)
            resp = client.post(
                BULK_OUTREACH_URL,
                json=_body({"emails": ["a@test.com", "b@test.com", "c@test.com"]}),
                headers=owner_headers,
            )

        assert resp.status_code == 202
        assert resp.json() == {"matched": 3, "queued": 3, "skipped": 0, "errors": []}

        from src.models.outreach_campaign import (
            OutreachCampaign,
            OutreachCampaignRecipient,
        )
        campaigns = db.query(OutreachCampaign).filter_by(organization_id=org.id).all()
        assert len(campaigns) == 1
        campaign = campaigns[0]
        assert campaign.subject == "Hello there"
        assert campaign.recipient_count == 3
        assert campaign.status == "in_progress"

        recipients = (
            db.query(OutreachCampaignRecipient)
            .filter_by(campaign_id=campaign.id)
            .order_by(OutreachCampaignRecipient.customer_email)
            .all()
        )
        assert [r.customer_email for r in recipients] == ["a@test.com", "b@test.com", "c@test.com"]
        assert all(r.status == "queued" and r.error is None for r in recipients)

        assert app.send_task.call_count == 3
        dispatched = {(c.kwargs["args"][0], c.kwargs["args"][1]) for c in app.send_task.call_args_list}
        assert all(c.args[0] == TASK_NAME for c in app.send_task.call_args_list)
        assert dispatched == {(campaign.id, r.id) for r in recipients}

    def test_campaign_done_immediately_when_all_skipped(self, client, db, org, owner_headers):
        _make_health(db, org, "opted@test.com", opted_out=True)
        _make_health(db, org, "bad-email")  # no "@" -> invalid email

        with __import__("unittest.mock").mock.patch(
            "src.background.celery_client.get_celery_app"
        ) as mock_get_app:
            app = _mock_celery(mock_get_app)
            resp = client.post(
                BULK_OUTREACH_URL,
                json=_body({"emails": ["opted@test.com", "bad-email"]}),
                headers=owner_headers,
            )

        assert resp.status_code == 202
        assert resp.json() == {"matched": 2, "queued": 0, "skipped": 2, "errors": []}
        assert app.send_task.call_count == 0

        from src.models.outreach_campaign import (
            OutreachCampaign,
            OutreachCampaignRecipient,
        )
        campaign = db.query(OutreachCampaign).filter_by(organization_id=org.id).first()
        assert campaign.status == "done"
        recipients = (
            db.query(OutreachCampaignRecipient)
            .filter_by(campaign_id=campaign.id)
            .order_by(OutreachCampaignRecipient.customer_email)
            .all()
        )
        statuses = {r.customer_email: (r.status, r.error) for r in recipients}
        assert statuses["opted@test.com"] == ("skipped", "opted out")
        assert statuses["bad-email"] == ("skipped", "invalid email")

    def test_dispatch_failure_is_loud_in_errors_still_202(self, client, db, org, owner_headers):
        _make_health(db, org, "a@test.com")
        _make_health(db, org, "b@test.com")

        with __import__("unittest.mock").mock.patch(
            "src.background.celery_client.get_celery_app"
        ) as mock_get_app:
            mock_get_app.return_value.send_task.side_effect = RuntimeError("broker down")
            resp = client.post(
                BULK_OUTREACH_URL,
                json=_body({"emails": ["a@test.com", "b@test.com"]}),
                headers=owner_headers,
            )

        assert resp.status_code == 202
        data = resp.json()
        assert data["matched"] == 2
        assert data["queued"] == 0
        assert len(data["errors"]) == 2
        assert all("broker down" in e for e in data["errors"])

        from src.models.outreach_campaign import (
            OutreachCampaign,
            OutreachCampaignRecipient,
        )
        campaign = db.query(OutreachCampaign).filter_by(organization_id=org.id).first()
        # Nothing was dispatched, but the recipients are still `queued` in the
        # DB waiting for the retry endpoint — the campaign stays in_progress.
        assert campaign.status == "in_progress"
        assert db.query(OutreachCampaignRecipient).filter_by(
            campaign_id=campaign.id, status="queued"
        ).count() == 2

    def test_emails_mode_includes_archived_and_skips_them_loudly(
        self, client, db, org, owner_headers
    ):
        _make_health(db, org, "arch@test.com", archived=True)
        _make_health(db, org, "ok@test.com")

        with __import__("unittest.mock").mock.patch(
            "src.background.celery_client.get_celery_app"
        ) as mock_get_app:
            app = _mock_celery(mock_get_app)
            resp = client.post(
                BULK_OUTREACH_URL,
                json=_body({"emails": ["arch@test.com", "ok@test.com"]}),
                headers=owner_headers,
            )

        assert resp.status_code == 202
        assert resp.json() == {"matched": 2, "queued": 1, "skipped": 1, "errors": []}
        assert app.send_task.call_count == 1

        from src.models.outreach_campaign import (
            OutreachCampaign,
            OutreachCampaignRecipient,
        )
        campaign = db.query(OutreachCampaign).filter_by(organization_id=org.id).first()
        recipients = {
            r.customer_email: (r.status, r.error)
            for r in db.query(OutreachCampaignRecipient).filter_by(campaign_id=campaign.id)
        }
        assert recipients["arch@test.com"] == ("skipped", "archived")
        assert recipients["ok@test.com"] == ("queued", None)

    def test_filter_mode_include_archived_skips_archived_loudly(
        self, client, db, org, owner_headers
    ):
        _make_health(db, org, "arch@test.com", archived=True)
        _make_health(db, org, "ok@test.com")

        with __import__("unittest.mock").mock.patch(
            "src.background.celery_client.get_celery_app"
        ) as mock_get_app:
            app = _mock_celery(mock_get_app)
            resp = client.post(
                BULK_OUTREACH_URL,
                json=_body({"filter": {"include_archived": True}}),
                headers=owner_headers,
            )

        assert resp.status_code == 202
        assert resp.json() == {"matched": 2, "queued": 1, "skipped": 1, "errors": []}
        assert app.send_task.call_count == 1

    def test_filter_mode_default_excludes_archived_from_matched(
        self, client, db, org, owner_headers
    ):
        _make_health(db, org, "arch@test.com", archived=True)
        _make_health(db, org, "ok@test.com")

        with __import__("unittest.mock").mock.patch(
            "src.background.celery_client.get_celery_app"
        ) as mock_get_app:
            app = _mock_celery(mock_get_app)
            resp = client.post(
                BULK_OUTREACH_URL,
                json=_body({"filter": {}}),
                headers=owner_headers,
            )

        assert resp.status_code == 202
        assert resp.json() == {"matched": 1, "queued": 1, "skipped": 0, "errors": []}
        assert app.send_task.call_count == 1


# ---------------------------------------------------------------------------
# Phase 2 — count_only (AC2)
# ---------------------------------------------------------------------------

class TestCountOnly:
    def test_count_only_returns_200_with_queued_zero_and_no_mutation(
        self, client, db, org, owner_headers
    ):
        _make_health(db, org, "a@test.com")
        _make_health(db, org, "opted@test.com", opted_out=True)
        _make_health(db, org, "bad-email")

        with __import__("unittest.mock").mock.patch(
            "src.background.celery_client.get_celery_app"
        ) as mock_get_app:
            app = _mock_celery(mock_get_app)
            resp = client.post(
                BULK_OUTREACH_URL + "?count_only=true",
                json=_body({"emails": ["a@test.com", "opted@test.com", "bad-email"]}),
                headers=owner_headers,
            )

        assert resp.status_code == 200
        assert resp.json() == {"matched": 3, "queued": 0, "skipped": 2, "errors": []}
        assert app.send_task.call_count == 0

        from src.models.outreach_campaign import (
            OutreachCampaign,
            OutreachCampaignRecipient,
        )
        assert db.query(OutreachCampaign).count() == 0
        assert db.query(OutreachCampaignRecipient).count() == 0

    def test_count_only_empty_cohort_returns_zeros(self, client, db, org, owner_headers):
        with __import__("unittest.mock").mock.patch(
            "src.background.celery_client.get_celery_app"
        ) as mock_get_app:
            app = _mock_celery(mock_get_app)
            resp = client.post(
                BULK_OUTREACH_URL + "?count_only=true",
                json=_body({"emails": ["unknown@nowhere.com"]}),
                headers=owner_headers,
            )

        assert resp.status_code == 200
        assert resp.json() == {"matched": 0, "queued": 0, "skipped": 0, "errors": []}
        assert app.send_task.call_count == 0

    def test_count_only_over_500_passes(self, client, db, org, owner_headers):
        for i in range(501):
            _make_health(db, org, f"c{i}@test.com")

        with __import__("unittest.mock").mock.patch(
            "src.background.celery_client.get_celery_app"
        ) as mock_get_app:
            app = _mock_celery(mock_get_app)
            resp = client.post(
                BULK_OUTREACH_URL + "?count_only=true",
                json=_body({"emails": [f"c{i}@test.com" for i in range(501)]}),
                headers=owner_headers,
            )

        assert resp.status_code == 200
        assert resp.json()["matched"] == 501
        assert resp.json()["queued"] == 0
        assert app.send_task.call_count == 0


# ---------------------------------------------------------------------------
# Phase 2 — validation (AC4)
# ---------------------------------------------------------------------------

class TestValidation:
    def test_subject_over_200_chars_422(self, client, db, org, owner_headers):
        _make_health(db, org, "a@test.com")
        resp = client.post(
            BULK_OUTREACH_URL,
            json=_body({"emails": ["a@test.com"]}, subject="x" * 201),
            headers=owner_headers,
        )
        assert resp.status_code == 422

    def test_body_over_20000_chars_422(self, client, db, org, owner_headers):
        _make_health(db, org, "a@test.com")
        resp = client.post(
            BULK_OUTREACH_URL,
            json=_body({"emails": ["a@test.com"]}, body="y" * 20001),
            headers=owner_headers,
        )
        assert resp.status_code == 422

    def test_blank_subject_422(self, client, db, org, owner_headers):
        resp = client.post(
            BULK_OUTREACH_URL,
            json=_body({"emails": ["a@test.com"]}, subject="   "),
            headers=owner_headers,
        )
        assert resp.status_code == 422

    def test_blank_body_422(self, client, db, org, owner_headers):
        resp = client.post(
            BULK_OUTREACH_URL,
            json=_body({"emails": ["a@test.com"]}, body=""),
            headers=owner_headers,
        )
        assert resp.status_code == 422

    def test_extra_field_422(self, client, db, org, owner_headers):
        resp = client.post(
            BULK_OUTREACH_URL,
            json={**_body({"emails": ["a@test.com"]}), "cc": "x@test.com"},
            headers=owner_headers,
        )
        assert resp.status_code == 422

    def test_cohort_with_both_emails_and_filter_422(self, client, db, org, owner_headers):
        resp = client.post(
            BULK_OUTREACH_URL,
            json=_body({"emails": ["a@test.com"], "filter": {}}),
            headers=owner_headers,
        )
        assert resp.status_code == 422

    def test_cohort_with_neither_422(self, client, db, org, owner_headers):
        resp = client.post(
            BULK_OUTREACH_URL,
            json=_body({}),
            headers=owner_headers,
        )
        assert resp.status_code == 422

    def test_real_run_over_500_422(self, client, db, org, owner_headers):
        for i in range(501):
            _make_health(db, org, f"c{i}@test.com")

        resp = client.post(
            BULK_OUTREACH_URL,
            json=_body({"emails": [f"c{i}@test.com" for i in range(501)]}),
            headers=owner_headers,
        )
        assert resp.status_code == 422
        assert "500" in resp.json()["detail"]

    def test_real_run_matched_zero_422(self, client, db, org, owner_headers):
        resp = client.post(
            BULK_OUTREACH_URL,
            json=_body({"emails": ["unknown@nowhere.com"]}),
            headers=owner_headers,
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Phase 2 — RBAC (AC5)
# ---------------------------------------------------------------------------

class TestRBAC:
    def test_member_role_403(self, client, db, org, member_headers):
        resp = client.post(
            BULK_OUTREACH_URL,
            json=_body({"emails": ["a@test.com"]}),
            headers=member_headers,
        )
        assert resp.status_code == 403

    def test_unauthenticated_401(self, client, db, org):
        resp = client.post(
            BULK_OUTREACH_URL,
            json=_body({"emails": ["a@test.com"]}),
            headers={"Authorization": "Bearer invalidtoken"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Phase 3 — GET /outreach/campaigns (AC7)
# ---------------------------------------------------------------------------

class TestCampaignList:
    def _make_recipient(self, db, campaign_id, email, status="queued", error=None):
        from src.models.outreach_campaign import OutreachCampaignRecipient
        r = OutreachCampaignRecipient(
            campaign_id=campaign_id, customer_email=email, status=status, error=error
        )
        db.add(r)
        db.commit()
        db.refresh(r)
        return r

    def _make_campaign(self, db, org, subject="S", status="in_progress", n=0, minutes_ago=0):
        from datetime import datetime, timedelta
        from src.models.outreach_campaign import OutreachCampaign
        c = OutreachCampaign(
            organization_id=org.id,
            created_by_user_id=None,
            subject=subject,
            body="b",
            recipient_count=n,
            status=status,
        )
        if minutes_ago:
            c.created_at = datetime.utcnow() - timedelta(minutes=minutes_ago)
        db.add(c)
        db.commit()
        db.refresh(c)
        return c

    def test_list_returns_org_scoped_campaigns_newest_first_with_counts(
        self, client, db, org, other_org, owner_headers
    ):
        c_old = self._make_campaign(db, org, subject="Old", n=3, minutes_ago=10)
        self._make_recipient(db, c_old.id, "a@x.com", status="sent")
        self._make_recipient(db, c_old.id, "b@x.com", status="skipped", error="opted out")
        self._make_recipient(db, c_old.id, "c@x.com", status="failed", error="no key")

        c_new = self._make_campaign(db, org, subject="New", n=1, minutes_ago=1)
        self._make_recipient(db, c_new.id, "d@x.com", status="queued")

        other = self._make_campaign(db, other_org, subject="Other", n=1, minutes_ago=1)
        self._make_recipient(db, other.id, "e@x.com", status="queued")

        resp = client.get(CAMPAIGNS_URL, headers=owner_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert [item["subject"] for item in data["items"]] == ["New", "Old"]

        new_item, old_item = data["items"]
        assert new_item["counts"] == {"queued": 1, "sent": 0, "skipped": 0, "failed": 0}
        assert new_item["recipient_count"] == 1
        assert old_item["counts"] == {"queued": 0, "sent": 1, "skipped": 1, "failed": 1}
        assert old_item["recipient_count"] == 3
        assert old_item["status"] == "in_progress"
        assert sum(old_item["counts"].values()) == old_item["recipient_count"]

    def test_list_pagination(self, client, db, org, owner_headers):
        for i in range(5):
            c = self._make_campaign(db, org, subject=f"S{i}", n=0, minutes_ago=i)
            self._make_recipient(db, c.id, f"a{i}@x.com", status="sent")

        resp = client.get(CAMPAIGNS_URL + "?page=2&page_size=2", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert data["page"] == 2
        assert data["page_size"] == 2
        assert len(data["items"]) == 2

    def test_list_member_403(self, client, db, org, member_headers):
        resp = client.get(CAMPAIGNS_URL, headers=member_headers)
        assert resp.status_code == 403

    def test_list_unauthenticated_401(self, client, db, org):
        resp = client.get(
            CAMPAIGNS_URL,
            headers={"Authorization": "Bearer invalidtoken"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Phase 3 — POST /outreach/campaigns/{id}/retry (AC8)
# ---------------------------------------------------------------------------

class TestCampaignRetry:
    def _make_campaign(self, db, org, status="in_progress", n=0):
        from src.models.outreach_campaign import OutreachCampaign
        c = OutreachCampaign(
            organization_id=org.id,
            created_by_user_id=None,
            subject="S",
            body="b",
            recipient_count=n,
            status=status,
        )
        db.add(c)
        db.commit()
        db.refresh(c)
        return c

    def _make_recipient(self, db, campaign_id, email, status="queued", error=None):
        from src.models.outreach_campaign import OutreachCampaignRecipient
        r = OutreachCampaignRecipient(
            campaign_id=campaign_id, customer_email=email, status=status, error=error
        )
        db.add(r)
        db.commit()
        db.refresh(r)
        return r

    def test_retry_re_enqueues_only_queued(self, client, db, org, owner_headers):
        campaign = self._make_campaign(db, org, n=3)
        r_queued1 = self._make_recipient(db, campaign.id, "q1@x.com", status="queued")
        r_queued2 = self._make_recipient(db, campaign.id, "q2@x.com", status="queued")
        r_sent = self._make_recipient(db, campaign.id, "sent@x.com", status="sent")

        with __import__("unittest.mock").mock.patch(
            "src.background.celery_client.get_celery_app"
        ) as mock_get_app:
            app = _mock_celery(mock_get_app)
            resp = client.post(
                f"/api/v1/outreach/campaigns/{campaign.id}/retry",
                headers=owner_headers,
            )

        assert resp.status_code == 200
        assert resp.json() == {"matched": 2, "queued": 2, "skipped": 0, "errors": []}
        assert app.send_task.call_count == 2
        dispatched = {
            (c.args[0], c.kwargs["args"][0], c.kwargs["args"][1])
            for c in app.send_task.call_args_list
        }
        assert dispatched == {(TASK_NAME, campaign.id, r_queued1.id), (TASK_NAME, campaign.id, r_queued2.id)}

        # Terminal rows untouched; queued rows stay queued (the task flips them).
        db.expire_all()
        assert db.query(
            __import__("src.models.outreach_campaign", fromlist=["OutreachCampaignRecipient"]).OutreachCampaignRecipient
        ).filter_by(id=r_sent.id).first().status == "sent"

        # Campaign moved queued -> in_progress when >= 1 dispatched.
        from src.models.outreach_campaign import OutreachCampaign
        assert db.query(OutreachCampaign).filter_by(id=campaign.id).first().status == "in_progress"

    def test_retry_all_terminal_is_noop_zeros(self, client, db, org, owner_headers):
        campaign = self._make_campaign(db, org, status="done", n=2)
        self._make_recipient(db, campaign.id, "a@x.com", status="sent")
        self._make_recipient(db, campaign.id, "b@x.com", status="failed", error="no key")

        with __import__("unittest.mock").mock.patch(
            "src.background.celery_client.get_celery_app"
        ) as mock_get_app:
            app = _mock_celery(mock_get_app)
            resp = client.post(
                f"/api/v1/outreach/campaigns/{campaign.id}/retry",
                headers=owner_headers,
            )

        assert resp.status_code == 200
        assert resp.json() == {"matched": 0, "queued": 0, "skipped": 0, "errors": []}
        assert app.send_task.call_count == 0

    def test_retry_cross_org_404(self, client, db, org, other_org, owner_headers):
        from src.models.outreach_campaign import OutreachCampaign
        other = OutreachCampaign(
            organization_id=other_org.id, created_by_user_id=None,
            subject="S", body="b", recipient_count=1, status="in_progress",
        )
        db.add(other)
        db.commit()
        db.refresh(other)

        resp = client.post(
            f"/api/v1/outreach/campaigns/{other.id}/retry",
            headers=owner_headers,
        )
        assert resp.status_code == 404

    def test_retry_unknown_campaign_404(self, client, db, org, owner_headers):
        resp = client.post("/api/v1/outreach/campaigns/999999/retry", headers=owner_headers)
        assert resp.status_code == 404

    def test_retry_member_403(self, client, db, org, member_headers):
        resp = client.post("/api/v1/outreach/campaigns/1/retry", headers=member_headers)
        assert resp.status_code == 403
