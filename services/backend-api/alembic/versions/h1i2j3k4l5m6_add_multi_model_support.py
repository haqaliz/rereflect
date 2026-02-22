"""add_multi_model_support

Revision ID: h1i2j3k4l5m6
Revises: 6e4501930bf0
Create Date: 2026-02-22 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import os
import logging

logger = logging.getLogger(__name__)

# revision identifiers, used by Alembic.
revision: str = 'h1i2j3k4l5m6'
down_revision: Union[str, None] = '6e4501930bf0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Initial model seed data
SEED_MODELS = [
    ('openai', 'gpt-4o-mini', 'GPT-4o Mini', 0.15, 0.60, 128000, 16384, True, 'cheap', 'free'),
    ('openai', 'gpt-4o', 'GPT-4o', 2.50, 10.00, 128000, 16384, True, 'mid', 'pro'),
    ('openai', 'gpt-4-turbo', 'GPT-4 Turbo', 10.00, 30.00, 128000, 4096, True, 'premium', 'business'),
    ('anthropic', 'claude-haiku-4-5', 'Claude Haiku 4.5', 0.80, 4.00, 200000, 8192, False, 'cheap', 'free'),
    ('anthropic', 'claude-sonnet-4-6', 'Claude Sonnet 4.6', 3.00, 15.00, 200000, 8192, False, 'mid', 'pro'),
    ('anthropic', 'claude-opus-4-6', 'Claude Opus 4.6', 15.00, 75.00, 200000, 8192, False, 'premium', 'business'),
    ('google', 'gemini-2.0-flash', 'Gemini 2.0 Flash', 0.075, 0.30, 1048576, 8192, True, 'cheap', 'free'),
    ('google', 'gemini-2.0-pro', 'Gemini 2.0 Pro', 1.25, 5.00, 2097152, 8192, True, 'mid', 'pro'),
]


def upgrade() -> None:
    # 1. Create org_api_keys table
    op.create_table(
        'org_api_keys',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider', sa.String(20), nullable=False),
        sa.Column('encrypted_key', sa.Text(), nullable=False),
        sa.Column('key_hint', sa.String(8), nullable=True),
        sa.Column('is_valid', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('organization_id', 'provider', name='uq_org_api_key_org_provider'),
    )
    op.create_index('idx_org_api_keys_org', 'org_api_keys', ['organization_id'])

    # 2. Create org_ai_config table
    op.create_table(
        'org_ai_config',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), unique=True, nullable=False),
        sa.Column('default_provider', sa.String(20), server_default='openai', nullable=False),
        sa.Column('model_categorization', sa.String(50), server_default='gpt-4o-mini', nullable=False),
        sa.Column('model_analysis', sa.String(50), server_default='gpt-4o-mini', nullable=False),
        sa.Column('model_insights', sa.String(50), server_default='gpt-4o-mini', nullable=False),
        sa.Column('monthly_budget_cents', sa.Integer(), nullable=True),
        sa.Column('budget_used_cents', sa.Integer(), server_default='0', nullable=False),
        sa.Column('budget_reset_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # 3. Create llm_usage_logs table
    op.create_table(
        'llm_usage_logs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider', sa.String(20), nullable=False),
        sa.Column('model', sa.String(50), nullable=False),
        sa.Column('task_type', sa.String(30), nullable=False),
        sa.Column('prompt_tokens', sa.Integer(), nullable=False),
        sa.Column('completion_tokens', sa.Integer(), nullable=False),
        sa.Column('total_tokens', sa.Integer(), nullable=False),
        sa.Column('estimated_cost_cents', sa.Float(), nullable=False),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('was_fallback', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('fallback_reason', sa.String(30), nullable=True),
        sa.Column('is_byok', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('idx_llm_usage_org_date', 'llm_usage_logs', ['organization_id', 'created_at'])

    # 4. Create llm_model_prices table
    op.create_table(
        'llm_model_prices',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('provider', sa.String(20), nullable=False),
        sa.Column('model_id', sa.String(50), nullable=False),
        sa.Column('display_name', sa.String(100), nullable=False),
        sa.Column('input_price_per_1m_tokens', sa.Float(), nullable=False),
        sa.Column('output_price_per_1m_tokens', sa.Float(), nullable=False),
        sa.Column('context_window', sa.Integer(), nullable=True),
        sa.Column('max_output_tokens', sa.Integer(), nullable=True),
        sa.Column('supports_json_mode', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('tier', sa.String(10), nullable=False),
        sa.Column('min_plan', sa.String(20), server_default='free', nullable=False),
        sa.Column('is_available', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('is_deprecated', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('replacement_model_id', sa.String(50), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('provider', 'model_id', name='uq_llm_model_price_provider_model'),
    )

    # 5. Add llm_provider, llm_model columns to feedback_items
    op.add_column('feedback_items', sa.Column('llm_provider', sa.String(20), nullable=True))
    op.add_column('feedback_items', sa.Column('llm_model', sa.String(50), nullable=True))

    # 6. Add llm_provider, llm_model columns to customer_health_scores
    op.add_column('customer_health_scores', sa.Column('llm_provider', sa.String(20), nullable=True))
    op.add_column('customer_health_scores', sa.Column('llm_model', sa.String(50), nullable=True))

    # 7. Migrate existing openai_api_key to org_api_keys
    conn = op.get_bind()
    try:
        # Try to encrypt with Fernet if key is available
        encryption_key = os.environ.get("LLM_ENCRYPTION_KEY", "")
        use_encryption = False
        fernet = None

        if encryption_key:
            try:
                from cryptography.fernet import Fernet
                fernet = Fernet(encryption_key.encode())
                use_encryption = True
            except Exception:
                logger.warning("Could not initialize Fernet encryption, storing keys as-is")

        # Check if openai_api_key column exists before trying to migrate
        result = conn.execute(sa.text(
            "SELECT id, openai_api_key FROM organizations WHERE openai_api_key IS NOT NULL AND openai_api_key != ''"
        ))
        rows = result.fetchall()

        for row in rows:
            org_id = row[0]
            api_key = row[1]
            key_hint = api_key[-4:] if len(api_key) >= 4 else api_key

            if use_encryption and fernet:
                encrypted = fernet.encrypt(api_key.encode()).decode()
            else:
                encrypted = api_key  # Store as-is if no encryption key

            conn.execute(sa.text(
                "INSERT INTO org_api_keys (organization_id, provider, encrypted_key, key_hint, is_valid, created_at, updated_at) "
                "VALUES (:org_id, 'openai', :encrypted, :hint, true, NOW(), NOW())"
            ), {"org_id": org_id, "encrypted": encrypted, "hint": key_hint})

        logger.info(f"Migrated {len(rows)} org API keys to org_api_keys table")
    except Exception as e:
        logger.warning(f"Could not migrate openai_api_key values: {e}")

    # 8. Create default org_ai_config for all existing orgs
    try:
        conn.execute(sa.text(
            "INSERT INTO org_ai_config (organization_id, default_provider, model_categorization, model_analysis, model_insights, budget_used_cents, created_at, updated_at) "
            "SELECT id, 'openai', 'gpt-4o-mini', 'gpt-4o-mini', 'gpt-4o-mini', 0, NOW(), NOW() FROM organizations "
            "ON CONFLICT DO NOTHING"
        ))
        logger.info("Created default org_ai_config for all existing organizations")
    except Exception as e:
        logger.warning(f"Could not create default org_ai_config: {e}")

    # 9. Seed llm_model_prices
    for provider, model_id, display_name, input_price, output_price, ctx_window, max_output, json_mode, tier, min_plan in SEED_MODELS:
        conn.execute(sa.text(
            "INSERT INTO llm_model_prices (provider, model_id, display_name, input_price_per_1m_tokens, output_price_per_1m_tokens, "
            "context_window, max_output_tokens, supports_json_mode, tier, min_plan, is_available, is_deprecated, updated_at) "
            "VALUES (:provider, :model_id, :display_name, :input_price, :output_price, :ctx_window, :max_output, :json_mode, :tier, :min_plan, true, false, NOW()) "
            "ON CONFLICT DO NOTHING"
        ), {
            "provider": provider, "model_id": model_id, "display_name": display_name,
            "input_price": input_price, "output_price": output_price,
            "ctx_window": ctx_window, "max_output": max_output, "json_mode": json_mode,
            "tier": tier, "min_plan": min_plan,
        })
    logger.info("Seeded llm_model_prices with 8 initial models")

    # 10. Drop openai_api_key from organizations
    op.drop_column('organizations', 'openai_api_key')


def downgrade() -> None:
    # 1. Re-add openai_api_key to organizations
    op.add_column('organizations', sa.Column('openai_api_key', sa.Text(), nullable=True))

    # 2. Restore openai keys from org_api_keys (best-effort, decrypted if possible)
    conn = op.get_bind()
    try:
        result = conn.execute(sa.text(
            "SELECT organization_id, encrypted_key FROM org_api_keys WHERE provider = 'openai'"
        ))
        rows = result.fetchall()

        encryption_key = os.environ.get("LLM_ENCRYPTION_KEY", "")
        fernet = None
        if encryption_key:
            try:
                from cryptography.fernet import Fernet
                fernet = Fernet(encryption_key.encode())
            except Exception:
                pass

        for row in rows:
            org_id = row[0]
            encrypted = row[1]
            try:
                if fernet:
                    plain_key = fernet.decrypt(encrypted.encode()).decode()
                else:
                    plain_key = encrypted
                conn.execute(sa.text(
                    "UPDATE organizations SET openai_api_key = :key WHERE id = :org_id"
                ), {"key": plain_key, "org_id": org_id})
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Could not restore openai_api_key values: {e}")

    # 3. Drop new columns from feedback_items and customer_health_scores
    op.drop_column('customer_health_scores', 'llm_model')
    op.drop_column('customer_health_scores', 'llm_provider')
    op.drop_column('feedback_items', 'llm_model')
    op.drop_column('feedback_items', 'llm_provider')

    # 4. Drop new tables
    op.drop_table('llm_model_prices')
    op.drop_table('llm_usage_logs')
    op.drop_table('org_ai_config')
    op.drop_table('org_api_keys')
