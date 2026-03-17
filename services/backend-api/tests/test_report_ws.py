"""
TDD tests for On-Demand AI Reports — Phase 2 (WebSocket Integration, M2.4).

Tests cover:
1. Report intent routes to the report pipeline (not the regular LLM path)
2. Report is saved to the database after generation
3. ConversationMessage with query_type="report" is persisted
4. Plan gating: free/pro users receive an error, not a report
5. Report type extraction from various natural-language queries
6. System report templates are registered in SYSTEM_REPORT_TEMPLATES
"""

import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.user import User
from src.models.organization import Organization
from src.models.conversation import Conversation
from src.api.auth import hash_password, create_access_token


# =============================================================================
# Helpers
# =============================================================================


def _async_generator(items):
    """Build an async generator from a list of items (for mocking call_llm_stream)."""
    async def gen():
        for item in items:
            yield item
    return gen()


def _make_token(user: User) -> str:
    return create_access_token({
        "user_id": user.id,
        "organization_id": user.organization_id,
        "role": user.role,
    })


def _make_headers(user: User) -> dict:
    return {"Authorization": f"Bearer {_make_token(user)}"}


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def business_org(db: Session) -> Organization:
    org = Organization(name="Business WS Corp", plan="business")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def business_user(db: Session, business_org: Organization) -> User:
    user = User(
        email="biz_ws@example.com",
        password_hash=hash_password("password123"),
        organization_id=business_org.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def business_token(business_user: User) -> str:
    return _make_token(business_user)


@pytest.fixture
def free_org(db: Session) -> Organization:
    org = Organization(name="Free WS Org", plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def free_user(db: Session, free_org: Organization) -> User:
    user = User(
        email="free_ws@example.com",
        password_hash=hash_password("password123"),
        organization_id=free_org.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def free_token(free_user: User) -> str:
    return _make_token(free_user)


@pytest.fixture
def pro_org(db: Session) -> Organization:
    org = Organization(name="Pro WS Org", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def pro_user(db: Session, pro_org: Organization) -> User:
    user = User(
        email="pro_ws@example.com",
        password_hash=hash_password("password123"),
        organization_id=pro_org.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def pro_token(pro_user: User) -> str:
    return _make_token(pro_user)


@pytest.fixture
def biz_conversation_id(client: TestClient, business_token: str) -> str:
    """Create a conversation for the business user and return its public_id."""
    headers = {"Authorization": f"Bearer {business_token}"}
    r = client.post("/api/v1/conversations", json={"title": "Report Test"}, headers=headers)
    assert r.status_code == 201, f"Failed to create conversation: {r.text}"
    return r.json()["public_id"]


@pytest.fixture
def free_conversation_id(client: TestClient, free_token: str) -> str:
    """Create a conversation for the free user."""
    headers = {"Authorization": f"Bearer {free_token}"}
    r = client.post("/api/v1/conversations", json={"title": "Free Test"}, headers=headers)
    assert r.status_code == 201
    return r.json()["public_id"]


@pytest.fixture
def pro_conversation_id(client: TestClient, pro_token: str) -> str:
    """Create a conversation for the pro user."""
    headers = {"Authorization": f"Bearer {pro_token}"}
    r = client.post("/api/v1/conversations", json={"title": "Pro Test"}, headers=headers)
    assert r.status_code == 201
    return r.json()["public_id"]


# =============================================================================
# 1. Report intent routes to the report pipeline
# =============================================================================


class TestReportIntentTriggersPipeline:
    """
    When the intent classifier returns 'report', the WebSocket handler must
    call ReportGenerator.generate() rather than the regular SQL/LLM pipeline.
    """

    def test_report_intent_triggers_report_pipeline(
        self,
        client: TestClient,
        business_token: str,
        biz_conversation_id: str,
    ):
        """
        A 'report' intent must invoke ReportGenerator.generate, not
        the regular data/analysis SQL pipeline.
        """
        llm_chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content="Overview section narrative."))])
        ]

        mock_report_result = {
            "title": "Executive Summary — Feb 16 to Mar 17, 2026",
            "sections": [
                {
                    "heading": "Overview",
                    "narrative": "",
                    "data": {"type": "table", "columns": ["Metric", "Value"], "rows": [["Total Feedback", 5]]},
                    "chart": None,
                }
            ],
        }

        mock_generate = MagicMock(return_value=mock_report_result)

        with patch(
            "src.api.routes.copilot_ws.IntentClassifier.classify",
            return_value={"intent": "report", "confidence": 0.95, "parameters": {}},
        ), patch(
            "src.api.routes.copilot_ws.ReportGenerator.generate",
            mock_generate,
        ), patch(
            "src.api.routes.copilot_ws.call_llm_stream",
            side_effect=lambda **kwargs: _async_generator(llm_chunks),
        ):
            with client.websocket_connect(f"/ws/copilot?token={business_token}") as ws:
                ws.send_json({
                    "type": "query",
                    "conversation_id": biz_conversation_id,
                    "content": "Generate an executive summary for this month",
                    "context_scope": "all_data",
                    "message_id": "report-test-1",
                })

                # Collect messages until we see report_complete or an error
                messages = []
                for _ in range(30):
                    try:
                        msg = ws.receive_json()
                        messages.append(msg)
                        if msg.get("type") in ("report_complete", "error"):
                            break
                    except Exception:
                        break

        msg_types = [m["type"] for m in messages]
        assert "report_complete" in msg_types, (
            f"Expected 'report_complete' message, got: {msg_types}"
        )
        mock_generate.assert_called_once()

    def test_report_intent_does_not_call_sql_generator(
        self,
        client: TestClient,
        business_token: str,
        biz_conversation_id: str,
    ):
        """
        For a 'report' intent, SQLGenerator must NOT be called.
        """
        llm_chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content="narrative"))])
        ]

        mock_report_result = {
            "title": "Test Report",
            "sections": [
                {
                    "heading": "Overview",
                    "narrative": "",
                    "data": {"type": "table", "columns": [], "rows": []},
                    "chart": None,
                }
            ],
        }

        with patch(
            "src.api.routes.copilot_ws.IntentClassifier.classify",
            return_value={"intent": "report", "confidence": 0.95, "parameters": {}},
        ), patch(
            "src.api.routes.copilot_ws.ReportGenerator.generate",
            return_value=mock_report_result,
        ), patch(
            "src.api.routes.copilot_ws.call_llm_stream",
            side_effect=lambda **kwargs: _async_generator(llm_chunks),
        ), patch(
            "src.api.routes.copilot_ws.SQLGenerator",
        ) as mock_sql_gen:
            with client.websocket_connect(f"/ws/copilot?token={business_token}") as ws:
                ws.send_json({
                    "type": "query",
                    "conversation_id": biz_conversation_id,
                    "content": "Executive summary this month",
                    "context_scope": "all_data",
                    "message_id": "report-sql-test",
                })

                for _ in range(20):
                    try:
                        msg = ws.receive_json()
                        if msg.get("type") in ("report_complete", "error"):
                            break
                    except Exception:
                        break

        mock_sql_gen.assert_not_called()

    def test_report_section_messages_sent(
        self,
        client: TestClient,
        business_token: str,
        biz_conversation_id: str,
    ):
        """
        Each report section must produce a 'report_section' WebSocket message.
        """
        llm_chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content="section text"))])
        ]

        mock_report_result = {
            "title": "Executive Summary",
            "sections": [
                {
                    "heading": "Overview",
                    "narrative": "",
                    "data": {"type": "table", "columns": ["Metric", "Value"], "rows": []},
                    "chart": None,
                },
                {
                    "heading": "Sentiment Analysis",
                    "narrative": "",
                    "data": {"type": "table", "columns": ["Sentiment", "Count"], "rows": []},
                    "chart": {"type": "pie", "data": []},
                },
            ],
        }

        with patch(
            "src.api.routes.copilot_ws.IntentClassifier.classify",
            return_value={"intent": "report", "confidence": 0.95, "parameters": {}},
        ), patch(
            "src.api.routes.copilot_ws.ReportGenerator.generate",
            return_value=mock_report_result,
        ), patch(
            "src.api.routes.copilot_ws.call_llm_stream",
            side_effect=lambda **kwargs: _async_generator(llm_chunks),
        ):
            with client.websocket_connect(f"/ws/copilot?token={business_token}") as ws:
                ws.send_json({
                    "type": "query",
                    "conversation_id": biz_conversation_id,
                    "content": "Generate executive summary",
                    "context_scope": "all_data",
                    "message_id": "report-sections-test",
                })

                messages = []
                for _ in range(40):
                    try:
                        msg = ws.receive_json()
                        messages.append(msg)
                        if msg.get("type") in ("report_complete", "error"):
                            break
                    except Exception:
                        break

        section_msgs = [m for m in messages if m.get("type") == "report_section"]
        assert len(section_msgs) == 2, (
            f"Expected 2 report_section messages, got {len(section_msgs)}. "
            f"All message types: {[m['type'] for m in messages]}"
        )

    def test_report_section_message_has_required_fields(
        self,
        client: TestClient,
        business_token: str,
        biz_conversation_id: str,
    ):
        """
        Each 'report_section' message must carry: section_index, section,
        total_sections, done, report_id, message_id.
        """
        llm_chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content="narrative text"))])
        ]

        mock_report_result = {
            "title": "Executive Summary",
            "sections": [
                {
                    "heading": "Overview",
                    "narrative": "",
                    "data": {"type": "table", "columns": [], "rows": []},
                    "chart": None,
                }
            ],
        }

        with patch(
            "src.api.routes.copilot_ws.IntentClassifier.classify",
            return_value={"intent": "report", "confidence": 0.95, "parameters": {}},
        ), patch(
            "src.api.routes.copilot_ws.ReportGenerator.generate",
            return_value=mock_report_result,
        ), patch(
            "src.api.routes.copilot_ws.call_llm_stream",
            side_effect=lambda **kwargs: _async_generator(llm_chunks),
        ):
            with client.websocket_connect(f"/ws/copilot?token={business_token}") as ws:
                ws.send_json({
                    "type": "query",
                    "conversation_id": biz_conversation_id,
                    "content": "Generate executive summary",
                    "context_scope": "all_data",
                    "message_id": "report-fields-test",
                })

                messages = []
                for _ in range(30):
                    try:
                        msg = ws.receive_json()
                        messages.append(msg)
                        if msg.get("type") in ("report_complete", "error"):
                            break
                    except Exception:
                        break

        section_msgs = [m for m in messages if m.get("type") == "report_section"]
        assert section_msgs, "No report_section messages received"
        sec = section_msgs[0]
        for field in ("section_index", "section", "total_sections", "message_id"):
            assert field in sec, f"Missing field '{field}' in report_section message: {sec}"

    def test_report_complete_message_has_required_fields(
        self,
        client: TestClient,
        business_token: str,
        biz_conversation_id: str,
    ):
        """
        The 'report_complete' message must carry: report_id, title, total_sections.
        """
        llm_chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content="done"))])
        ]

        mock_report_result = {
            "title": "Executive Summary — Test",
            "sections": [
                {
                    "heading": "Overview",
                    "narrative": "",
                    "data": {"type": "table", "columns": [], "rows": []},
                    "chart": None,
                }
            ],
        }

        with patch(
            "src.api.routes.copilot_ws.IntentClassifier.classify",
            return_value={"intent": "report", "confidence": 0.95, "parameters": {}},
        ), patch(
            "src.api.routes.copilot_ws.ReportGenerator.generate",
            return_value=mock_report_result,
        ), patch(
            "src.api.routes.copilot_ws.call_llm_stream",
            side_effect=lambda **kwargs: _async_generator(llm_chunks),
        ):
            with client.websocket_connect(f"/ws/copilot?token={business_token}") as ws:
                ws.send_json({
                    "type": "query",
                    "conversation_id": biz_conversation_id,
                    "content": "Generate executive summary",
                    "context_scope": "all_data",
                    "message_id": "report-complete-fields",
                })

                complete_msg = None
                for _ in range(30):
                    try:
                        msg = ws.receive_json()
                        if msg.get("type") == "report_complete":
                            complete_msg = msg
                            break
                        if msg.get("type") == "error":
                            break
                    except Exception:
                        break

        assert complete_msg is not None, "No report_complete message received"
        for field in ("report_id", "title", "total_sections"):
            assert field in complete_msg, (
                f"Missing field '{field}' in report_complete: {complete_msg}"
            )
        assert complete_msg["title"] == "Executive Summary — Test"
        assert complete_msg["total_sections"] == 1


