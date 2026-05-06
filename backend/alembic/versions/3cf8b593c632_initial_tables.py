"""initial tables

Revision ID: 3cf8b593c632
Revises:
Create Date: 2026-05-06 09:53:37.917351

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3cf8b593c632'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create enums
    genderenum = postgresql.ENUM('male', 'female', 'other', name='genderenum', create_type=False)
    genderenum.create(op.get_bind(), checkfirst=True)

    dimensionenum = postgresql.ENUM('exercise', 'diet', 'sleep', 'appearance', name='dimensionenum', create_type=False)
    dimensionenum.create(op.get_bind(), checkfirst=True)

    taskstatusenum = postgresql.ENUM('pending', 'in_progress', 'completed', 'failed', name='taskstatusenum', create_type=False)
    taskstatusenum.create(op.get_bind(), checkfirst=True)

    difficultyenum = postgresql.ENUM('easy', 'medium', 'hard', name='difficultyenum', create_type=False)
    difficultyenum.create(op.get_bind(), checkfirst=True)

    roleenum = postgresql.ENUM('system', 'user', name='roleenum', create_type=False)
    roleenum.create(op.get_bind(), checkfirst=True)

    # Create users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('nickname', sa.String(100), nullable=False),
        sa.Column('avatar_url', sa.String(500)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Create user_profiles table
    op.create_table(
        'user_profiles',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), unique=True, nullable=False),
        sa.Column('height_cm', sa.Numeric(5, 1)),
        sa.Column('weight_kg', sa.Numeric(5, 1)),
        sa.Column('age', sa.Integer),
        sa.Column('gender', genderenum),
        sa.Column('body_fat_pct', sa.Numeric(4, 1)),
        sa.Column('front_photo_url', sa.String(500)),
        sa.Column('side_photo_url', sa.String(500)),
        sa.Column('ai_profile_score', postgresql.JSON),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Create user_scores table
    op.create_table(
        'user_scores',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('dimension', dimensionenum, nullable=False),
        sa.Column('score', sa.Numeric(4, 1), server_default='50.0'),
        sa.Column('total_positive_count', sa.Integer, server_default='0'),
        sa.Column('total_negative_count', sa.Integer, server_default='0'),
        sa.Column('streak_days', sa.Integer, server_default='0'),
        sa.Column('last_score_change', sa.DateTime(timezone=True)),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Create score_history table
    op.create_table(
        'score_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('dimension', dimensionenum, nullable=False),
        sa.Column('delta', sa.Numeric(3, 1), nullable=False),
        sa.Column('reason', sa.String(500)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Create tasks table
    op.create_table(
        'tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('dimension', dimensionenum, nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('difficulty', difficultyenum, server_default='medium'),
        sa.Column('scheduled_date', sa.Date, nullable=False, index=True),
        sa.Column('status', taskstatusenum, server_default='pending'),
        sa.Column('completion_proof', sa.Text),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Create conversations table
    op.create_table(
        'conversations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('role', roleenum, nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('metadata', postgresql.JSON),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Create weight_records table
    op.create_table(
        'weight_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('weight_kg', sa.Numeric(5, 1), nullable=False),
        sa.Column('recorded_at', sa.Date, nullable=False),
        sa.Column('ai_evaluation', postgresql.JSON),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('weight_records')
    op.drop_table('conversations')
    op.drop_table('tasks')
    op.drop_table('score_history')
    op.drop_table('user_scores')
    op.drop_table('user_profiles')
    op.drop_table('users')

    op.execute('DROP TYPE IF EXISTS roleenum')
    op.execute('DROP TYPE IF EXISTS difficultyenum')
    op.execute('DROP TYPE IF EXISTS taskstatusenum')
    op.execute('DROP TYPE IF EXISTS dimensionenum')
    op.execute('DROP TYPE IF EXISTS genderenum')
