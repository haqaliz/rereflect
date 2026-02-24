"""
TDD tests for AI Copilot (M2.2) database models.

Tests cover all 6 new tables:
1. conversation_folders
2. conversations
3. conversation_messages
4. query_templates
5. query_template_mappings
6. copilot_schema_whitelist
"""
import pytest
from datetime import datetime
from decimal import Decimal
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User


# ---------------------------------------------------------------------------
# 1. ConversationFolder
# ---------------------------------------------------------------------------
class TestConversationFolderModel:

    def test_importable(self):
        from src.models.conversation_folder import ConversationFolder
        assert ConversationFolder is not None

    def test_exported_from_init(self):
        from src.models import ConversationFolder
        assert ConversationFolder is not None

    def test_table_name(self):
        from src.models.conversation_folder import ConversationFolder
        assert ConversationFolder.__tablename__ == "conversation_folders"

    def test_create_folder(self, db: Session, test_organization: Organization):
        from src.models.conversation_folder import ConversationFolder

        folder = ConversationFolder(
            organization_id=test_organization.id,
            name="General",
            sort_order=0,
        )
        db.add(folder)
        db.commit()
        db.refresh(folder)

        assert folder.id is not None
        assert folder.organization_id == test_organization.id
        assert folder.name == "General"
        assert folder.sort_order == 0
        assert folder.created_at is not None

    def test_created_at_defaults_to_now(self, db: Session, test_organization: Organization):
        from src.models.conversation_folder import ConversationFolder

        before = datetime.utcnow()
        folder = ConversationFolder(
            organization_id=test_organization.id,
            name="Test",
            sort_order=1,
        )
        db.add(folder)
        db.commit()
        db.refresh(folder)
        after = datetime.utcnow()

        assert before <= folder.created_at <= after