# =============================================================================
# 2. Report is saved to the DB
# =============================================================================


class TestReportSavesToDb:
    """After generation, a Report record must exist in the database."""

    def test_report_saves_to_db(
        self,
        client: TestClient,
        db: Session,
        business_token: str,
        biz_conversation_id: str,
        business_user: User,
    ):
        """
        After a successful report generation, a Report row with the correct
        org_id, report_type, and date_range_days must exist.
        """
        from src.models.report import Report

        llm_chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content="test narrative"))])
        ]
        mock_report_result = {
            "title": "Executive Summary — Test",
            "sections": [
                {
                    "heading": "Overview",
                    "narrative": "",
                    "data": {"type": "table", "columns": [], "rows": []},
                    "chart": None,
                }
            ],
        }

        with patch(
            "src.api.routes.copilot_ws.IntentClassifier.classify",
            return_value={"intent": "report", "confidence": 0.95, "parameters": {}},
        ), patch(
            "src.api.routes.copilot_ws.ReportGenerator.generate",
            return_value=mock_report_result,
        ), patch(
            "src.api.routes.copilot_ws.call_llm_stream",
            side_effect=lambda **kwargs: _async_generator(llm_chunks),
        ):
            with client.websocket_connect(f"/ws/copilot?token={business_token}") as ws:
                ws.send_json({
                    "type": "query",
                    "conversation_id": biz_conversation_id,
                    "content": "Generate an executive summary for this month",
                    "context_scope": "all_data",
                    "message_id": "db-save-test",
                })

                for _ in range(30):
                    try:
                        msg = ws.receive_json()
                        if msg.get("type") in ("report_complete", "error"):
                            break
                    except Exception:
                        break

        report = db.query(Report).filter_by(organization_id=business_user.organization_id).first()
        assert report is not None, "Report was not saved to the database"
        assert report.report_type == "executive_summary"
        assert report.date_range_days == 30
        assert report.title == "Executive Summary — Test"

    def test_report_sections_saved_to_db(
        self,
        client: TestClient,
        db: Session,
        business_token: str,
        biz_conversation_id: str,
        business_user: User,
    ):
        """
        The saved Report must have sections containing the generated narratives.
        """
        from src.models.report import Report

        llm_chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content="Generated narrative text."))])
        ]
        mock_report_result = {
            "title": "Test Report",
            "sections": [
                {
                    "heading": "Overview",
                    "narrative": "",
                    "data": {"type": "table", "columns": [], "rows": []},
                    "chart": None,
                }
            ],
        }

        with patch(
            "src.api.routes.copilot_ws.IntentClassifier.classify",
            return_value={"intent": "report", "confidence": 0.95, "parameters": {}},
        ), patch(
            "src.api.routes.copilot_ws.ReportGenerator.generate",
            return_value=mock_report_result,
        ), patch(
            "src.api.routes.copilot_ws.call_llm_stream",
            side_effect=lambda **kwargs: _async_generator(llm_chunks),
        ):
            with client.websocket_connect(f"/ws/copilot?token={business_token}") as ws:
                ws.send_json({
                    "type": "query",
                    "conversation_id": biz_conversation_id,
                    "content": "Executive summary",
                    "context_scope": "all_data",
                    "message_id": "sections-save-test",
                })

                for _ in range(30):
                    try:
                        msg = ws.receive_json()
                        if msg.get("type") in ("report_complete", "error"):
                            break
                    except Exception:
                        break

        report = db.query(Report).filter_by(organization_id=business_user.organization_id).first()
        assert report is not None
        assert report.sections is not None
        assert isinstance(report.sections, list)
        assert len(report.sections) == 1
        # The narrative should have been filled in by the LLM stream
        assert report.sections[0]["heading"] == "Overview"
        assert "Generated narrative text." in report.sections[0]["narrative"]

    def test_report_conversation_id_linked(
        self,
        client: TestClient,
        db: Session,
        business_token: str,
        biz_conversation_id: str,
        business_user: User,
    ):
        """
        The saved Report should reference the conversation it was generated in.
        """
        from src.models.report import Report

        llm_chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content="text"))])
        ]
        mock_report_result = {
            "title": "Test",
            "sections": [
                {
                    "heading": "Overview",
                    "narrative": "",
                    "data": {"type": "table", "columns": [], "rows": []},
                    "chart": None,
                }
            ],
        }

        with patch(
            "src.api.routes.copilot_ws.IntentClassifier.classify",
            return_value={"intent": "report", "confidence": 0.95, "parameters": {}},
        ), patch(
            "src.api.routes.copilot_ws.ReportGenerator.generate",
            return_value=mock_report_result,
        ), patch(
            "src.api.routes.copilot_ws.call_llm_stream",
            side_effect=lambda **kwargs: _async_generator(llm_chunks),
        ):
            with client.websocket_connect(f"/ws/copilot?token={business_token}") as ws:
                ws.send_json({
                    "type": "query",
                    "conversation_id": biz_conversation_id,
                    "content": "Executive summary",
                    "context_scope": "all_data",
                    "message_id": "conv-link-test",
                })

                for _ in range(30):
                    try:
                        msg = ws.receive_json()
                        if msg.get("type") in ("report_complete", "error"):
                            break
                    except Exception:
                        break

        report = db.query(Report).filter_by(organization_id=business_user.organization_id).first()
        assert report is not None
        # conversation_id must be set (not None)
        assert report.conversation_id is not None


