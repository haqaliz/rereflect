"""
TDD tests — POST /api/v1/copilot/actions/execute (copilot-suggested-actions,
action-registry aspect, PRD M4/M5/M6/M7/M9).

The execute route is a normal authenticated REST endpoint — deliberately not a
WebSocket message — taking the message the proposal came from, the
`proposal_id`, the `action` id, and the user-supplied params. It is
registry-gated (`min_role` enforced at execute time), org-scoped (conversation
lookup + cohort resolution), one-shot (a second execution of the same
`proposal_id` returns the prior stored outcome without re-running), and
audited (exactly one `AuditLog` row per execution).

See docs/planning/copilot-suggested-actions/action-registry/{plan,spec}.
"""
import pytest

from datetime import datetime
from sqlalchemy.orm import Session

from src.models.audit_log import AuditLog
from src.models.conversation import Conversation
from src.models.conversation_message import ConversationMessage
from src.models.customer_health import CustomerHealth
from src.models.organization import Organization
from src.models.user import User
from src.api.auth import hash_password, create_access_token
from src.services.copilot.action_registry import COPILOT_ACTION_AUDIT_ACTION


# ---------------------------------------------------------------------------
# Fixtures + builders
# ---------------------------------------------------------------------------


@pytest.fixture
def org(db: Session) -> Organization:
    o = Organization(name="Copilot Co", plan="business")
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


@pytest.fixture
def other_org(db: Session) -> Organization:
    o = Organization(name="Other Copilot Co", plan="business")
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


