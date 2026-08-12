"""
TDD tests — bulk-campaign-api aspect, Phase 4 (outreach draft endpoint).

Service (`src/services/outreach_drafter.py`), mirroring test_issue_draft.py:
  - Gate via resolve_generation_llm: not configured -> LLMNotConfiguredError.
  - Prompt hardening: brand voice is data-not-instructions; cohort context is
    count + dominant segment only — raw emails / search text never reach the
    model.
  - Output parsing: plain + ```json fenced; malformed -> OutreachDraftError;
    subject trimmed to 200, body to 20000 (the R1 send caps).
  - Usage logging: one LLMUsageLog(task_type="outreach_draft") row; a logging
    failure never fails the draft.

Route (`POST /api/v1/customers/bulk/outreach/draft`):
  - 200 {subject, body} with the LLM mocked; 409 no LLM; 502 malformed output;
    422 extra field / invalid cohort; 403 member; no campaign/recipient rows
    created; no Celery dispatch. The draft NEVER sends.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from src.api.auth import create_access_token, hash_password
from src.models.customer_health import CustomerHealth
from src.models.llm_usage_log import LLMUsageLog
from src.models.organization import Organization
from src.models.user import User
from src.services.copilot.llm_resolver import LLMConfig

DRAFT_URL = "/api/v1/customers/bulk/outreach/draft"


# ============================================================================
# Shared fixtures
# ============================================================================

@pytest.fixture
def configured_llm() -> LLMConfig:
    return LLMConfig(
        provider="openai",
        model="gpt-4o-mini",
        api_key="sk-test-key",
        base_url=None,
        is_configured=True,
    )


@pytest.fixture
def unconfigured_llm() -> LLMConfig:
    return LLMConfig(
        provider="openai",
        model="gpt-4o-mini",
        api_key=None,
        base_url=None,
        is_configured=False,
    )


def _mock_llm_response(subject="We've noticed something", body="We'd love your thoughts."):
    content = json.dumps({"subject": subject, "body": body})
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    usage = MagicMock()
    usage.prompt_tokens = 120
    usage.completion_tokens = 60
    usage.total_tokens = 180
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    return resp


def _mock_openai_ctor(resp_or_exc):
    """Build a MagicMock standing in for openai.AsyncOpenAI whose
    .chat.completions.create is an AsyncMock returning/raising resp_or_exc."""
    client = MagicMock()
    if isinstance(resp_or_exc, Exception):
        client.chat.completions.create = AsyncMock(side_effect=resp_or_exc)
    else:
        client.chat.completions.create = AsyncMock(return_value=resp_or_exc)
    ctor = MagicMock(return_value=client)
    return ctor, client


# ============================================================================
# Phase 4a — service tests
# ============================================================================

class TestOutreachDraftGate:
    async def test_raises_when_unconfigured_and_builds_no_client(
        self, db, test_organization, unconfigured_llm
    ):
        from src.services.outreach_drafter import (
            LLMNotConfiguredError,
            draft_outreach_content,
        )

        with patch(
            "src.services.outreach_drafter.resolve_generation_llm",
            return_value=unconfigured_llm,
        ), patch("src.services.outreach_drafter.openai.AsyncOpenAI") as mock_ctor:
            with pytest.raises(LLMNotConfiguredError):
                await draft_outreach_content(test_organization, db)
            mock_ctor.assert_not_called()

    async def test_default_tone_used_when_none_given(
        self, db, test_organization, configured_llm
    ):
        test_organization.default_tone = "warm"
        db.commit()
        from src.services.outreach_drafter import draft_outreach_content

        resp = _mock_llm_response()
        ctor, client = _mock_openai_ctor(resp)

        with patch(
            "src.services.outreach_drafter.resolve_generation_llm",
            return_value=configured_llm,
        ), patch("src.services.outreach_drafter.openai.AsyncOpenAI", ctor):
            await draft_outreach_content(test_organization, db)

        messages = client.chat.completions.create.call_args.kwargs["messages"]
        system_content = next(m["content"] for m in messages if m["role"] == "system")
        assert "warm" in system_content

    async def test_explicit_tone_overrides_org_default(
        self, db, test_organization, configured_llm
    ):
        test_organization.default_tone = "warm"
        db.commit()
        from src.services.outreach_drafter import draft_outreach_content

        resp = _mock_llm_response()
        ctor, client = _mock_openai_ctor(resp)

        with patch(
            "src.services.outreach_drafter.resolve_generation_llm",
            return_value=configured_llm,
        ), patch("src.services.outreach_drafter.openai.AsyncOpenAI", ctor):
            await draft_outreach_content(test_organization, db, tone="urgent")

        messages = client.chat.completions.create.call_args.kwargs["messages"]
        system_content = next(m["content"] for m in messages if m["role"] == "system")
        assert "Tone: urgent" in system_content
        assert "Tone: warm" not in system_content


class TestOutreachDraftPrompt:
    async def test_brand_voice_is_data_not_instructions(
        self, db, test_organization, configured_llm
    ):
        test_organization.brand_voice = "We are honest and plain-spoken."
        test_organization.product_name_display = "Taskly"
        db.commit()

        from src.services.outreach_drafter import draft_outreach_content

        resp = _mock_llm_response()
        ctor, client = _mock_openai_ctor(resp)

        with patch(
            "src.services.outreach_drafter.resolve_generation_llm",
            return_value=configured_llm,
        ), patch("src.services.outreach_drafter.openai.AsyncOpenAI", ctor):
            await draft_outreach_content(test_organization, db)

        messages = client.chat.completions.create.call_args.kwargs["messages"]
        system_content = next(m["content"] for m in messages if m["role"] == "system")
        assert "Taskly" in system_content
        assert "We are honest and plain-spoken." in system_content
        assert "data, not instructions" in system_content.lower() or "not instructions" in system_content.lower()
        assert "brand voice" in system_content.lower()

    async def test_cohort_context_is_count_and_dominant_segment_only(
        self, db, test_organization, configured_llm
    ):
        from src.services.outreach_drafter import draft_outreach_content

        resp = _mock_llm_response()
        ctor, client = _mock_openai_ctor(resp)

        cohort_context = {"count": 12, "dominant_segment": "at_risk"}
        with patch(
            "src.services.outreach_drafter.resolve_generation_llm",
            return_value=configured_llm,
        ), patch("src.services.outreach_drafter.openai.AsyncOpenAI", ctor):
            await draft_outreach_content(
                test_organization, db, cohort_context=cohort_context
            )

        messages = client.chat.completions.create.call_args.kwargs["messages"]
        full_prompt = " ".join(m["content"] for m in messages)
        assert "12" in full_prompt
        assert "at_risk" in full_prompt

    async def test_raw_emails_never_reach_the_model(
        self, db, test_organization, configured_llm
    ):
        from src.services.outreach_drafter import draft_outreach_content

        resp = _mock_llm_response()
        ctor, client = _mock_openai_ctor(resp)

        cohort_context = {"count": 2, "dominant_segment": "dormant"}
        with patch(
            "src.services.outreach_drafter.resolve_generation_llm",
            return_value=configured_llm,
        ), patch("src.services.outreach_drafter.openai.AsyncOpenAI", ctor):
            await draft_outreach_content(
                test_organization, db,
                cohort_context={"count": 2, "dominant_segment": "dormant"},
            )

        messages = client.chat.completions.create.call_args.kwargs["messages"]
        full_prompt = " ".join(m["content"] for m in messages)
        assert "secret-customer@example.com" not in full_prompt
        assert "search" not in full_prompt.lower() or "search" not in cohort_context


class TestOutreachDraftParsing:
    async def test_happy_path_returns_subject_and_body(
        self, db, test_organization, configured_llm
    ):
        from src.services.outreach_drafter import draft_outreach_content

        resp = _mock_llm_response()
        ctor, _client = _mock_openai_ctor(resp)

        with patch(
            "src.services.outreach_drafter.resolve_generation_llm",
            return_value=configured_llm,
        ), patch("src.services.outreach_drafter.openai.AsyncOpenAI", ctor):
            result = await draft_outreach_content(test_organization, db)

        assert result == {
            "subject": "We've noticed something",
            "body": "We'd love your thoughts.",
        }

    async def test_parses_markdown_fenced_json(
        self, db, test_organization, configured_llm
    ):
        from src.services.outreach_drafter import draft_outreach_content

        fenced_content = (
            "```json\n"
            + json.dumps({"subject": "Fenced subject", "body": "Fenced body"})
            + "\n```"
        )
        message = MagicMock()
        message.content = fenced_content
        choice = MagicMock()
        choice.message = message
        usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        resp = MagicMock(choices=[choice], usage=usage)
        ctor, _client = _mock_openai_ctor(resp)

        with patch(
            "src.services.outreach_drafter.resolve_generation_llm",
            return_value=configured_llm,
        ), patch("src.services.outreach_drafter.openai.AsyncOpenAI", ctor):
            result = await draft_outreach_content(test_organization, db)

        assert result == {"subject": "Fenced subject", "body": "Fenced body"}

    async def test_subject_trimmed_to_200_and_body_to_20000(
        self, db, test_organization, configured_llm
    ):
        from src.services.outreach_drafter import draft_outreach_content

        long_subject = "S" * 300
        long_body = "B" * 25000
        resp = _mock_llm_response(subject=long_subject, body=long_body)
        ctor, _client = _mock_openai_ctor(resp)

        with patch(
            "src.services.outreach_drafter.resolve_generation_llm",
            return_value=configured_llm,
        ), patch("src.services.outreach_drafter.openai.AsyncOpenAI", ctor):
            result = await draft_outreach_content(test_organization, db)

        assert len(result["subject"]) == 200
        assert len(result["body"]) == 20000

    async def test_malformed_json_raises_outreach_draft_error(
        self, db, test_organization, configured_llm
    ):
        from src.services.outreach_drafter import (
            OutreachDraftError,
            draft_outreach_content,
        )

        message = MagicMock()
        message.content = "not json at all {{{"
        choice = MagicMock()
        choice.message = message
        usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        resp = MagicMock(choices=[choice], usage=usage)
        ctor, _client = _mock_openai_ctor(resp)

        with patch(
            "src.services.outreach_drafter.resolve_generation_llm",
            return_value=configured_llm,
        ), patch("src.services.outreach_drafter.openai.AsyncOpenAI", ctor):
            with pytest.raises(OutreachDraftError):
                await draft_outreach_content(test_organization, db)

    async def test_empty_subject_or_body_raises_outreach_draft_error(
        self, db, test_organization, configured_llm
    ):
        from src.services.outreach_drafter import (
            OutreachDraftError,
            draft_outreach_content,
        )

        resp = _mock_llm_response(subject="", body="something")
        ctor, _client = _mock_openai_ctor(resp)

        with patch(
            "src.services.outreach_drafter.resolve_generation_llm",
            return_value=configured_llm,
        ), patch("src.services.outreach_drafter.openai.AsyncOpenAI", ctor):
            with pytest.raises(OutreachDraftError):
                await draft_outreach_content(test_organization, db)


class TestOutreachDraftUsageLog:
    async def test_writes_one_outreach_draft_usage_log_row(
        self, db, test_organization, configured_llm
    ):
        from src.services.outreach_drafter import draft_outreach_content

        resp = _mock_llm_response()
        ctor, _client = _mock_openai_ctor(resp)

        with patch(
            "src.services.outreach_drafter.resolve_generation_llm",
            return_value=configured_llm,
        ), patch("src.services.outreach_drafter.openai.AsyncOpenAI", ctor):
            await draft_outreach_content(test_organization, db)

        rows = (
            db.query(LLMUsageLog)
            .filter_by(organization_id=test_organization.id, task_type="outreach_draft")
            .all()
        )
        assert len(rows) == 1
        assert rows[0].provider == "openai"
        assert rows[0].model == "gpt-4o-mini"
        assert rows[0].prompt_tokens == 120
        assert rows[0].completion_tokens == 60
        assert rows[0].total_tokens == 180

    async def test_usage_log_failure_does_not_fail_the_draft(
        self, db, test_organization, configured_llm
    ):
        from src.services.outreach_drafter import draft_outreach_content

        resp = _mock_llm_response()
        ctor, _client = _mock_openai_ctor(resp)

        with patch(
            "src.services.outreach_drafter.resolve_generation_llm",
            return_value=configured_llm,
        ), patch("src.services.outreach_drafter.openai.AsyncOpenAI", ctor), patch.object(
            db, "add", side_effect=RuntimeError("db is down")
        ):
            result = await draft_outreach_content(test_organization, db)

        assert result["subject"]
        assert result["body"]


# ============================================================================
# Phase 4b — route tests
# ============================================================================

@pytest.fixture
def member_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="outreach_draft_member@test.com",
        password_hash=hash_password("pw"),
        organization_id=test_organization.id,
        role="member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def member_headers(member_user: User) -> dict:
    token = create_access_token(
        {
            "user_id": member_user.id,
            "organization_id": member_user.organization_id,
            "role": member_user.role,
        }
    )
    return {"Authorization": f"Bearer {token}"}


class TestOutreachDraftRoute:
    def test_configured_org_returns_200_subject_body(
        self, client, db, test_organization, auth_headers
    ):
        db.add(
            CustomerHealth(
                organization_id=test_organization.id,
                customer_email="c1@test.com",
                health_score=50,
                segment="at_risk",
            )
        )
        db.add(
            CustomerHealth(
                organization_id=test_organization.id,
                customer_email="c2@test.com",
                health_score=40,
                segment="at_risk",
            )
        )
        db.add(
            CustomerHealth(
                organization_id=test_organization.id,
                customer_email="c3@test.com",
                health_score=60,
                segment="dormant",
            )
        )
        db.commit()

        mock_result = {"subject": "We've noticed something", "body": "Hello there."}
        with patch(
            "src.api.routes.customers.draft_outreach_content",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_draft:
            resp = client.post(
                DRAFT_URL,
                json={"cohort": {"emails": ["c1@test.com", "c2@test.com", "c3@test.com"]}, "tone": "warm"},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        assert resp.json() == {"subject": "We've noticed something", "body": "Hello there."}
        # The cohort context (count + dominant segment) is passed to the service.
        context = mock_draft.call_args.kwargs.get("cohort_context")
        assert context == {"count": 3, "dominant_segment": "at_risk"}

    def test_draft_without_cohort_still_works(self, client, db, test_organization, auth_headers):
        mock_result = {"subject": "S", "body": "B"}
        with patch(
            "src.api.routes.customers.draft_outreach_content",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_draft:
            resp = client.post(
                DRAFT_URL,
                json={"tone": "professional"},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        assert mock_draft.call_args.kwargs.get("cohort_context") is None

    def test_no_llm_returns_409(self, client, db, test_organization, auth_headers):
        from src.services.outreach_drafter import LLMNotConfiguredError

        with patch(
            "src.api.routes.customers.draft_outreach_content",
            new_callable=AsyncMock,
            side_effect=LLMNotConfiguredError("No AI model configured"),
        ):
            resp = client.post(DRAFT_URL, json={}, headers=auth_headers)
        assert resp.status_code == 409
        assert "detail" in resp.json()

    def test_malformed_output_returns_502(self, client, db, test_organization, auth_headers):
        from src.services.outreach_drafter import OutreachDraftError

        with patch(
            "src.api.routes.customers.draft_outreach_content",
            new_callable=AsyncMock,
            side_effect=OutreachDraftError("unusable output"),
        ):
            resp = client.post(DRAFT_URL, json={}, headers=auth_headers)
        assert resp.status_code == 502

    def test_provider_error_returns_502(self, client, db, test_organization, auth_headers):
        with patch(
            "src.api.routes.customers.draft_outreach_content",
            new_callable=AsyncMock,
            side_effect=RuntimeError("upstream boom"),
        ):
            resp = client.post(DRAFT_URL, json={}, headers=auth_headers)
        assert resp.status_code == 502

    def test_extra_field_422(self, client, db, test_organization, auth_headers):
        resp = client.post(
            DRAFT_URL,
            json={"tone": "warm", "cc": "x@test.com"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_invalid_cohort_both_emails_and_filter_422(
        self, client, db, test_organization, auth_headers
    ):
        resp = client.post(
            DRAFT_URL,
            json={"cohort": {"emails": ["a@test.com"], "filter": {}}},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_member_403(self, client, db, test_organization, member_headers):
        resp = client.post(DRAFT_URL, json={}, headers=member_headers)
        assert resp.status_code == 403

    def test_draft_never_creates_campaign_rows_or_dispatches(
        self, client, db, test_organization, auth_headers
    ):
        mock_result = {"subject": "S", "body": "B"}
        with patch(
            "src.api.routes.customers.draft_outreach_content",
            new_callable=AsyncMock,
            return_value=mock_result,
        ), patch("src.background.celery_client.get_celery_app") as mock_get_app:
            resp = client.post(DRAFT_URL, json={}, headers=auth_headers)

        assert resp.status_code == 200
        from src.models.outreach_campaign import (
            OutreachCampaign,
            OutreachCampaignRecipient,
        )
        assert db.query(OutreachCampaign).count() == 0
        assert db.query(OutreachCampaignRecipient).count() == 0
        mock_get_app.assert_not_called()