# =============================================================================
# 3. ConversationMessage with query_type="report"
# =============================================================================


class TestReportConversationMessage:
    """After generation, a ConversationMessage with query_type='report' must exist."""

    def test_report_creates_conversation_message(
        self,
        client: TestClient,
        db: Session,
        business_token: str,
        biz_conversation_id: str,
    ):
        """
        A ConversationMessage with role='assistant' and query_type='report'
        must be persisted after report generation.
        """
        from src.models.conversation_message import ConversationMessage

        llm_chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content="report narrative"))])
        ]
        mock_report_result = {
            "title": "Executive Summary",
            "sections": [
                {
                    "heading": "Overview",
                    "narrative": "",
                    "data": {"type": "table", "columns": [], "rows": []},
                    "chart": None,
                }
            ],
        }

        with patch(
            "src.api.routes.copilot_ws.IntentClassifier.classify",
            return_value={"intent": "report", "confidence": 0.95, "parameters": {}},
        ), patch(
            "src.api.routes.copilot_ws.ReportGenerator.generate",
            return_value=mock_report_result,
        ), patch(
            "src.api.routes.copilot_ws.call_llm_stream",
            side_effect=lambda **kwargs: _async_generator(llm_chunks),
        ):
            with client.websocket_connect(f"/ws/copilot?token={business_token}") as ws:
                ws.send_json({
                    "type": "query",
                    "conversation_id": biz_conversation_id,
                    "content": "Generate a report",
                    "context_scope": "all_data",
                    "message_id": "msg-persist-test",
                })

                for _ in range(30):
                    try:
                        msg = ws.receive_json()
                        if msg.get("type") in ("report_complete", "error"):
                            break
                    except Exception:
                        break

        # Look up the conversation by its public_id to get the DB id
        conv = db.query(Conversation).filter_by(public_id=biz_conversation_id).first()
        assert conv is not None

        assistant_msgs = (
            db.query(ConversationMessage)
            .filter_by(conversation_id=conv.id, role="assistant")
            .all()
        )
        assert len(assistant_msgs) >= 1, "No assistant ConversationMessage found"

        report_msgs = [m for m in assistant_msgs if m.query_type == "report"]
        assert len(report_msgs) >= 1, (
            f"Expected ConversationMessage with query_type='report', "
            f"found query_types: {[m.query_type for m in assistant_msgs]}"
        )

    def test_report_user_message_also_persisted(
        self,
        client: TestClient,
        db: Session,
        business_token: str,
        biz_conversation_id: str,
    ):
        """
        The user message that triggered the report must also be stored.
        """
        from src.models.conversation_message import ConversationMessage

        llm_chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content="text"))])
        ]
        mock_report_result = {
            "title": "Test",
            "sections": [
                {
                    "heading": "Overview",
                    "narrative": "",
                    "data": {"type": "table", "columns": [], "rows": []},
                    "chart": None,
                }
            ],
        }

        with patch(
            "src.api.routes.copilot_ws.IntentClassifier.classify",
            return_value={"intent": "report", "confidence": 0.95, "parameters": {}},
        ), patch(
            "src.api.routes.copilot_ws.ReportGenerator.generate",
            return_value=mock_report_result,
        ), patch(
            "src.api.routes.copilot_ws.call_llm_stream",
            side_effect=lambda **kwargs: _async_generator(llm_chunks),
        ):
            with client.websocket_connect(f"/ws/copilot?token={business_token}") as ws:
                ws.send_json({
                    "type": "query",
                    "conversation_id": biz_conversation_id,
                    "content": "Generate an executive summary",
                    "context_scope": "all_data",
                    "message_id": "user-msg-test",
                })

                for _ in range(30):
                    try:
                        msg = ws.receive_json()
                        if msg.get("type") in ("report_complete", "error"):
                            break
                    except Exception:
                        break

        conv = db.query(Conversation).filter_by(public_id=biz_conversation_id).first()
        user_msgs = (
            db.query(ConversationMessage)
            .filter_by(conversation_id=conv.id, role="user")
            .all()
        )
        assert len(user_msgs) >= 1, "User message was not persisted"
        assert any("executive summary" in m.content.lower() for m in user_msgs)


