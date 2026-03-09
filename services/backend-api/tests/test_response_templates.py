"""
Tests for Response Templates CRUD and suggestion algorithm.

TDD order:
1. List system templates returns 8 defaults
2. Create custom template
3. Get single template by ID
4. Update custom template
5. Delete custom template
6. Cannot edit/delete system templates
7. Template suggestion scoring
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.feedback import FeedbackItem
from src.models.response_template import ResponseTemplate
from src.config.system_templates import SYSTEM_TEMPLATES


# ===========================================================================
# Helpers
# ===========================================================================

def _seed_system_templates(db: Session) -> list[ResponseTemplate]:
    """Seed the 8 system templates into the test DB."""
    templates = []
    for t in SYSTEM_TEMPLATES:
        tmpl = ResponseTemplate(
            organization_id=None,
            name=t["name"],
            category=t["category"],
            body=t["body"],
            is_system=True,
            usage_count=0,
        )
        db.add(tmpl)
        templates.append(tmpl)
    db.commit()
    for t in templates:
        db.refresh(t)
    return templates


# ===========================================================================
# 1. List system templates returns 8 defaults
# ===========================================================================

class TestListResponseTemplates:
    def test_list_includes_system_templates(
        self, client: TestClient, auth_headers: dict, db: Session, test_organization: Organization
    ):
        """Listing templates returns the 8 system templates."""
        _seed_system_templates(db)

        response = client.get("/api/v1/response-templates", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "templates" in data
        system = [t for t in data["templates"] if t["is_system"]]
        assert len(system) == 8

    def test_list_requires_auth(self, client: TestClient):
        """Unauthenticated request is rejected."""
        response = client.get("/api/v1/response-templates")
        assert response.status_code in (401, 403)

    def test_list_requires_pro_plan(
        self, client: TestClient, db: Session, test_organization: Organization
    ):
        """Free-plan org gets 403."""
        from src.api.auth import hash_password, create_access_token

        test_organization.plan = "free"
        db.commit()
        db.refresh(test_organization)

        user = User(
            email="free@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="admin",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        token = create_access_token({"user_id": user.id, "organization_id": user.organization_id, "role": user.role})
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/api/v1/response-templates", headers=headers)
        assert response.status_code == 403

    def test_list_separates_system_and_custom(
        self, client: TestClient, auth_headers: dict, db: Session, test_organization: Organization
    ):
        """Response distinguishes system templates from org custom ones."""
        _seed_system_templates(db)
        custom = ResponseTemplate(
            organization_id=test_organization.id,
            name="My Custom Template",
            category="Sales",
            body="Hello {{customer_name}}, ...",
            is_system=False,
        )
        db.add(custom)
        db.commit()

        response = client.get("/api/v1/response-templates", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        custom_templates = [t for t in data["templates"] if not t["is_system"]]
        assert len(custom_templates) == 1
        assert custom_templates[0]["name"] == "My Custom Template"


# ===========================================================================
# 2. Create custom template
# ===========================================================================

class TestCreateResponseTemplate:
    def test_create_custom_template(
        self, client: TestClient, auth_headers: dict, db: Session
    ):
        """Admin can create a custom template."""
        payload = {
            "name": "Enterprise Welcome",
            "category": "Onboarding",
            "body": "Hi {{customer_name}}, welcome to the enterprise tier!",
        }
        response = client.post("/api/v1/response-templates", json=payload, headers=auth_headers)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Enterprise Welcome"
        assert data["category"] == "Onboarding"
        assert data["is_system"] is False
        assert data["usage_count"] == 0

    def test_create_template_requires_auth(self, client: TestClient):
        payload = {"name": "X", "category": "Y", "body": "Z"}
        response = client.post("/api/v1/response-templates", json=payload)
        assert response.status_code in (401, 403)

    def test_create_template_requires_admin_or_owner(
        self, client: TestClient, db: Session, test_organization: Organization
    ):
        """Member cannot create templates."""
        from src.api.auth import hash_password, create_access_token

        member = User(
            email="member@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="member",
        )
        db.add(member)
        db.commit()
        db.refresh(member)
        token = create_access_token({"user_id": member.id, "organization_id": member.organization_id, "role": member.role})
        headers = {"Authorization": f"Bearer {token}"}

        payload = {"name": "X", "category": "Y", "body": "Z"}
        response = client.post("/api/v1/response-templates", json=payload, headers=headers)
        assert response.status_code == 403

    def test_create_template_name_required(
        self, client: TestClient, auth_headers: dict
    ):
        payload = {"category": "Bug Report", "body": "Some text"}
        response = client.post("/api/v1/response-templates", json=payload, headers=auth_headers)
        assert response.status_code == 422

    def test_create_template_body_required(
        self, client: TestClient, auth_headers: dict
    ):
        payload = {"name": "X", "category": "Bug Report"}
        response = client.post("/api/v1/response-templates", json=payload, headers=auth_headers)
        assert response.status_code == 422


# ===========================================================================
# 3. Get single template by ID
# ===========================================================================

class TestGetResponseTemplate:
    def test_get_system_template(
        self, client: TestClient, auth_headers: dict, db: Session
    ):
        """Can retrieve a system template by ID."""
        system_templates = _seed_system_templates(db)
        tmpl_id = system_templates[0].id

        response = client.get(f"/api/v1/response-templates/{tmpl_id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == tmpl_id
        assert data["is_system"] is True

    def test_get_custom_template(
        self, client: TestClient, auth_headers: dict, db: Session, test_organization: Organization
    ):
        custom = ResponseTemplate(
            organization_id=test_organization.id,
            name="Custom",
            category="Sales",
            body="Body text",
            is_system=False,
        )
        db.add(custom)
        db.commit()
        db.refresh(custom)

        response = client.get(f"/api/v1/response-templates/{custom.id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["name"] == "Custom"

    def test_get_template_not_found(
        self, client: TestClient, auth_headers: dict
    ):
        response = client.get("/api/v1/response-templates/99999", headers=auth_headers)
        assert response.status_code == 404

    def test_get_other_org_custom_template_not_found(
        self, client: TestClient, auth_headers: dict, db: Session
    ):
        """Cannot access another org's custom template."""
        other_org = Organization(name="Other Org", plan="pro")
        db.add(other_org)
        db.commit()
        db.refresh(other_org)

        other_tmpl = ResponseTemplate(
            organization_id=other_org.id,
            name="Other Org Template",
            category="Bug Report",
            body="Other body",
            is_system=False,
        )
        db.add(other_tmpl)
        db.commit()
        db.refresh(other_tmpl)

        response = client.get(f"/api/v1/response-templates/{other_tmpl.id}", headers=auth_headers)
        assert response.status_code == 404


