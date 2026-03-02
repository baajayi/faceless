"""Initial schema — 8 tables

Revision ID: 0001
Revises:
Create Date: 2026-03-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── runs ─────────────────────────────────────────────────────────────────
    op.create_table(
        "runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_date", sa.Date(), nullable=False, unique=True),
        sa.Column("status", sa.String(30), nullable=False, default="PENDING"),
        sa.Column("cost_usd", sa.Numeric(10, 4), nullable=False, default=0),
        sa.Column("celery_task_id", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    # ── topics ───────────────────────────────────────────────────────────────
    op.create_table(
        "topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("trend_score", sa.Float(), nullable=False, default=0.0),
        sa.Column("kid_score", sa.Float(), nullable=False, default=0.0),
        sa.Column("educational_score", sa.Float(), nullable=False, default=0.0),
        sa.Column("novelty_score", sa.Float(), nullable=False, default=0.0),
        sa.Column("risk_score", sa.Float(), nullable=False, default=0.0),
        sa.Column("composite_score", sa.Float(), nullable=False, default=0.0),
        sa.Column("is_selected", sa.Boolean(), nullable=False, default=False),
        sa.Column("safety_report", postgresql.JSONB(), nullable=True),
        sa.Column("raw_sources", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_topics_run_id", "topics", ["run_id"])
    op.create_index("ix_topics_is_selected", "topics", ["is_selected"])

    # ── scripts ──────────────────────────────────────────────────────────────
    op.create_table(
        "scripts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("topics.id"), nullable=False),
        sa.Column("raw_json", postgresql.JSONB(), nullable=False),
        sa.Column("estimated_duration_s", sa.Float(), nullable=True),
        sa.Column("validation_errors", postgresql.JSONB(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_scripts_run_id", "scripts", ["run_id"])

    # ── storyboards ──────────────────────────────────────────────────────────
    op.create_table(
        "storyboards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("script_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scripts.id"), nullable=False),
        sa.Column("raw_json", postgresql.JSONB(), nullable=False),
        sa.Column("shot_count", sa.Integer(), nullable=False, default=0),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_storyboards_run_id", "storyboards", ["run_id"])

    # ── assets ───────────────────────────────────────────────────────────────
    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column(
            "asset_type",
            sa.String(30),
            nullable=False,
        ),  # image | audio | video_shot | thumbnail | music
        sa.Column("shot_index", sa.Integer(), nullable=True),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("dalle_prompt", sa.Text(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 4), nullable=False, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_assets_run_id", "assets", ["run_id"])

    # ── videos ───────────────────────────────────────────────────────────────
    op.create_table(
        "videos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("thumbnail_path", sa.String(500), nullable=True),
        sa.Column("duration_s", sa.Float(), nullable=True),
        sa.Column("qa_passed", sa.Boolean(), nullable=True),
        sa.Column("qa_report", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_videos_run_id", "videos", ["run_id"])

    # ── publish_jobs ─────────────────────────────────────────────────────────
    op.create_table(
        "publish_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("mode", sa.String(5), nullable=False, default="C"),
        sa.Column("status", sa.String(30), nullable=False, default="PENDING"),
        sa.Column("export_path", sa.String(500), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("hashtags", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_publish_jobs_run_id", "publish_jobs", ["run_id"])

    # ── errors ───────────────────────────────────────────────────────────────
    op.create_table(
        "errors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("stage", sa.String(50), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("traceback", sa.Text(), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False, default=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_errors_run_id", "errors", ["run_id"])


def downgrade() -> None:
    op.drop_table("errors")
    op.drop_table("publish_jobs")
    op.drop_table("videos")
    op.drop_table("assets")
    op.drop_table("storyboards")
    op.drop_table("scripts")
    op.drop_table("topics")
    op.drop_table("runs")