# =============================================================================
# 4. Plan gating
# =============================================================================


class TestReportPlanGating:
    """Free and Pro users must NOT generate reports — they get an error message."""

    def _run_report_query(self, client, token, conversation_id, message_id="plan-gate-test"):
        """Helper: send a report-intent query and collect all messages."""
        messages = []
        with patch(
            "src.api.routes.copilot_ws.IntentClassifier.classify",
            return_value={"intent": "report", "confidence": 0.95, "parameters": {}},
        ):
            with client.websocket_connect(f"/ws/copilot?token={token}") as ws:
                ws.send_json({
                    "type": "query",
                    "conversation_id": conversation_id,
                    "content": "Generate an executive summary",
                    "context_scope": "all_data",
                    "message_id": message_id,
                })

                for _ in range(20):
                    try:
                        msg = ws.receive_json()
                        messages.append(msg)
                        # Stop on error, report_complete, or stream done
                        if msg.get("type") == "error":
                            break
                        if msg.get("type") == "report_complete":
                            break
                        if msg.get("type") == "stream" and msg.get("done"):
                            break
                    except Exception:
                        break
        return messages

    def test_report_plan_gating_free_user_gets_error(
        self,
        client: TestClient,
        free_token: str,
        free_conversation_id: str,
    ):
        """
        Free users who trigger a report intent must receive an error message
        (not a report_complete or report_section message).
        """
        messages = self._run_report_query(client, free_token, free_conversation_id, "free-gate-test")
        msg_types = [m["type"] for m in messages]

        assert "report_complete" not in msg_types, (
            "Free user should not receive report_complete"
        )
        assert "report_section" not in msg_types, (
            "Free user should not receive report_section"
        )
        # Should receive either a stream with an upgrade message, or an error
        has_error_or_stream = (
            "error" in msg_types or "stream" in msg_types
        )
        assert has_error_or_stream, f"Expected error or stream response, got: {msg_types}"

    def test_report_plan_gating_pro_user_gets_error(
        self,
        client: TestClient,
        pro_token: str,
        pro_conversation_id: str,
    ):
        """
        Pro users who trigger a report intent must not receive a report.
        """
        messages = self._run_report_query(client, pro_token, pro_conversation_id, "pro-gate-test")
        msg_types = [m["type"] for m in messages]

        assert "report_complete" not in msg_types, (
            "Pro user should not receive report_complete"
        )
        assert "report_section" not in msg_types, (
            "Pro user should not receive report_section"
        )

    def test_report_plan_gating_free_response_mentions_business(
        self,
        client: TestClient,
        free_token: str,
        free_conversation_id: str,
    ):
        """
        The gating response for a free user must mention Business or upgrade.
        """
        messages = self._run_report_query(client, free_token, free_conversation_id, "free-msg-test")

        full_text = ""
        for msg in messages:
            if msg.get("type") == "stream":
                full_text += msg.get("delta", "")
            elif msg.get("type") == "error":
                full_text += msg.get("error", "")

        lower_text = full_text.lower()
        assert any(word in lower_text for word in ("business", "upgrade", "plan")), (
            f"Expected upgrade message mentioning 'business'/'upgrade'/'plan', got: {full_text!r}"
        )

    def test_report_plan_gating_business_user_can_generate(
        self,
        client: TestClient,
        business_token: str,
        biz_conversation_id: str,
    ):
        """
        Business users must be allowed to generate reports.
        """
        llm_chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content="narrative"))])
        ]
        mock_report_result = {
            "title": "Test Report",
            "sections": [
                {
                    "heading": "Overview",
                    "narrative": "",
                    "data": {"type": "table", "columns": [], "rows": []},
                    "chart": None,
                }
            ],
        }

        with patch(
            "src.api.routes.copilot_ws.IntentClassifier.classify",
            return_value={"intent": "report", "confidence": 0.95, "parameters": {}},
        ), patch(
            "src.api.routes.copilot_ws.ReportGenerator.generate",
            return_value=mock_report_result,
        ), patch(
            "src.api.routes.copilot_ws.call_llm_stream",
            side_effect=lambda **kwargs: _async_generator(llm_chunks),
        ):
            messages = self._run_report_query(
                client, business_token, biz_conversation_id, "biz-allowed-test"
            )

        msg_types = [m["type"] for m in messages]
        assert "report_complete" in msg_types, (
            f"Business user should receive report_complete, got: {msg_types}"
        )

    def test_report_plan_gating_does_not_call_generator_for_free(
        self,
        client: TestClient,
        free_token: str,
        free_conversation_id: str,
    ):
        """
        ReportGenerator.generate must NOT be called for a free user.
        """
        with patch(
            "src.api.routes.copilot_ws.IntentClassifier.classify",
            return_value={"intent": "report", "confidence": 0.95, "parameters": {}},
        ), patch(
            "src.api.routes.copilot_ws.ReportGenerator.generate",
        ) as mock_gen:
            with client.websocket_connect(f"/ws/copilot?token={free_token}") as ws:
                ws.send_json({
                    "type": "query",
                    "conversation_id": free_conversation_id,
                    "content": "Generate an executive summary",
                    "context_scope": "all_data",
                    "message_id": "free-no-gen",
                })

                for _ in range(20):
                    try:
                        msg = ws.receive_json()
                        if msg.get("type") in ("error", "report_complete"):
                            break
                        if msg.get("type") == "stream" and msg.get("done"):
                            break
                    except Exception:
                        break

        mock_gen.assert_not_called()


