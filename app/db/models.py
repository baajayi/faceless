"""All ORM models — 8 tables."""
import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


# ── Run status constants ──────────────────────────────────────────────────────
class RunStatus:
    PENDING = "PENDING"
    TREND_RESEARCH = "TREND_RESEARCH"
    TOPIC_SELECTED = "TOPIC_SELECTED"
    SCRIPTED = "SCRIPTED"
    STORYBOARDED = "STORYBOARDED"
    ASSETS_GENERATING = "ASSETS_GENERATING"
    ASSETS_DONE = "ASSETS_DONE"
    ASSEMBLING = "ASSEMBLING"
    QA = "QA"
    PUBLISHING = "PUBLISHING"
    DONE = "DONE"
    FAILED = "FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class AssetType:
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO_SHOT = "video_shot"
    THUMBNAIL = "thumbnail"
    MUSIC = "music"


class PublishStatus:
    PENDING = "PENDING"
    READY_TO_POST = "READY_TO_POST"
    POSTED = "POSTED"
    FAILED = "FAILED"


# ── Models ────────────────────────────────────────────────────────────────────

class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_date: Mapped[date] = mapped_column(Date(), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=RunStatus.PENDING)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=Decimal("0"))
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # relationships
    topics: Mapped[list["Topic"]] = relationship("Topic", back_populates="run", lazy="dynamic")
    scripts: Mapped[list["Script"]] = relationship("Script", back_populates="run", lazy="dynamic")
    storyboards: Mapped[list["Storyboard"]] = relationship(
        "Storyboard", back_populates="run", lazy="dynamic"
    )
    assets: Mapped[list["Asset"]] = relationship("Asset", back_populates="run", lazy="dynamic")
    videos: Mapped[list["Video"]] = relationship("Video", back_populates="run", lazy="dynamic")
    publish_jobs: Mapped[list["PublishJob"]] = relationship(
        "PublishJob", back_populates="run", lazy="dynamic"
    )
    errors: Mapped[list["Error"]] = relationship("Error", back_populates="run", lazy="dynamic")


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("runs.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    trend_score: Mapped[float] = mapped_column(Float(), nullable=False, default=0.0)
    kid_score: Mapped[float] = mapped_column(Float(), nullable=False, default=0.0)
    educational_score: Mapped[float] = mapped_column(Float(), nullable=False, default=0.0)
    novelty_score: Mapped[float] = mapped_column(Float(), nullable=False, default=0.0)
    risk_score: Mapped[float] = mapped_column(Float(), nullable=False, default=0.0)
    composite_score: Mapped[float] = mapped_column(Float(), nullable=False, default=0.0)
    is_selected: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    safety_report: Mapped[Optional[dict]] = mapped_column(JSONB(), nullable=True)
    raw_sources: Mapped[Optional[dict]] = mapped_column(JSONB(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    run: Mapped["Run"] = relationship("Run", back_populates="topics")
    scripts: Mapped[list["Script"]] = relationship("Script", back_populates="topic", lazy="dynamic")


class Script(Base):
    __tablename__ = "scripts"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("runs.id"), nullable=False)
    topic_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("topics.id"), nullable=False
    )
    raw_json: Mapped[dict] = mapped_column(JSONB(), nullable=False)
    estimated_duration_s: Mapped[Optional[float]] = mapped_column(Float(), nullable=True)
    validation_errors: Mapped[Optional[list]] = mapped_column(JSONB(), nullable=True)
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer(), nullable=True)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer(), nullable=True)
    revision: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    run: Mapped["Run"] = relationship("Run", back_populates="scripts")
    topic: Mapped["Topic"] = relationship("Topic", back_populates="scripts")
    storyboards: Mapped[list["Storyboard"]] = relationship(
        "Storyboard", back_populates="script", lazy="dynamic"
    )


class Storyboard(Base):
    __tablename__ = "storyboards"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("runs.id"), nullable=False)
    script_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("scripts.id"), nullable=False
    )
    raw_json: Mapped[dict] = mapped_column(JSONB(), nullable=False)
    shot_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer(), nullable=True)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    run: Mapped["Run"] = relationship("Run", back_populates="storyboards")
    script: Mapped["Script"] = relationship("Script", back_populates="storyboards")


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("runs.id"), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(30), nullable=False)  # AssetType constants
    shot_index: Mapped[Optional[int]] = mapped_column(Integer(), nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    dalle_prompt: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    run: Mapped["Run"] = relationship("Run", back_populates="assets")


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("runs.id"), nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    duration_s: Mapped[Optional[float]] = mapped_column(Float(), nullable=True)
    qa_passed: Mapped[Optional[bool]] = mapped_column(Boolean(), nullable=True)
    qa_report: Mapped[Optional[dict]] = mapped_column(JSONB(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    run: Mapped["Run"] = relationship("Run", back_populates="videos")


class PublishJob(Base):
    __tablename__ = "publish_jobs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("runs.id"), nullable=False)
    mode: Mapped[str] = mapped_column(String(5), nullable=False, default="C")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=PublishStatus.PENDING)
    export_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    caption: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    hashtags: Mapped[Optional[list]] = mapped_column(ARRAY(String()), nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    run: Mapped["Run"] = relationship("Run", back_populates="publish_jobs")


class Error(Base):
    __tablename__ = "errors"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("runs.id"), nullable=False)
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    traceback: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    retry_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    run: Mapped["Run"] = relationship("Run", back_populates="errors")
