"""fix user deletion FK constraints

Make FK columns nullable where user data should be preserved
after user deletion, and add ondelete behavior to all user FKs.

Revision ID: e8f9g0h1i2j3
Revises: d7e8f9g0h1i2
Create Date: 2026-02-17 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8f9g0h1i2j3'
down_revision: Union[str, None] = 'd7e8f9g0h1i2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_fk_name(conn, table_name, column_name):
    """Look up the actual FK constraint name from PostgreSQL catalog."""
    result = conn.execute(sa.text("""
        SELECT tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_name = :table_name
            AND kcu.column_name = :column_name
        LIMIT 1
    """), {"table_name": table_name, "column_name": column_name})
    row = result.fetchone()
    if not row:
        raise RuntimeError(f"No FK constraint found on {table_name}.{column_name}")
    return row[0]


def _replace_fk(conn, table_name, column_name, ref_table, ref_column, ondelete, new_name):
    """Drop existing FK and recreate with ondelete behavior."""
    old_name = _get_fk_name(conn, table_name, column_name)
    op.drop_constraint(old_name, table_name, type_='foreignkey')
    op.create_foreign_key(new_name, table_name, ref_table, [column_name], [ref_column], ondelete=ondelete)


def upgrade() -> None:
    conn = op.get_bind()

    # --- Make columns nullable for preserved records ---
    op.alter_column('audit_logs', 'user_id', existing_type=sa.Integer(), nullable=True)
    op.alter_column('feedback_workflow_events', 'actor_id', existing_type=sa.Integer(), nullable=True)
    op.alter_column('feedback_notes', 'author_id', existing_type=sa.Integer(), nullable=True)
    op.alter_column('shared_links', 'created_by_id', existing_type=sa.Integer(), nullable=True)
    op.alter_column('team_invites', 'invited_by_id', existing_type=sa.Integer(), nullable=True)

    # --- Replace FK constraints with ondelete behavior ---

    # SET NULL: preserve historical data, just remove the user reference
    _replace_fk(conn, 'audit_logs', 'user_id', 'users', 'id', 'SET NULL', 'fk_audit_logs_user_id')
    _replace_fk(conn, 'feedback_workflow_events', 'actor_id', 'users', 'id', 'SET NULL', 'fk_workflow_events_actor_id')
    _replace_fk(conn, 'feedback_notes', 'author_id', 'users', 'id', 'SET NULL', 'fk_feedback_notes_author_id')
    _replace_fk(conn, 'shared_links', 'created_by_id', 'users', 'id', 'SET NULL', 'fk_shared_links_created_by_id')
    _replace_fk(conn, 'team_invites', 'invited_by_id', 'users', 'id', 'SET NULL', 'fk_team_invites_invited_by_id')
    _replace_fk(conn, 'feedback_items', 'assigned_to', 'users', 'id', 'SET NULL', 'fk_feedback_items_assigned_to')

    # CASCADE: delete user-owned personal data
    _replace_fk(conn, 'notifications', 'user_id', 'users', 'id', 'CASCADE', 'fk_notifications_user_id')
    _replace_fk(conn, 'saved_views', 'created_by_id', 'users', 'id', 'CASCADE', 'fk_saved_views_created_by_id')
    _replace_fk(conn, 'user_alert_preferences', 'user_id', 'users', 'id', 'CASCADE', 'fk_user_alert_prefs_user_id')
    _replace_fk(conn, 'assignment_rules', 'assign_to_user_id', 'users', 'id', 'CASCADE', 'fk_assignment_rules_user_id')

    # users.invited_by_id already has ondelete='SET NULL' from original migration — skip


def downgrade() -> None:
    conn = op.get_bind()

    # Revert FK constraints (remove ondelete behavior)
    _replace_fk(conn, 'assignment_rules', 'assign_to_user_id', 'users', 'id', None, 'fk_assignment_rules_user_id')
    _replace_fk(conn, 'user_alert_preferences', 'user_id', 'users', 'id', None, 'fk_user_alert_prefs_user_id')
    _replace_fk(conn, 'saved_views', 'created_by_id', 'users', 'id', None, 'fk_saved_views_created_by_id')
    _replace_fk(conn, 'notifications', 'user_id', 'users', 'id', None, 'fk_notifications_user_id')
    _replace_fk(conn, 'feedback_items', 'assigned_to', 'users', 'id', None, 'fk_feedback_items_assigned_to')
    _replace_fk(conn, 'team_invites', 'invited_by_id', 'users', 'id', None, 'fk_team_invites_invited_by_id')
    _replace_fk(conn, 'shared_links', 'created_by_id', 'users', 'id', None, 'fk_shared_links_created_by_id')
    _replace_fk(conn, 'feedback_notes', 'author_id', 'users', 'id', None, 'fk_feedback_notes_author_id')
    _replace_fk(conn, 'feedback_workflow_events', 'actor_id', 'users', 'id', None, 'fk_workflow_events_actor_id')
    _replace_fk(conn, 'audit_logs', 'user_id', 'users', 'id', None, 'fk_audit_logs_user_id')

    # Revert nullable changes
    op.alter_column('team_invites', 'invited_by_id', existing_type=sa.Integer(), nullable=False)
    op.alter_column('shared_links', 'created_by_id', existing_type=sa.Integer(), nullable=False)
    op.alter_column('feedback_notes', 'author_id', existing_type=sa.Integer(), nullable=False)
    op.alter_column('feedback_workflow_events', 'actor_id', existing_type=sa.Integer(), nullable=False)
    op.alter_column('audit_logs', 'user_id', existing_type=sa.Integer(), nullable=False)