# =============================================================================
# 5. Report type extraction from query
# =============================================================================


class TestReportTypeExtractionFromQuery:
    """
    Verify that ReportGenerator.extract_report_type() correctly identifies
    the report type from a variety of natural-language queries.
    """

    @pytest.fixture(autouse=True)
    def generator(self):
        from src.services.copilot.report_generator import ReportGenerator
        self.gen = ReportGenerator()

    def test_executive_summary_from_executive_keyword(self):
        assert self.gen.extract_report_type("Generate an executive summary") == "executive_summary"

    def test_executive_summary_from_summary_keyword(self):
        assert self.gen.extract_report_type("Give me a monthly summary") == "executive_summary"

    def test_executive_summary_from_overview_keyword(self):
        assert self.gen.extract_report_type("Show me an overview for last 30 days") == "executive_summary"

    def test_executive_summary_this_month(self):
        assert self.gen.extract_report_type("Executive summary this month") == "executive_summary"

    def test_customer_health_from_health_report(self):
        assert self.gen.extract_report_type("Customer health report") == "customer_health"

    def test_customer_health_from_health_keyword(self):
        assert self.gen.extract_report_type("Generate a health report") == "customer_health"

    def test_customer_health_from_health_score(self):
        assert self.gen.extract_report_type("Show me health score breakdown") == "customer_health"

    def test_feature_prioritization_from_feature_requests(self):
        assert self.gen.extract_report_type("Feature request priorities") == "feature_prioritization"

    def test_feature_prioritization_from_prioritize(self):
        assert self.gen.extract_report_type("Prioritize my feature requests") == "feature_prioritization"

    def test_feature_prioritization_from_feature_keyword(self):
        assert self.gen.extract_report_type("Show me feature prioritization") == "feature_prioritization"

    def test_churn_risk_from_churn(self):
        assert self.gen.extract_report_type("Churn risk analysis for this month") == "churn_risk"

    def test_churn_risk_from_attrition(self):
        assert self.gen.extract_report_type("Show attrition analysis") == "churn_risk"

    def test_churn_risk_analysis_keyword(self):
        assert self.gen.extract_report_type("Risk analysis of churning customers") == "churn_risk"

    def test_default_to_executive_summary_for_bare_report(self):
        """'Generate a report' with no type hint defaults to executive_summary."""
        assert self.gen.extract_report_type("Generate a report") == "executive_summary"

    def test_case_insensitive_executive(self):
        assert self.gen.extract_report_type("EXECUTIVE SUMMARY PLEASE") == "executive_summary"

    def test_case_insensitive_churn(self):
        assert self.gen.extract_report_type("CHURN RISK ANALYSIS") == "churn_risk"

    def test_churn_takes_priority_over_summary(self):
        """When both 'churn' and 'summary' appear, churn should win."""
        result = self.gen.extract_report_type("Give me a churn summary")
        assert result == "churn_risk"

    def test_health_takes_priority_over_summary(self):
        """When both 'health' and 'summary' appear, health should win."""
        result = self.gen.extract_report_type("Customer health summary report")
        assert result == "customer_health"


