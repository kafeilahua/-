"""Add spaced review schedules, personal notes, favorites and local reports."""

import sqlalchemy as sa

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("mistakes", sa.Column("due_at", sa.Float(), nullable=True))
    op.add_column("mistakes", sa.Column("review_stage", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("mistakes", sa.Column("last_reviewed", sa.Float(), nullable=True))
    op.add_column("mistakes", sa.Column("schedule_updated", sa.Float(), nullable=False, server_default="0"))
    op.add_column(
        "mistakes",
        sa.Column("imported_wrong_sources", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.execute(
        "UPDATE mistakes SET due_at = CASE WHEN mastered = 0 THEN updated ELSE NULL END, schedule_updated = updated"
    )
    op.create_table(
        "personal_questions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", sa.String(), nullable=False),
        sa.Column("favorite", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("updated", sa.Float(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "question_id"),
    )
    op.create_table(
        "question_reports",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.String(), nullable=True),
        sa.Column("question_id", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created", sa.Float(), nullable=False),
        sa.Column("updated", sa.Float(), nullable=False),
    )
    for table in ("personal_questions", "question_reports"):
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])


def downgrade():
    op.drop_table("question_reports")
    op.drop_table("personal_questions")
    with op.batch_alter_table("mistakes") as batch:
        for column in (
            "imported_wrong_sources",
            "schedule_updated",
            "last_reviewed",
            "review_stage",
            "due_at",
        ):
            batch.drop_column(column)