# ===========================================================================
# 4. Update custom template
# ===========================================================================

class TestUpdateResponseTemplate:
    def test_update_custom_template(
        self, client: TestClient, auth_headers: dict, db: Session, test_organization: Organization
    ):
        custom = ResponseTemplate(
            organization_id=test_organization.id,
            name="Old Name",
            category="Bug Report",
            body="Old body",
            is_system=False,
        )
        db.add(custom)
        db.commit()
        db.refresh(custom)

        payload = {"name": "New Name", "body": "New body"}
        response = client.put(f"/api/v1/response-templates/{custom.id}", json=payload, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name"
        assert data["body"] == "New body"
        assert data["category"] == "Bug Report"  # unchanged

    def test_update_requires_admin_or_owner(
        self, client: TestClient, db: Session, test_organization: Organization
    ):
        from src.api.auth import hash_password, create_access_token

        custom = ResponseTemplate(
            organization_id=test_organization.id,
            name="Custom",
            category="Bug Report",
            body="Body",
            is_system=False,
        )
        db.add(custom)
        db.commit()
        db.refresh(custom)

        member = User(
            email="member2@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="member",
        )
        db.add(member)
        db.commit()
        db.refresh(member)
        token = create_access_token({"user_id": member.id, "organization_id": member.organization_id, "role": member.role})

        response = client.put(
            f"/api/v1/response-templates/{custom.id}",
            json={"name": "Hacked"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403


# ===========================================================================
# 5. Delete custom template
# ===========================================================================

class TestDeleteResponseTemplate:
    def test_delete_custom_template(
        self, client: TestClient, auth_headers: dict, db: Session, test_organization: Organization
    ):
        custom = ResponseTemplate(
            organization_id=test_organization.id,
            name="To Delete",
            category="Bug Report",
            body="Delete me",
            is_system=False,
        )
        db.add(custom)
        db.commit()
        db.refresh(custom)
        tmpl_id = custom.id

        response = client.delete(f"/api/v1/response-templates/{tmpl_id}", headers=auth_headers)
        assert response.status_code == 204

        # Confirm gone
        db.expire_all()
        assert db.query(ResponseTemplate).filter(ResponseTemplate.id == tmpl_id).first() is None

    def test_delete_requires_admin_or_owner(
        self, client: TestClient, db: Session, test_organization: Organization
    ):
        from src.api.auth import hash_password, create_access_token

        custom = ResponseTemplate(
            organization_id=test_organization.id,
            name="Protected",
            category="Bug Report",
            body="Body",
            is_system=False,
        )
        db.add(custom)
        db.commit()
        db.refresh(custom)

        member = User(
            email="member3@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="member",
        )
        db.add(member)
        db.commit()
        db.refresh(member)
        token = create_access_token({"user_id": member.id, "organization_id": member.organization_id, "role": member.role})

        response = client.delete(
            f"/api/v1/response-templates/{custom.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403


# ===========================================================================
# 6. Cannot edit or delete system templates
# ===========================================================================

class TestSystemTemplateGuard:
    def test_cannot_update_system_template(
        self, client: TestClient, auth_headers: dict, db: Session
    ):
        system_templates = _seed_system_templates(db)
        tmpl_id = system_templates[0].id

        response = client.put(
            f"/api/v1/response-templates/{tmpl_id}",
            json={"name": "Hacked system"},
            headers=auth_headers,
        )
        assert response.status_code == 403

    def test_cannot_delete_system_template(
        self, client: TestClient, auth_headers: dict, db: Session
    ):
        system_templates = _seed_system_templates(db)
        tmpl_id = system_templates[0].id

        response = client.delete(
            f"/api/v1/response-templates/{tmpl_id}",
            headers=auth_headers,
        )
        assert response.status_code == 403


# ===========================================================================
# 7. Template suggestion scoring
# ===========================================================================

class TestTemplateSuggestion:
    def test_suggest_bug_report_for_bug_feedback(
        self, client: TestClient, auth_headers: dict, db: Session, test_organization: Organization
    ):
        """Bug report feedback → Bug Report Acknowledgment template suggested."""
        _seed_system_templates(db)

        feedback = FeedbackItem(
            organization_id=test_organization.id,
            text="The export button crashes every time.",
            source="email",
            sentiment_label="negative",
            is_urgent=False,
            pain_point_category="Bug Report",
            churn_risk_score=30,
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        response = client.post(
            "/api/v1/response-templates/suggest",
            json={"feedback_id": feedback.id},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["template"] is not None
        assert "Bug Report" in data["template"]["category"]
        assert data["score"] >= 50

    def test_suggest_urgent_escalation_for_urgent_feedback(
        self, client: TestClient, auth_headers: dict, db: Session, test_organization: Organization
    ):
        """Urgent feedback → Urgent Issue Escalation template preferred."""
        _seed_system_templates(db)

        feedback = FeedbackItem(
            organization_id=test_organization.id,
            text="CRITICAL: our entire team is locked out!",
            source="email",
            sentiment_label="negative",
            is_urgent=True,
            pain_point_category="Urgent",
            churn_risk_score=10,
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        response = client.post(
            "/api/v1/response-templates/suggest",
            json={"feedback_id": feedback.id},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["template"] is not None
        assert data["template"]["category"] == "Urgent"

    def test_suggest_churn_risk_for_high_churn_score(
        self, client: TestClient, auth_headers: dict, db: Session, test_organization: Organization
    ):
        """High churn risk → Churn Risk Outreach template preferred."""
        _seed_system_templates(db)

        feedback = FeedbackItem(
            organization_id=test_organization.id,
            text="I'm thinking about cancelling my subscription.",
            source="email",
            sentiment_label="negative",
            is_urgent=False,
            pain_point_category="Churn Risk",
            churn_risk_score=85,
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        response = client.post(
            "/api/v1/response-templates/suggest",
            json={"feedback_id": feedback.id},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["template"] is not None
        assert data["template"]["category"] == "Churn Risk"

    def test_suggest_returns_none_for_no_match(
        self, client: TestClient, auth_headers: dict, db: Session, test_organization: Organization
    ):
        """No template scores above threshold → template is null."""
        # No system templates seeded → nothing to match
        feedback = FeedbackItem(
            organization_id=test_organization.id,
            text="Just browsing.",
            source="email",
            sentiment_label="neutral",
            is_urgent=False,
            pain_point_category=None,
            churn_risk_score=5,
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        response = client.post(
            "/api/v1/response-templates/suggest",
            json={"feedback_id": feedback.id},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["template"] is None
        assert data["score"] == 0

    def test_suggest_feedback_not_found(
        self, client: TestClient, auth_headers: dict
    ):
        response = client.post(
            "/api/v1/response-templates/suggest",
            json={"feedback_id": 99999},
            headers=auth_headers,
        )
        assert response.status_code == 404