# =============================================================================
# 6. System report templates
# =============================================================================


class TestSystemReportTemplates:
    """
    The 4 report quick-start templates must be registered so they can be
    surfaced in the Cmd+K CommandBar (Copilot template chips).
    """

    def test_system_report_templates_importable(self):
        from src.services.copilot.template_saver import SYSTEM_REPORT_TEMPLATES
        assert SYSTEM_REPORT_TEMPLATES is not None

    def test_system_report_templates_has_four_entries(self):
        from src.services.copilot.template_saver import SYSTEM_REPORT_TEMPLATES
        assert len(SYSTEM_REPORT_TEMPLATES) == 4, (
            f"Expected 4 report templates, got {len(SYSTEM_REPORT_TEMPLATES)}"
        )

    def test_system_report_templates_are_list(self):
        from src.services.copilot.template_saver import SYSTEM_REPORT_TEMPLATES
        assert isinstance(SYSTEM_REPORT_TEMPLATES, list)

    def test_each_template_has_label(self):
        from src.services.copilot.template_saver import SYSTEM_REPORT_TEMPLATES
        for tmpl in SYSTEM_REPORT_TEMPLATES:
            assert "label" in tmpl, f"Template missing 'label': {tmpl}"
            assert len(tmpl["label"]) > 0

    def test_each_template_has_report_type(self):
        from src.services.copilot.template_saver import SYSTEM_REPORT_TEMPLATES
        valid_types = {"executive_summary", "customer_health", "feature_prioritization", "churn_risk"}
        for tmpl in SYSTEM_REPORT_TEMPLATES:
            assert "report_type" in tmpl, f"Template missing 'report_type': {tmpl}"
            assert tmpl["report_type"] in valid_types, (
                f"Unknown report_type '{tmpl['report_type']}' in {tmpl}"
            )

    def test_each_template_has_description(self):
        from src.services.copilot.template_saver import SYSTEM_REPORT_TEMPLATES
        for tmpl in SYSTEM_REPORT_TEMPLATES:
            assert "description" in tmpl, f"Template missing 'description': {tmpl}"

    def test_all_four_report_types_covered(self):
        from src.services.copilot.template_saver import SYSTEM_REPORT_TEMPLATES
        covered = {t["report_type"] for t in SYSTEM_REPORT_TEMPLATES}
        required = {"executive_summary", "customer_health", "feature_prioritization", "churn_risk"}
        assert covered == required, (
            f"Not all report types covered. Missing: {required - covered}"
        )

    def test_executive_summary_template_label_contains_expected_words(self):
        from src.services.copilot.template_saver import SYSTEM_REPORT_TEMPLATES
        exec_tmpl = next(
            (t for t in SYSTEM_REPORT_TEMPLATES if t["report_type"] == "executive_summary"),
            None,
        )
        assert exec_tmpl is not None
        label_lower = exec_tmpl["label"].lower()
        assert any(word in label_lower for word in ("executive", "summary")), (
            f"Executive summary template label should mention 'executive' or 'summary': {exec_tmpl['label']}"
        )

    def test_churn_risk_template_label_contains_expected_words(self):
        from src.services.copilot.template_saver import SYSTEM_REPORT_TEMPLATES
        churn_tmpl = next(
            (t for t in SYSTEM_REPORT_TEMPLATES if t["report_type"] == "churn_risk"),
            None,
        )
        assert churn_tmpl is not None
        label_lower = churn_tmpl["label"].lower()
        assert any(word in label_lower for word in ("churn", "risk", "attrition")), (
            f"Churn template label should mention 'churn'/'risk'/'attrition': {churn_tmpl['label']}"
        )

    def test_health_template_label_contains_expected_words(self):
        from src.services.copilot.template_saver import SYSTEM_REPORT_TEMPLATES
        health_tmpl = next(
            (t for t in SYSTEM_REPORT_TEMPLATES if t["report_type"] == "customer_health"),
            None,
        )
        assert health_tmpl is not None
        label_lower = health_tmpl["label"].lower()
        assert any(word in label_lower for word in ("health", "customer")), (
            f"Health template label should mention 'health'/'customer': {health_tmpl['label']}"
        )

    def test_feature_template_label_contains_expected_words(self):
        from src.services.copilot.template_saver import SYSTEM_REPORT_TEMPLATES
        feature_tmpl = next(
            (t for t in SYSTEM_REPORT_TEMPLATES if t["report_type"] == "feature_prioritization"),
            None,
        )
        assert feature_tmpl is not None
        label_lower = feature_tmpl["label"].lower()
        assert any(word in label_lower for word in ("feature", "priorit", "request")), (
            f"Feature template label should mention 'feature'/'priorit'/'request': {feature_tmpl['label']}"
        )
