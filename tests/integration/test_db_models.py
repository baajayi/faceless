"""Integration tests for DB models — uses SQLite with JSON-compatible schema."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


# ── SQLite-compatible base + models (mirrors app/db/models.py without PG types) ──

class SqliteBase(DeclarativeBase):
    pass


class RunT(SqliteBase):
    __tablename__ = "runs"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_date = Column(Date(), nullable=False, unique=True)
    status = Column(String(30), nullable=False, default="PENDING")
    cost_usd = Column(Numeric(10, 4), nullable=False, default=Decimal("0"))
    celery_task_id = Column(String(200), nullable=True)
    created_at = Column(DateTime(), server_default=func.now())
    updated_at = Column(DateTime(), server_default=func.now())


class TopicT(SqliteBase):
    __tablename__ = "topics"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String(36), ForeignKey("runs.id"), nullable=False)
    title = Column(String(300), nullable=False)
    category = Column(String(100), nullable=True)
    trend_score = Column(Float(), nullable=False, default=0.0)
    kid_score = Column(Float(), nullable=False, default=0.0)
    educational_score = Column(Float(), nullable=False, default=0.0)
    novelty_score = Column(Float(), nullable=False, default=0.0)
    risk_score = Column(Float(), nullable=False, default=0.0)
    composite_score = Column(Float(), nullable=False, default=0.0)
    is_selected = Column(Boolean(), nullable=False, default=False)
    safety_report = Column(Text(), nullable=True)  # JSON as text for SQLite
    raw_sources = Column(Text(), nullable=True)
    created_at = Column(DateTime(), server_default=func.now())


class ScriptT(SqliteBase):
    __tablename__ = "scripts"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String(36), ForeignKey("runs.id"), nullable=False)
    topic_id = Column(String(36), ForeignKey("topics.id"), nullable=False)
    raw_json = Column(Text(), nullable=False)
    estimated_duration_s = Column(Float(), nullable=True)
    validation_errors = Column(Text(), nullable=True)
    prompt_tokens = Column(Integer(), nullable=True)
    completion_tokens = Column(Integer(), nullable=True)
    revision = Column(Integer(), nullable=False, default=0)
    created_at = Column(DateTime(), server_default=func.now())


class AssetT(SqliteBase):
    __tablename__ = "assets"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String(36), ForeignKey("runs.id"), nullable=False)
    asset_type = Column(String(30), nullable=False)
    shot_index = Column(Integer(), nullable=True)
    file_path = Column(String(500), nullable=True)
    dalle_prompt = Column(Text(), nullable=True)
    cost_usd = Column(Numeric(10, 4), nullable=False, default=Decimal("0"))
    created_at = Column(DateTime(), server_default=func.now())


class VideoT(SqliteBase):
    __tablename__ = "videos"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String(36), ForeignKey("runs.id"), nullable=False)
    file_path = Column(String(500), nullable=True)
    thumbnail_path = Column(String(500), nullable=True)
    duration_s = Column(Float(), nullable=True)
    qa_passed = Column(Boolean(), nullable=True)
    qa_report = Column(Text(), nullable=True)
    created_at = Column(DateTime(), server_default=func.now())


class PublishJobT(SqliteBase):
    __tablename__ = "publish_jobs"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String(36), ForeignKey("runs.id"), nullable=False)
    mode = Column(String(5), nullable=False, default="C")
    status = Column(String(30), nullable=False, default="PENDING")
    export_path = Column(String(500), nullable=True)
    caption = Column(Text(), nullable=True)
    hashtags = Column(Text(), nullable=True)  # JSON text for SQLite
    metadata_json = Column(Text(), nullable=True)
    created_at = Column(DateTime(), server_default=func.now())
    updated_at = Column(DateTime(), server_default=func.now())


class ErrorT(SqliteBase):
    __tablename__ = "errors"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String(36), ForeignKey("runs.id"), nullable=False)
    stage = Column(String(50), nullable=False)
    message = Column(Text(), nullable=True)
    traceback = Column(Text(), nullable=True)
    retryable = Column(Boolean(), nullable=False, default=True)
    retry_count = Column(Integer(), nullable=False, default=0)
    created_at = Column(DateTime(), server_default=func.now())


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    SqliteBase.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    conn = engine.connect()
    tx = conn.begin()
    TestSessionLocal = sessionmaker(bind=conn)
    s = TestSessionLocal()
    yield s
    s.close()
    tx.rollback()
    conn.close()


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestRunModel:
    def test_create_run(self, session):
        run = RunT(run_date=date(2026, 3, 2), status="PENDING")
        session.add(run)
        session.flush()

        assert run.id is not None
        assert run.status == "PENDING"
        assert run.cost_usd == Decimal("0")

    def test_run_date_unique(self, session):
        run1 = RunT(run_date=date(2026, 3, 3))
        session.add(run1)
        session.flush()

        run2 = RunT(run_date=date(2026, 3, 3))
        session.add(run2)
        with pytest.raises(Exception):  # unique constraint
            session.flush()

    def test_run_status_transitions(self, session):
        run = RunT(run_date=date(2026, 3, 4), status="PENDING")
        session.add(run)
        session.flush()

        run.status = "TREND_RESEARCH"
        session.flush()
        assert run.status == "TREND_RESEARCH"

        run.status = "DONE"
        session.flush()
        assert run.status == "DONE"


class TestTopicModel:
    def test_create_topic(self, session):
        run = RunT(run_date=date(2026, 3, 5))
        session.add(run)
        session.flush()

        topic = TopicT(
            run_id=run.id,
            title="Why Do Butterflies Have Wings",
            trend_score=0.8,
            kid_score=0.7,
            educational_score=0.9,
            novelty_score=1.0,
            risk_score=0.01,
            composite_score=0.75,
        )
        session.add(topic)
        session.flush()

        assert topic.id is not None
        assert topic.is_selected is False

    def test_select_topic(self, session):
        run = RunT(run_date=date(2026, 3, 6))
        session.add(run)
        session.flush()

        topic = TopicT(run_id=run.id, title="Ocean Animals")
        session.add(topic)
        session.flush()

        topic.is_selected = True
        session.flush()
        assert topic.is_selected is True


class TestScriptModel:
    def test_create_script(self, session):
        run = RunT(run_date=date(2026, 3, 7))
        session.add(run)
        session.flush()

        topic = TopicT(run_id=run.id, title="Space Facts")
        session.add(topic)
        session.flush()

        import json
        script = ScriptT(
            run_id=run.id,
            topic_id=topic.id,
            raw_json=json.dumps({"title": "Space Facts for Kids"}),
            estimated_duration_s=30.0,
            prompt_tokens=100,
            completion_tokens=200,
        )
        session.add(script)
        session.flush()

        assert script.id is not None
        assert script.revision == 0


class TestAssetModel:
    def test_create_image_asset(self, session):
        run = RunT(run_date=date(2026, 3, 8))
        session.add(run)
        session.flush()

        asset = AssetT(
            run_id=run.id,
            asset_type="image",
            shot_index=0,
            file_path="/app/output/2026-03-08/images/shot_00.png",
            dalle_prompt="Cartoon butterfly, no faces",
            cost_usd=Decimal("0.040"),
        )
        session.add(asset)
        session.flush()

        assert asset.id is not None
        assert asset.asset_type == "image"
        assert asset.cost_usd == Decimal("0.040")


class TestPublishJobModel:
    def test_create_publish_job(self, session):
        run = RunT(run_date=date(2026, 3, 9))
        session.add(run)
        session.flush()

        job = PublishJobT(
            run_id=run.id,
            mode="C",
            status="PENDING",
            caption="Amazing butterfly facts!",
        )
        session.add(job)
        session.flush()

        assert job.id is not None
        assert job.status == "PENDING"

    def test_update_to_ready(self, session):
        run = RunT(run_date=date(2026, 3, 10))
        session.add(run)
        session.flush()

        job = PublishJobT(run_id=run.id, mode="C", status="PENDING")
        session.add(job)
        session.flush()

        job.status = "READY_TO_POST"
        job.export_path = "/app/output/2026-03-10"
        session.flush()

        assert job.status == "READY_TO_POST"


class TestErrorModel:
    def test_create_error(self, session):
        run = RunT(run_date=date(2026, 3, 11))
        session.add(run)
        session.flush()

        err = ErrorT(
            run_id=run.id,
            stage="scriptwriter",
            message="GPT-4o returned invalid JSON",
            retryable=True,
            retry_count=0,
        )
        session.add(err)
        session.flush()

        assert err.id is not None
        assert err.retryable is True