# ---------------------------------------------------------------------------
# 2. Conversation
# ---------------------------------------------------------------------------
class TestConversationModel:

    def test_importable(self):
        from src.models.conversation import Conversation
        assert Conversation is not None

    def test_exported_from_init(self):
        from src.models import Conversation
        assert Conversation is not None

    def test_table_name(self):
        from src.models.conversation import Conversation
        assert Conversation.__tablename__ == "conversations"

    def test_create_conversation(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.conversation import Conversation

        conv = Conversation(
            organization_id=test_organization.id,
            created_by_user_id=test_user.id,
            title="How many negative feedbacks?",
            context_scope="all_data",
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)

        assert conv.id is not None
        assert conv.organization_id == test_organization.id
        assert conv.created_by_user_id == test_user.id
        assert conv.title == "How many negative feedbacks?"
        assert conv.folder_id is None
        assert conv.context_scope == "all_data"
        assert conv.is_active is True
        assert conv.created_at is not None
        assert conv.updated_at is not None

    def test_conversation_with_folder(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.conversation import Conversation
        from src.models.conversation_folder import ConversationFolder

        folder = ConversationFolder(
            organization_id=test_organization.id,
            name="General",
            sort_order=0,
        )
        db.add(folder)
        db.commit()
        db.refresh(folder)

        conv = Conversation(
            organization_id=test_organization.id,
            created_by_user_id=test_user.id,
            title="Weekly summary",
            folder_id=folder.id,
            context_scope="feedbacks",
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)

        assert conv.folder_id == folder.id

    def test_is_active_defaults_to_true(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.conversation import Conversation

        conv = Conversation(
            organization_id=test_organization.id,
            created_by_user_id=test_user.id,
            title="Test",
            context_scope="all_data",
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)

        assert conv.is_active is True

    def test_soft_delete(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.conversation import Conversation

        conv = Conversation(
            organization_id=test_organization.id,
            created_by_user_id=test_user.id,
            title="To be deleted",
            context_scope="all_data",
        )
        db.add(conv)
        db.commit()

        conv.is_active = False
        db.commit()
        db.refresh(conv)

        assert conv.is_active is False


# ---------------------------------------------------------------------------
# 3. ConversationMessage
# ---------------------------------------------------------------------------
class TestConversationMessageModel:

    def test_importable(self):
        from src.models.conversation_message import ConversationMessage
        assert ConversationMessage is not None

    def test_exported_from_init(self):
        from src.models import ConversationMessage
        assert ConversationMessage is not None

    def test_table_name(self):
        from src.models.conversation_message import ConversationMessage
        assert ConversationMessage.__tablename__ == "conversation_messages"

    def test_create_user_message(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.conversation import Conversation
        from src.models.conversation_message import ConversationMessage

        conv = Conversation(
            organization_id=test_organization.id,
            created_by_user_id=test_user.id,
            title="Test conv",
            context_scope="all_data",
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)

        msg = ConversationMessage(
            conversation_id=conv.id,
            role="user",
            content="How many negative feedbacks this week?",
            context_scope="all_data",
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)

        assert msg.id is not None
        assert msg.conversation_id == conv.id
        assert msg.role == "user"
        assert msg.content == "How many negative feedbacks this week?"
        assert msg.context_scope == "all_data"
        assert msg.query_type is None
        assert msg.template_id is None
        assert msg.sql_generated is None
        assert msg.llm_provider is None
        assert msg.llm_model is None
        assert msg.tokens_in is None
        assert msg.tokens_out is None
        assert msg.cost_cents is None
        assert msg.latency_ms is None
        assert msg.is_regenerated is False
        assert msg.created_at is not None

    def test_create_assistant_message_with_metadata(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.conversation import Conversation
        from src.models.conversation_message import ConversationMessage

        conv = Conversation(
            organization_id=test_organization.id,
            created_by_user_id=test_user.id,
            title="Test conv",
            context_scope="all_data",
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)

        msg = ConversationMessage(
            conversation_id=conv.id,
            role="assistant",
            content="Based on your data, there are 47 negative feedbacks this week.",
            structured_data={"columns": ["sentiment", "count"], "rows": [["negative", 47]]},
            context_scope="feedbacks",
            query_type="data",
            sql_generated="SELECT sentiment_label, COUNT(*) FROM feedback_items WHERE ...",
            llm_provider="openai",
            llm_model="gpt-4o",
            tokens_in=1250,
            tokens_out=340,
            cost_cents=Decimal("2.4000"),
            latency_ms=1830,
            raw_request={"model": "gpt-4o", "messages": []},
            raw_response={"id": "chatcmpl-123"},
            is_regenerated=False,
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)

        assert msg.role == "assistant"
        assert msg.structured_data is not None
        assert msg.query_type == "data"
        assert msg.sql_generated is not None
        assert msg.llm_provider == "openai"
        assert msg.llm_model == "gpt-4o"
        assert msg.tokens_in == 1250
        assert msg.tokens_out == 340
        assert msg.latency_ms == 1830
        assert msg.raw_request is not None
        assert msg.raw_response is not None

    def test_is_regenerated_defaults_to_false(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.conversation import Conversation
        from src.models.conversation_message import ConversationMessage

        conv = Conversation(
            organization_id=test_organization.id,
            created_by_user_id=test_user.id,
            title="Test",
            context_scope="all_data",
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)

        msg = ConversationMessage(
            conversation_id=conv.id,
            role="user",
            content="Test",
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)

        assert msg.is_regenerated is False


# ---------------------------------------------------------------------------
# 4. QueryTemplate
# ---------------------------------------------------------------------------
class TestQueryTemplateModel:

    def test_importable(self):
        from src.models.query_template import QueryTemplate
        assert QueryTemplate is not None

    def test_exported_from_init(self):
        from src.models import QueryTemplate
        assert QueryTemplate is not None

    def test_table_name(self):
        from src.models.query_template import QueryTemplate
        assert QueryTemplate.__tablename__ == "query_templates"

    def test_create_system_template(self, db: Session):
        from src.models.query_template import QueryTemplate

        tmpl = QueryTemplate(
            organization_id=None,
            sql_query="SELECT sentiment_label, COUNT(*) FROM feedback_items WHERE organization_id = :org_id GROUP BY sentiment_label",
            description="Count feedbacks by sentiment",
            parameter_schema={"org_id": "integer"},
            created_by="system",
        )
        db.add(tmpl)
        db.commit()
        db.refresh(tmpl)

        assert tmpl.id is not None
        assert tmpl.organization_id is None
        assert tmpl.sql_query is not None
        assert tmpl.description == "Count feedbacks by sentiment"
        assert tmpl.parameter_schema is not None
        assert tmpl.created_by == "system"
        assert tmpl.usage_count == 0
        assert tmpl.last_used_at is None
        assert tmpl.is_active is True
        assert tmpl.created_at is not None
        assert tmpl.updated_at is not None

    def test_create_org_specific_template(self, db: Session, test_organization: Organization):
        from src.models.query_template import QueryTemplate

        tmpl = QueryTemplate(
            organization_id=test_organization.id,
            sql_query="SELECT * FROM feedback_items WHERE organization_id = :org_id AND is_urgent = true",
            description="Get urgent feedbacks",
            parameter_schema={"org_id": "integer"},
            created_by="llm",
        )
        db.add(tmpl)
        db.commit()
        db.refresh(tmpl)

        assert tmpl.organization_id == test_organization.id
        assert tmpl.created_by == "llm"

    def test_usage_count_defaults_to_zero(self, db: Session):
        from src.models.query_template import QueryTemplate

        tmpl = QueryTemplate(
            sql_query="SELECT 1",
            description="Test",
            created_by="system",
        )
        db.add(tmpl)
        db.commit()
        db.refresh(tmpl)

        assert tmpl.usage_count == 0

    def test_is_active_defaults_to_true(self, db: Session):
        from src.models.query_template import QueryTemplate

        tmpl = QueryTemplate(
            sql_query="SELECT 1",
            description="Test",
            created_by="system",
        )
        db.add(tmpl)
        db.commit()
        db.refresh(tmpl)

        assert tmpl.is_active is True


# ---------------------------------------------------------------------------
# 5. QueryTemplateMapping
# ---------------------------------------------------------------------------
class TestQueryTemplateMappingModel:

    def test_importable(self):
        from src.models.query_template_mapping import QueryTemplateMapping
        assert QueryTemplateMapping is not None

    def test_exported_from_init(self):
        from src.models import QueryTemplateMapping
        assert QueryTemplateMapping is not None

    def test_table_name(self):
        from src.models.query_template_mapping import QueryTemplateMapping
        assert QueryTemplateMapping.__tablename__ == "query_template_mappings"

    def test_create_mapping(self, db: Session):
        from src.models.query_template import QueryTemplate
        from src.models.query_template_mapping import QueryTemplateMapping

        tmpl = QueryTemplate(
            sql_query="SELECT sentiment_label, COUNT(*) FROM feedback_items GROUP BY sentiment_label",
            description="Count by sentiment",
            created_by="system",
        )
        db.add(tmpl)
        db.commit()
        db.refresh(tmpl)

        mapping = QueryTemplateMapping(
            template_id=tmpl.id,
            question_pattern="how many negative feedbacks",
            match_count=0,
        )
        db.add(mapping)
        db.commit()
        db.refresh(mapping)

        assert mapping.id is not None
        assert mapping.template_id == tmpl.id
        assert mapping.question_pattern == "how many negative feedbacks"
        assert mapping.match_count == 0
        assert mapping.created_at is not None

    def test_question_embedding_jsonb_fallback(self, db: Session):
        """question_embedding should accept JSONB data (fallback for pgvector)."""
        from src.models.query_template import QueryTemplate
        from src.models.query_template_mapping import QueryTemplateMapping

        tmpl = QueryTemplate(
            sql_query="SELECT 1",
            description="Test",
            created_by="system",
        )
        db.add(tmpl)
        db.commit()
        db.refresh(tmpl)

        embedding = [0.1] * 10
        mapping = QueryTemplateMapping(
            template_id=tmpl.id,
            question_pattern="test question",
            question_embedding=embedding,
        )
        db.add(mapping)
        db.commit()
        db.refresh(mapping)

        assert mapping.question_embedding is not None

    def test_match_count_defaults_to_zero(self, db: Session):
        from src.models.query_template import QueryTemplate
        from src.models.query_template_mapping import QueryTemplateMapping

        tmpl = QueryTemplate(
            sql_query="SELECT 1",
            description="Test",
            created_by="system",
        )
        db.add(tmpl)
        db.commit()
        db.refresh(tmpl)

        mapping = QueryTemplateMapping(
            template_id=tmpl.id,
            question_pattern="test",
        )
        db.add(mapping)
        db.commit()
        db.refresh(mapping)

        assert mapping.match_count == 0


# ---------------------------------------------------------------------------
# 6. CopilotSchemaWhitelist
# ---------------------------------------------------------------------------
class TestCopilotSchemaWhitelistModel:

    def test_importable(self):
        from src.models.copilot_schema_whitelist import CopilotSchemaWhitelist
        assert CopilotSchemaWhitelist is not None

    def test_exported_from_init(self):
        from src.models import CopilotSchemaWhitelist
        assert CopilotSchemaWhitelist is not None

    def test_table_name(self):
        from src.models.copilot_schema_whitelist import CopilotSchemaWhitelist
        assert CopilotSchemaWhitelist.__tablename__ == "copilot_schema_whitelist"

    def test_create_table_level_entry(self, db: Session):
        from src.models.copilot_schema_whitelist import CopilotSchemaWhitelist

        entry = CopilotSchemaWhitelist(
            table_name="feedback_items",
            column_name=None,
            description="All feedback items submitted by customers",
            is_active=True,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)

        assert entry.id is not None
        assert entry.table_name == "feedback_items"
        assert entry.column_name is None
        assert entry.description is not None
        assert entry.is_active is True

    def test_create_column_level_entry(self, db: Session):
        from src.models.copilot_schema_whitelist import CopilotSchemaWhitelist

        entry = CopilotSchemaWhitelist(
            table_name="feedback_items",
            column_name="sentiment_label",
            description="Sentiment classification: positive, neutral, negative",
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)

        assert entry.table_name == "feedback_items"
        assert entry.column_name == "sentiment_label"

    def test_is_active_defaults_to_true(self, db: Session):
        from src.models.copilot_schema_whitelist import CopilotSchemaWhitelist

        entry = CopilotSchemaWhitelist(
            table_name="customer_health_scores",
            description="Customer health scores",
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)

        assert entry.is_active is True


# ---------------------------------------------------------------------------
# Relationship Tests
# ---------------------------------------------------------------------------
class TestCopilotRelationships:

    def test_conversation_has_messages_relationship(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.conversation import Conversation
        from src.models.conversation_message import ConversationMessage

        conv = Conversation(
            organization_id=test_organization.id,
            created_by_user_id=test_user.id,
            title="Test",
            context_scope="all_data",
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)

        msg1 = ConversationMessage(conversation_id=conv.id, role="user", content="Question 1")
        msg2 = ConversationMessage(conversation_id=conv.id, role="assistant", content="Answer 1")
        db.add_all([msg1, msg2])
        db.commit()
        db.refresh(conv)

        assert hasattr(conv, "messages")
        assert len(conv.messages) == 2

    def test_conversation_folder_relationship(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.conversation import Conversation
        from src.models.conversation_folder import ConversationFolder

        folder = ConversationFolder(organization_id=test_organization.id, name="Research", sort_order=0)
        db.add(folder)
        db.commit()
        db.refresh(folder)

        conv = Conversation(
            organization_id=test_organization.id,
            created_by_user_id=test_user.id,
            title="Test",
            folder_id=folder.id,
            context_scope="all_data",
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)

        assert conv.folder is not None
        assert conv.folder.name == "Research"

    def test_query_template_has_mappings_relationship(self, db: Session):
        from src.models.query_template import QueryTemplate
        from src.models.query_template_mapping import QueryTemplateMapping

        tmpl = QueryTemplate(sql_query="SELECT 1", description="Test", created_by="system")
        db.add(tmpl)
        db.commit()
        db.refresh(tmpl)

        m1 = QueryTemplateMapping(template_id=tmpl.id, question_pattern="how many feedbacks")
        m2 = QueryTemplateMapping(template_id=tmpl.id, question_pattern="total feedback count")
        db.add_all([m1, m2])
        db.commit()
        db.refresh(tmpl)

        assert hasattr(tmpl, "mappings")
        assert len(tmpl.mappings) == 2

    def test_message_template_relationship(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.conversation import Conversation
        from src.models.conversation_message import ConversationMessage
        from src.models.query_template import QueryTemplate

        tmpl = QueryTemplate(sql_query="SELECT 1", description="Test", created_by="system")
        db.add(tmpl)
        db.commit()
        db.refresh(tmpl)

        conv = Conversation(
            organization_id=test_organization.id,
            created_by_user_id=test_user.id,
            title="Test",
            context_scope="all_data",
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)

        msg = ConversationMessage(conversation_id=conv.id, role="assistant", content="Answer", template_id=tmpl.id)
        db.add(msg)
        db.commit()
        db.refresh(msg)

        assert msg.template_id == tmpl.id


# ---------------------------------------------------------------------------
# Index existence tests
# ---------------------------------------------------------------------------
class TestCopilotIndexes:

    def test_conversations_org_date_index(self):
        from src.models.conversation import Conversation
        index_names = [idx.name for idx in Conversation.__table__.indexes]
        assert "ix_conversations_org_date" in index_names

    def test_conversations_org_folder_index(self):
        from src.models.conversation import Conversation
        index_names = [idx.name for idx in Conversation.__table__.indexes]
        assert "ix_conversations_org_folder" in index_names

    def test_messages_conv_date_index(self):
        from src.models.conversation_message import ConversationMessage
        index_names = [idx.name for idx in ConversationMessage.__table__.indexes]
        assert "ix_messages_conv_date" in index_names

    def test_templates_org_active_usage_index(self):
        from src.models.query_template import QueryTemplate
        index_names = [idx.name for idx in QueryTemplate.__table__.indexes]
        assert "ix_templates_org_active_usage" in index_names

    def test_template_mappings_template_index(self):
        from src.models.query_template_mapping import QueryTemplateMapping
        index_names = [idx.name for idx in QueryTemplateMapping.__table__.indexes]
        assert "ix_mappings_template_id" in index_names
