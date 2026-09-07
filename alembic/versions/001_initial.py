"""Initial personal study schema, frozen independently of current models."""

import sqlalchemy as sa

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("username", sa.String(), nullable=False, unique=True),
        sa.Column("password", sa.Text(), nullable=False),
        sa.Column("timezone", sa.String(), nullable=False),
    )
    op.create_table(
        "logins",
        sa.Column("token", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("csrf", sa.String(), nullable=False),
        sa.Column("expires", sa.Float(), nullable=False),
    )
    op.create_table(
        "exams",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("started", sa.Float(), nullable=False),
        sa.Column("deadline", sa.Float()),
        sa.Column("finished", sa.Float()),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
    )
    op.create_table(
        "attempts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("exam_id", sa.String(), sa.ForeignKey("exams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", sa.String(), nullable=False),
        sa.Column("topic", sa.Integer(), nullable=False),
        sa.Column("created", sa.Float(), nullable=False),
        sa.Column("correct", sa.Integer(), nullable=False),
        sa.Column("earned", sa.Integer(), nullable=False),
        sa.Column("possible", sa.Integer(), nullable=False),
        sa.Column("answer", sa.JSON(), nullable=False),
        sa.UniqueConstraint("exam_id", "question_id"),
    )
    op.create_table(
        "mistakes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", sa.String(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("mastered", sa.Integer(), nullable=False),
        sa.Column("updated", sa.Float(), nullable=False),
        sa.UniqueConstraint("user_id", "question_id"),
    )
    op.create_table(
        "activity",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.String(), nullable=False),
        sa.Column("seconds", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "day"),
    )
    for table in ("exams", "attempts", "mistakes"):
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])


def downgrade():
    for table in ("activity", "mistakes", "attempts", "exams", "logins", "users"):
        op.drop_table(table)