def _make_user(db, org, email, role="owner"):
    u = User(
        email=email,
        password_hash=hash_password("password123"),
        organization_id=org.id,
        role=role,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _headers_for(u: User) -> dict:
    token = create_access_token(
        {"user_id": u.id, "organization_id": u.organization_id, "role": u.role}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_user(db, org):
    return _make_user(db, org, "admin@copilot.com", role="admin")


@pytest.fixture
def owner_user(db, org):
    return _make_user(db, org, "owner@copilot.com", role="owner")


@pytest.fixture
def member_user(db, org):
    return _make_user(db, org, "member@copilot.com", role="member")


@pytest.fixture
def admin_headers(admin_user):
    return _headers_for(admin_user)


@pytest.fixture
def member_headers(member_user):
    return _headers_for(member_user)


def make_ch(db, org, email, **kwargs) -> CustomerHealth:
    defaults = dict(
        health_score=60,
        risk_level="moderate",
        feedback_count=5,
        confidence_level="medium",
        last_feedback_at=datetime.utcnow(),
        is_archived=False,
        churn_risk_component=50,
        sentiment_component=60,
        resolution_component=70,
        frequency_component=55,
    )
    defaults.update(kwargs)
    record = CustomerHealth(organization_id=org.id, customer_email=email, **defaults)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _tag_action(emails, action="tag_customers"):
    return {
        "action": action,
        "label": "Tag these customers…",
        "params": {"emails": list(emails)},
        "requires_input": ["tag"],
    }


def add_proposal(
    db: Session,
    org: Organization,
    *,
    proposal_id: str = "prop-1",
    emails=(),
    actions=None,
) -> tuple[Conversation, ConversationMessage]:
    """Org-scoped conversation whose assistant message carries an `actions`
    structured_data item shaped exactly like the golden fixture
    (tests/fixtures/copilot_actions_item.json)."""
    if actions is None:
        actions = [_tag_action(emails)]
    conv = Conversation(organization_id=org.id, title="Copilot triage")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    msg = ConversationMessage(
        conversation_id=conv.id,
        role="assistant",
        content="Here are the customers matching your question.",
        structured_data=[
            {
                "data_type": "actions",
                "data": {"proposal_id": proposal_id, "actions": actions},
            }
        ],
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return conv, msg


def _payload(conversation_id, proposal_id="prop-1", action="tag_customers", tag="vip"):
    return {
        "conversation_id": conversation_id,
        "proposal_id": proposal_id,
        "action": action,
        "params": {"tag": tag},
    }


def _audit_count(db: Session, org: Organization) -> int:
    return (
        db.query(AuditLog).filter(AuditLog.organization_id == org.id).count()
    )


def _customer_tags(db: Session, org: Organization, email: str):
    row = (
        db.query(CustomerHealth)
        .filter(
            CustomerHealth.organization_id == org.id,
            CustomerHealth.customer_email == email,
        )
        .first()
    )
    return row.tags


# ---------------------------------------------------------------------------
# Acceptance criteria
# ---------------------------------------------------------------------------


class TestUnknownAction:
    def test_unknown_action_404_nothing_executed_nothing_audited(
        self, client, org, db, admin_headers
    ):
        """A proposal may name an action the registry no longer allows: the
        registry is the only dispatch path and rejects it before anything
        runs (PRD M1)."""
        make_ch(db, org, "ada@example.com", tags=[])
        conv, _msg = add_proposal(
            db,
            org,
            proposal_id="prop-mystery",
            emails=["ada@example.com"],
            actions=[_tag_action(["ada@example.com"], action="mystery_action")],
        )

        r = client.post(
            "/api/v1/copilot/actions/execute",
            json=_payload(conv.id, proposal_id="prop-mystery", action="mystery_action"),
            headers=admin_headers,
        )

        assert r.status_code == 404
        assert _customer_tags(db, org, "ada@example.com") == []
        assert _audit_count(db, org) == 0


class TestMemberRBAC:
    def test_member_403_nothing_executed_nothing_audited(
        self, client, org, db, member_headers
    ):
        """min_role is enforced by the registry at execute time, not by a route
        dependency (PRD M5) — a member JWT gets 403 with nothing executed and
        nothing audited."""
        make_ch(db, org, "ada@example.com", tags=[])
        conv, _msg = add_proposal(db, org, proposal_id="prop-1", emails=["ada@example.com"])

        r = client.post(
            "/api/v1/copilot/actions/execute",
            json=_payload(conv.id),
            headers=member_headers,
        )

        assert r.status_code == 403
        assert _customer_tags(db, org, "ada@example.com") == []
        assert _audit_count(db, org) == 0


class TestExecuteSuccess:
    def test_admin_success_tags_applied_summary_returned_one_audit_row(
        self, client, org, db, admin_user, admin_headers
    ):
        make_ch(db, org, "ada@example.com", tags=["existing"])
        make_ch(db, org, "grace@example.com", tags=[])
        conv, msg = add_proposal(
            db,
            org,
            proposal_id="prop-1",
            emails=["ada@example.com", "grace@example.com"],
        )

        r = client.post(
            "/api/v1/copilot/actions/execute",
            json=_payload(conv.id),
            headers=admin_headers,
        )

        assert r.status_code == 200
        assert r.json() == {"matched": 2, "updated": 2, "skipped": 0, "errors": []}
        assert _customer_tags(db, org, "ada@example.com") == ["existing", "vip"]
        assert _customer_tags(db, org, "grace@example.com") == ["vip"]

        # Exactly one audit row, with action, target and params in details.
        assert _audit_count(db, org) == 1
        log = db.query(AuditLog).filter(AuditLog.organization_id == org.id).first()
        assert log.action == COPILOT_ACTION_AUDIT_ACTION
        assert log.target_type == "copilot_action"
        assert log.target_id == msg.id  # the ConversationMessage that carried the proposal
        assert log.user_id == admin_user.id
        assert log.user_email == admin_user.email
        assert log.details == {
            "proposal_id": "prop-1",
            "action": "tag_customers",
            "tag": "vip",
            "outcome": {"matched": 2, "updated": 2, "skipped": 0, "errors": []},
        }

    def test_owner_allowed(self, client, org, db, owner_user):
        make_ch(db, org, "ada@example.com", tags=[])
        conv, _msg = add_proposal(db, org, proposal_id="prop-1", emails=["ada@example.com"])
        headers = _headers_for(owner_user)

        r = client.post(
            "/api/v1/copilot/actions/execute",
            json=_payload(conv.id),
            headers=headers,
        )

        assert r.status_code == 200
        assert r.json() == {"matched": 1, "updated": 1, "skipped": 0, "errors": []}


class TestFrozenCohortForeignEmails:
    def test_foreign_and_unknown_emails_absorbed_as_skipped_reported(
        self, client, org, other_org, db, admin_headers
    ):
        """The cohort is the frozen proposal, never the client (PRD M9 / OQ1).
        Emails belonging to another org (or absent) are absorbed as `skipped`
        by resolve_cohort and reported — never an error, never a cross-org
        write."""
        make_ch(db, org, "ada@example.com", tags=[])
        make_ch(db, other_org, "theirs@other.com", tags=[])
        conv, _msg = add_proposal(
            db,
            org,
            proposal_id="prop-1",
            emails=["ada@example.com", "theirs@other.com", "ghost@nowhere.com"],
        )

        r = client.post(
            "/api/v1/copilot/actions/execute",
            json=_payload(conv.id),
            headers=admin_headers,
        )

        assert r.status_code == 200
        assert r.json() == {"matched": 1, "updated": 1, "skipped": 2, "errors": []}
        assert _customer_tags(db, org, "ada@example.com") == ["vip"]
        other_row = (
            db.query(CustomerHealth)
            .filter(CustomerHealth.customer_email == "theirs@other.com")
            .first()
        )
        assert other_row.tags == []  # no cross-org write
        assert _audit_count(db, other_org) == 0
        assert _audit_count(db, org) == 1


class TestOneShotGuard:
    def test_second_execution_returns_prior_outcome_without_second_audit_row(
        self, client, org, db, admin_headers
    ):
        """M9 one-shot: a second execution of the same proposal_id must not
        re-execute and must not write a second audit row — the prior stored
        outcome is returned."""
        make_ch(db, org, "ada@example.com", tags=[])
        conv, _msg = add_proposal(db, org, proposal_id="prop-1", emails=["ada@example.com"])

        first = client.post(
            "/api/v1/copilot/actions/execute",
            json=_payload(conv.id),
            headers=admin_headers,
        )
        assert first.status_code == 200
        assert _audit_count(db, org) == 1

        second = client.post(
            "/api/v1/copilot/actions/execute",
            json=_payload(conv.id),
            headers=admin_headers,
        )

        assert second.status_code == 200
        assert second.json() == first.json()
        assert _audit_count(db, org) == 1  # no second audit row
        assert second.json() == {"matched": 1, "updated": 1, "skipped": 0, "errors": []}

    def test_second_execution_with_different_tag_still_returns_stored_outcome(
        self, client, org, db, admin_headers
    ):
        """The guard is keyed on proposal_id alone (PRD OQ2): a later attempt
        carrying different user params returns the stored outcome rather than
        executing against the new tag."""
        make_ch(db, org, "ada@example.com", tags=[])
        conv, _msg = add_proposal(db, org, proposal_id="prop-1", emails=["ada@example.com"])

        first = client.post(
            "/api/v1/copilot/actions/execute",
            json=_payload(conv.id, tag="vip"),
            headers=admin_headers,
        )
        assert first.status_code == 200
        assert first.json()["updated"] == 1

        retry = client.post(
            "/api/v1/copilot/actions/execute",
            json=_payload(conv.id, tag="other-tag"),
            headers=admin_headers,
        )

        assert retry.status_code == 200
        assert retry.json() == first.json()  # stored outcome, not re-executed
        assert _customer_tags(db, org, "ada@example.com") == ["vip"]  # tag untouched
        assert _audit_count(db, org) == 1


class TestTagValidation:
    def test_tag_over_50_chars_422_nothing_applied_nothing_audited(
        self, client, org, db, admin_headers
    ):
        make_ch(db, org, "ada@example.com", tags=[])
        conv, _msg = add_proposal(db, org, proposal_id="prop-1", emails=["ada@example.com"])

        r = client.post(
            "/api/v1/copilot/actions/execute",
            json=_payload(conv.id, tag="x" * 51),
            headers=admin_headers,
        )

        assert r.status_code == 422
        assert _customer_tags(db, org, "ada@example.com") == []
        assert _audit_count(db, org) == 0

    def test_missing_tag_422(self, client, org, db, admin_headers):
        make_ch(db, org, "ada@example.com", tags=[])
        conv, _msg = add_proposal(db, org, proposal_id="prop-1", emails=["ada@example.com"])
        body = _payload(conv.id)
        body["params"] = {}

        r = client.post(
            "/api/v1/copilot/actions/execute", json=body, headers=admin_headers
        )

        assert r.status_code == 422
        assert _customer_tags(db, org, "ada@example.com") == []
        assert _audit_count(db, org) == 0

    def test_whitespace_only_tag_422(self, client, org, db, admin_headers):
        make_ch(db, org, "ada@example.com", tags=[])
        conv, _msg = add_proposal(db, org, proposal_id="prop-1", emails=["ada@example.com"])

        r = client.post(
            "/api/v1/copilot/actions/execute",
            json=_payload(conv.id, tag="    "),
            headers=admin_headers,
        )

        assert r.status_code == 422
        assert _audit_count(db, org) == 0


class TestPerCustomerTagCap:
    def test_customer_at_20_tag_cap_in_errors_others_still_update(
        self, client, org, db, admin_headers
    ):
        full = make_ch(db, org, "full@example.com", tags=[f"tag{i}" for i in range(20)])
        make_ch(db, org, "room@example.com", tags=[])
        conv, _msg = add_proposal(
            db,
            org,
            proposal_id="prop-1",
            emails=["full@example.com", "room@example.com"],
        )

        r = client.post(
            "/api/v1/copilot/actions/execute",
            json=_payload(conv.id),
            headers=admin_headers,
        )

        assert r.status_code == 200
        body = r.json()
        assert body["matched"] == 2
        assert body["updated"] == 1  # only room@ updated
        assert len(body["errors"]) == 1
        assert "full@example.com" in body["errors"][0]
        assert len(full.tags) == 20  # unchanged, not truncated
        assert _customer_tags(db, org, "room@example.com") == ["vip"]
        assert _audit_count(db, org) == 1  # still exactly one audit row


class TestProposalLookup:
    def test_proposal_id_not_matching_any_message_404(
        self, client, org, db, admin_headers
    ):
        make_ch(db, org, "ada@example.com", tags=[])
        conv, _msg = add_proposal(db, org, proposal_id="prop-1", emails=["ada@example.com"])

        r = client.post(
            "/api/v1/copilot/actions/execute",
            json=_payload(conv.id, proposal_id="prop-never-issued"),
            headers=admin_headers,
        )

        assert r.status_code == 404
        assert _customer_tags(db, org, "ada@example.com") == []
        assert _audit_count(db, org) == 0

    def test_action_not_offered_by_proposal_404(
        self, client, org, db, admin_headers
    ):
        """The requested action must actually be offered by the proposal's
        actions[] list — you cannot execute an action the proposal never
        offered against its frozen cohort."""
        make_ch(db, org, "ada@example.com", tags=[])
        conv, _msg = add_proposal(
            db, org, proposal_id="prop-1", emails=["ada@example.com"], actions=[]
        )

        r = client.post(
            "/api/v1/copilot/actions/execute",
            json=_payload(conv.id, action="tag_customers"),
            headers=admin_headers,
        )

        assert r.status_code == 404
        assert _audit_count(db, org) == 0


class TestConversationScoping:
    def test_cross_org_conversation_id_404(self, client, org, other_org, db, admin_headers):
        make_ch(db, org, "ada@example.com", tags=[])
        other_conv, _msg = add_proposal(
            db, other_org, proposal_id="prop-1", emails=["ada@example.com"]
        )

        r = client.post(
            "/api/v1/copilot/actions/execute",
            json=_payload(other_conv.id),
            headers=admin_headers,
        )

        assert r.status_code == 404  # conversation lookup is org-scoped
        assert _customer_tags(db, org, "ada@example.com") == []
        assert _audit_count(db, org) == 0

    def test_nonexistent_conversation_id_404(self, client, org, db, admin_headers):
        r = client.post(
            "/api/v1/copilot/actions/execute",
            json=_payload(999999),
            headers=admin_headers,
        )
        assert r.status_code == 404
        assert _audit_count(db, org) == 0
