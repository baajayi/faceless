#!/usr/bin/env python3
"""
run_full_pipeline.py — Run the real pipeline end-to-end using real OpenAI APIs.

Uses SQLite locally (no Docker/Postgres needed).
Produces a fully AI-generated video in output/{run_date}/.

Usage:
    python scripts/run_full_pipeline.py [--date YYYY-MM-DD] [--force]
"""
from __future__ import annotations

import json
import os
import sys
import traceback
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import click
from dotenv import load_dotenv

# ── Load .env before any app imports ─────────────────────────────────────────
load_dotenv(Path(__file__).parent.parent / ".env")

# ── Patch DB to use SQLite in-process ────────────────────────────────────────
# We do this before importing app modules so the engine is created with SQLite.

import sqlalchemy
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

_DB_PATH = Path(__file__).parent.parent / "output" / "pipeline.sqlite3"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
_SQLITE_URL = f"sqlite:///{_DB_PATH}"

# Patch settings DATABASE_URL before anything imports it
os.environ["DATABASE_URL"] = _SQLITE_URL

# Now import app modules
from app.settings import settings  # noqa: E402

# Override artifacts dir to local output/
settings.ARTIFACTS_DIR = str(Path(__file__).parent.parent / "output")

# ── Bootstrap SQLite schema ───────────────────────────────────────────────────

def _bootstrap_db(engine) -> None:
    """Create all 8 tables with SQLite-compatible types."""
    ddl = """
    CREATE TABLE IF NOT EXISTS runs (
        id TEXT PRIMARY KEY,
        run_date DATE NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'PENDING',
        cost_usd NUMERIC(10,4) NOT NULL DEFAULT 0,
        celery_task_id TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS topics (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(id),
        title TEXT NOT NULL,
        category TEXT,
        trend_score REAL NOT NULL DEFAULT 0.0,
        kid_score REAL NOT NULL DEFAULT 0.0,
        educational_score REAL NOT NULL DEFAULT 0.0,
        novelty_score REAL NOT NULL DEFAULT 0.0,
        risk_score REAL NOT NULL DEFAULT 0.0,
        composite_score REAL NOT NULL DEFAULT 0.0,
        is_selected INTEGER NOT NULL DEFAULT 0,
        safety_report TEXT,
        raw_sources TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS scripts (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(id),
        topic_id TEXT NOT NULL REFERENCES topics(id),
        raw_json TEXT NOT NULL,
        estimated_duration_s REAL,
        validation_errors TEXT,
        prompt_tokens INTEGER,
        completion_tokens INTEGER,
        revision INTEGER NOT NULL DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS storyboards (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(id),
        script_id TEXT NOT NULL REFERENCES scripts(id),
        raw_json TEXT NOT NULL,
        shot_count INTEGER NOT NULL DEFAULT 0,
        prompt_tokens INTEGER,
        completion_tokens INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS assets (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(id),
        asset_type TEXT NOT NULL,
        shot_index INTEGER,
        file_path TEXT,
        dalle_prompt TEXT,
        cost_usd NUMERIC(10,4) NOT NULL DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS videos (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(id),
        file_path TEXT,
        thumbnail_path TEXT,
        duration_s REAL,
        qa_passed INTEGER,
        qa_report TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS publish_jobs (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(id),
        mode TEXT NOT NULL DEFAULT 'C',
        status TEXT NOT NULL DEFAULT 'PENDING',
        export_path TEXT,
        caption TEXT,
        hashtags TEXT,
        metadata_json TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS errors (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(id),
        stage TEXT NOT NULL,
        message TEXT,
        traceback TEXT,
        retryable INTEGER NOT NULL DEFAULT 1,
        retry_count INTEGER NOT NULL DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """
    with engine.begin() as conn:
        for stmt in ddl.strip().split(";"):
            s = stmt.strip()
            if s:
                conn.execute(text(s))


# ── Thin SQLite-compatible ORM shim ──────────────────────────────────────────
# Rather than fighting the PG-specific ORM models, we manage state in a simple
# dict-based store and provide a session-like interface to the agents.

class _Row:
    """Generic row object whose attributes can be set and read freely."""
    def __init__(self, table: str, **kwargs):
        self._table = table
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __repr__(self):
        return f"<{self._table} id={getattr(self, 'id', '?')}>"


class _Store:
    """In-memory store that also persists key fields to SQLite."""

    def __init__(self, engine):
        self._engine = engine
        self._rows: dict[str, _Row] = {}  # id → row

    def add(self, row: _Row):
        self._rows[row.id] = row

    def get_run(self, run_id: str) -> _Row | None:
        return self._rows.get(run_id)

    def get_topic(self, topic_id: str) -> _Row | None:
        return self._rows.get(topic_id)

    def find_first(self, table: str, **filters) -> _Row | None:
        for row in self._rows.values():
            if row._table != table:
                continue
            if all(getattr(row, k, None) == v for k, v in filters.items()):
                return row
        return None

    def find_all(self, table: str, **filters) -> list[_Row]:
        results = []
        for row in self._rows.values():
            if row._table != table:
                continue
            if all(getattr(row, k, None) == v for k, v in filters.items()):
                results.append(row)
        return results

    def count(self, table: str, **filters) -> int:
        return len(self.find_all(table, **filters))

    def persist_run(self, run: _Row):
        with self._engine.begin() as conn:
            conn.execute(
                text("INSERT OR REPLACE INTO runs (id, run_date, status, cost_usd) VALUES (:id, :d, :s, :c)"),
                {"id": run.id, "d": str(run.run_date), "s": run.status, "c": float(getattr(run, "cost_usd", 0))},
            )


# Global store instance
_store: _Store | None = None


def _make_session(store: _Store):
    """Create a mock session that delegates to our in-memory store."""
    session = MagicMock()
    session.flush = MagicMock()
    session.commit = MagicMock()
    session.close = MagicMock()

    def _get(model_class, pk):
        row = store.get_run(pk) or store.find_first(
            _table_name(model_class), id=pk
        )
        return row

    session.get.side_effect = _get

    def _query(model_class):
        table = _table_name(model_class)
        q = MagicMock()

        # .filter().first()
        def _filter(*args, **kwargs):
            fq = MagicMock()
            def _first():
                if table == "topics":
                    return store.find_first("topics", is_selected=1) or store.find_first("topics")
                if table == "scripts":
                    rows = store.find_all("scripts")
                    return sorted(rows, key=lambda r: getattr(r, "revision", 0), reverse=True)[0] if rows else None
                if table == "storyboards":
                    rows = store.find_all("storyboards")
                    return rows[0] if rows else None
                if table == "videos":
                    rows = store.find_all("videos")
                    return rows[0] if rows else None
                if table == "publish_jobs":
                    rows = store.find_all("publish_jobs")
                    return rows[0] if rows else None
                if table == "runs":
                    rows = store.find_all("runs")
                    return rows[0] if rows else None
                return None

            fq.first = _first
            fq.first.return_value = _first()

            def _order_by(*a):
                oq = MagicMock()
                oq.first.side_effect = _first
                return oq
            fq.order_by = _order_by

            def _all():
                return store.find_all(table)
            fq.all = _all
            fq.count.return_value = store.count(table)
            fq.join.return_value.filter.return_value.all.return_value = []
            return fq

        q.filter.side_effect = _filter
        q.filter.return_value = _filter()
        q.order_by.return_value.offset.return_value.limit.return_value.all.return_value = store.find_all(table)
        return q

    session.query.side_effect = _query

    def _add(row):
        if hasattr(row, "id") and row.id:
            store.add(row)
        if hasattr(row, "_table") and row._table == "runs":
            store.persist_run(row)

    session.add.side_effect = _add
    return session


def _table_name(model_class) -> str:
    if hasattr(model_class, "__tablename__"):
        return model_class.__tablename__
    return str(model_class)


# ── Patched agent implementations using SQLite-compatible rows ────────────────

def _run_trend_research(run_id: str, run: _Row, store: _Store) -> list[str]:
    from app.services.trends.google_trends import fetch_google_trends
    from app.services.trends.youtube_trends import fetch_youtube_trends

    run.status = "TREND_RESEARCH"
    store.persist_run(run)

    google = fetch_google_trends(region=settings.REGION)
    youtube = fetch_youtube_trends(region=settings.REGION)
    all_raw = google + youtube

    # Deduplicate
    seen = set()
    unique = []
    for t in all_raw:
        key = t["title"].lower()[:30]
        if key not in seen:
            seen.add(key)
            unique.append(t)

    topic_ids = []
    for t in unique[:15]:  # top 15 candidates
        title_lower = t["title"].lower()
        kid_kw = ["animal","dino","space","ocean","color","number","letter","fun","learn","magic"]
        edu_kw = ["fact","why","how","what","science","math","history","learn","discover"]
        kid_score = min(sum(1 for k in kid_kw if k in title_lower) / 3.0, 1.0)
        edu_score = min(sum(1 for k in edu_kw if k in title_lower) / 3.0, 1.0)

        tid = str(uuid.uuid4())
        topic = _Row(
            "topics",
            id=tid,
            run_id=run_id,
            title=t["title"],
            category=None,
            trend_score=t.get("trend_score", 0.5),
            kid_score=kid_score,
            educational_score=edu_score,
            novelty_score=1.0,
            risk_score=0.0,
            composite_score=0.0,
            is_selected=0,
            safety_report=None,
            raw_sources=json.dumps(t),
        )
        store.add(topic)
        topic_ids.append(tid)

    return topic_ids


def _run_topic_selection(run_id: str, run: _Row, store: _Store) -> str:
    import yaml
    from app.services.moderation.openai_moderation import moderate_text

    blocklist_path = Path(__file__).parent.parent / "configs" / "safety_blocklist.yaml"
    with open(blocklist_path) as f:
        blocklist = yaml.safe_load(f)
    blocked = [k.lower() for k in
               blocklist.get("blocked_keywords", []) + blocklist.get("blocked_brands", [])]

    candidates = store.find_all("topics")
    # Recent topics for diversity (none in first run)
    recent_cats: list[str] = []

    scores = []
    for topic in candidates:
        title_lower = topic.title.lower()
        if any(kw in title_lower for kw in blocked):
            continue
        mod = moderate_text(topic.title)
        risk = mod["risk_score"]
        if mod["flagged"] and risk > 0.7:
            continue
        topic.risk_score = risk
        topic.safety_report = json.dumps({
            "flagged": mod["flagged"],
            "risk_score": risk,
            "categories": mod["categories"],
        })
        composite = (
            0.25 * topic.trend_score
            + 0.30 * topic.kid_score
            + 0.25 * topic.educational_score
            + 0.15 * topic.novelty_score
            - 0.50 * risk
        )
        topic.composite_score = composite
        scores.append((topic, composite))

    if not scores:
        raise ValueError("No safe topics found")

    scores.sort(key=lambda x: x[1], reverse=True)
    selected, best = scores[0]
    selected.is_selected = 1

    run.status = "TOPIC_SELECTED"
    store.persist_run(run)
    return selected.id


def _run_scriptwriter(run_id: str, run: _Row, store: _Store, revision_feedback: str = "") -> str:
    import hashlib
    import openai
    from app.agents.scriptwriter import ScriptSchema, SYSTEM_PROMPT
    from app.utils.spellcheck import apply_spellcheck, spellcheck_enabled
    import json as _json

    topic = store.find_first("topics", is_selected=1)
    if not topic:
        raise ValueError("No selected topic")

    run_date_str = str(run.run_date)
    seed = int(hashlib.md5(run_date_str.encode()).hexdigest(), 16) % (2**31)

    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    system = SYSTEM_PROMPT.format(age_band=settings.AGE_BAND, visual_style=settings.VISUAL_STYLE)
    user_msg = f"Create an educational children's video script about: {topic.title}"
    if revision_feedback:
        user_msg += f"\n\nREVISION NEEDED: {revision_feedback}"

    total_prompt_tokens = total_completion_tokens = 0
    last_error = ""
    validated = None

    for attempt in range(2):
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user_msg}]
        if last_error and attempt > 0:
            messages.append({"role": "user", "content": f"Fix these errors: {last_error}"})

        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.8,
            seed=seed,
        )
        total_prompt_tokens += resp.usage.prompt_tokens
        total_completion_tokens += resp.usage.completion_tokens

        try:
            raw = _json.loads(resp.choices[0].message.content)
            _sanitize_sound_effects(raw)
            validated = ScriptSchema.model_validate(raw)
            break
        except Exception as e:
            last_error = str(e)

    if not validated:
        raise ValueError(f"Script validation failed: {last_error}")

    script_data = validated.model_dump()
    if spellcheck_enabled():
        script_data["title"], _ = apply_spellcheck(script_data.get("title", ""))
        for item in script_data.get("on_screen_text", []):
            if "text" in item:
                item["text"], _ = apply_spellcheck(item["text"])
    sid = str(uuid.uuid4())
    script = _Row(
        "scripts",
        id=sid,
        run_id=run_id,
        topic_id=topic.id,
        raw_json=script_data,
        estimated_duration_s=script_data.get("estimated_duration_s", 30.0),
        prompt_tokens=total_prompt_tokens,
        completion_tokens=total_completion_tokens,
        revision=1 if revision_feedback else 0,
    )
    store.add(script)
    run.status = "SCRIPTED"
    store.persist_run(run)
    return sid


def _sanitize_sound_effects(raw_data: dict) -> None:
    allowed = {"pop", "ding", "whoosh"}
    sfx = raw_data.get("sound_effects")
    if not isinstance(sfx, list):
        return
    cleaned = [item for item in sfx if isinstance(item, dict) and item.get("type") in allowed]
    raw_data["sound_effects"] = cleaned


def _run_storyboard(run_id: str, run: _Row, store: _Store) -> str:
    import openai
    from app.agents.storyboard import StoryboardSchema, STORYBOARD_SYSTEM
    from app.utils.spellcheck import apply_spellcheck, spellcheck_enabled
    import json as _json

    scripts = store.find_all("scripts")
    script = sorted(scripts, key=lambda r: getattr(r, "revision", 0), reverse=True)[0]
    script_data = script.raw_json

    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": STORYBOARD_SYSTEM},
            {"role": "user", "content": f"Create storyboard for:\n{_json.dumps(script_data, indent=2)}"},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
    )

    raw = _json.loads(resp.choices[0].message.content)
    validated = StoryboardSchema.model_validate(raw)
    board_data = validated.model_dump()
    if spellcheck_enabled():
        for shot in board_data.get("shots", []):
            if shot.get("text_overlay"):
                shot["text_overlay"], _ = apply_spellcheck(shot["text_overlay"])
    for shot in board_data.get("shots", []):
        if shot.get("text_overlay"):
            if "include exact text" not in shot.get("dalle_prompt", "").lower():
                shot["dalle_prompt"] = (
                    f'{shot["dalle_prompt"]} Include exact text: "{shot["text_overlay"]}". '
                    "Use clear block letters. No other words."
                )

    bid = str(uuid.uuid4())
    board = _Row(
        "storyboards",
        id=bid,
        run_id=run_id,
        script_id=script.id,
        raw_json=board_data,
        shot_count=len(board_data.get("shots", [])),
        prompt_tokens=resp.usage.prompt_tokens,
        completion_tokens=resp.usage.completion_tokens,
    )
    store.add(board)
    run.status = "STORYBOARDED"
    store.persist_run(run)
    return bid


def _run_asset_generation(run_id: str, run: _Row, store: _Store) -> list[str]:
    from app.services.image_gen.image_text_guard import generate_image_with_text_guard
    from app.services.tts.openai_tts import generate_speech
    from app.storage.artifact_paths import (
        ensure_dirs, shot_image_path, shot_audio_path, shot_video_path,
    )
    from app.agents.asset_generator import _build_style_prefix, _create_static_clip

    run.status = "ASSETS_GENERATING"
    store.persist_run(run)

    boards = store.find_all("storyboards")
    board = boards[0]
    board_data = board.raw_json

    scripts = store.find_all("scripts")
    script = sorted(scripts, key=lambda r: getattr(r, "revision", 0), reverse=True)[0]
    narration_data = script.raw_json.get("narration", [])

    run_date = str(run.run_date)
    ensure_dirs(run_date)

    shots = board_data.get("shots", [])
    style_lock = board_data.get("style_lock", {})
    style_prefix = _build_style_prefix(board_data.get("visual_style", "cartoon"), style_lock)
    asset_ids = []
    total_cost = Decimal("0")

    for shot in shots:
        idx = shot["index"]

        # 1. DALL-E image (skip if already exists)
        img_path = shot_image_path(run_date, idx)
        dalle_prompt = shot.get("dalle_prompt", "")
        text_overlay = shot.get("text_overlay")
        cost = Decimal("0")
        if img_path.exists():
            print(f"    shot {idx}: image already exists, skipping DALL-E")
        else:
            try:
                print(f"    DALL-E shot {idx}...")
                _, cost, meta = generate_image_with_text_guard(
                    prompt=dalle_prompt,
                    style_prefix=style_prefix,
                    text_overlay=text_overlay,
                    output_path=img_path,
                )
                total_cost += cost
            except Exception as e:
                print(f"    [warn] DALL-E shot {idx} failed: {e} — using placeholder")
                from app.agents.asset_generator import _create_placeholder_image
                _create_placeholder_image(img_path)

        # 2. Ken Burns clip (static fallback — fast, skip if exists)
        clip_path = shot_video_path(run_date, idx)
        if clip_path.exists():
            print(f"    shot {idx}: clip already exists, skipping")
        else:
            try:
                _create_static_clip(img_path, clip_path, shot["duration_s"])
            except Exception as e:
                print(f"    [warn] clip shot {idx}: {e}")

        aid = str(uuid.uuid4())
        asset = _Row("assets", id=aid, run_id=run_id, asset_type="image",
                     shot_index=idx, file_path=str(img_path), dalle_prompt=dalle_prompt,
                     cost_usd=float(cost))
        store.add(asset)
        asset_ids.append(aid)

    # 3. TTS per shot (skip if exists)
    for shot in shots:
        idx = shot["index"]
        narr_indices = shot.get("narration_indices", [])
        texts = [narration_data[i]["text"] for i in narr_indices if i < len(narration_data)]
        if not texts:
            continue
        full_text = " ".join(texts)
        audio_path = shot_audio_path(run_date, idx)
        cost = Decimal("0")
        if audio_path.exists():
            print(f"    shot {idx}: audio already exists, skipping TTS")
        else:
            try:
                print(f"    TTS shot {idx}: \"{full_text[:50]}...\"")
                audio_bytes, cost = generate_speech(text=full_text, output_path=audio_path)
                total_cost += cost
            except Exception as e:
                print(f"    [warn] TTS shot {idx}: {e}")

        aid = str(uuid.uuid4())
        asset = _Row("assets", id=aid, run_id=run_id, asset_type="audio",
                     shot_index=idx, file_path=str(audio_path), cost_usd=float(cost))
        store.add(asset)
        asset_ids.append(aid)

    run.cost_usd = float(total_cost)
    run.status = "ASSETS_DONE"
    store.persist_run(run)
    return asset_ids


def _run_video_assembly(run_id: str, run: _Row, store: _Store) -> str:
    from app.agents.video_assembler import (
        _assemble_with_moviepy, _get_video_duration,
    )
    from app.storage.artifact_paths import final_video_path, thumbnail_path

    run.status = "ASSEMBLING"
    store.persist_run(run)

    boards = store.find_all("storyboards")
    board = boards[0]
    scripts = store.find_all("scripts")
    script = sorted(scripts, key=lambda r: getattr(r, "revision", 0), reverse=True)[0]

    run_date = str(run.run_date)
    out_video = final_video_path(run_date)
    out_thumb = thumbnail_path(run_date)

    _assemble_with_moviepy(
        run_date=run_date,
        shots=board.raw_json.get("shots", []),
        script_data=script.raw_json,
        out_video=out_video,
        out_thumb=out_thumb,
    )

    duration = _get_video_duration(out_video)
    vid_id = str(uuid.uuid4())
    video = _Row("videos", id=vid_id, run_id=run_id,
                 file_path=str(out_video),
                 thumbnail_path=str(out_thumb),
                 duration_s=duration)
    store.add(video)
    return vid_id


def _run_metadata(run_id: str, run: _Row, store: _Store) -> str:
    import openai
    from app.agents.metadata_agent import METADATA_SYSTEM
    import json as _json

    scripts = store.find_all("scripts")
    script = sorted(scripts, key=lambda r: getattr(r, "revision", 0), reverse=True)[0]
    videos = store.find_all("videos")
    video = videos[0] if videos else None

    title = script.raw_json.get("title", "")
    topic = script.raw_json.get("topic", "")
    narration = script.raw_json.get("narration", [])
    preview = " ".join(n["text"] for n in narration[:3])

    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": METADATA_SYSTEM},
            {"role": "user", "content": f"Title: {title}\nTopic: {topic}\nPreview: {preview[:300]}"},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
    )

    data = _json.loads(resp.choices[0].message.content)
    caption = data.get("caption", title)[:150]
    hashtags = [h.lstrip("#") for h in data.get("hashtags", ["kidslearning"])]

    run_date = str(run.run_date)
    metadata = {
        "run_id": run_id,
        "run_date": run_date,
        "title": title,
        "topic": topic,
        "caption": caption,
        "hashtags": hashtags,
        "video_path": video.file_path if video else None,
        "thumbnail_path": video.thumbnail_path if video else None,
        "duration_s": video.duration_s if video else None,
    }

    jid = str(uuid.uuid4())
    job = _Row("publish_jobs", id=jid, run_id=run_id, mode="C",
               status="PENDING", caption=caption,
               hashtags=json.dumps(hashtags),
               metadata_json=json.dumps(metadata))
    store.add(job)
    return jid


def _run_qa(run_id: str, run: _Row, store: _Store) -> dict:
    from app.services.moderation.openai_moderation import moderate_text
    from app.storage.artifact_paths import final_video_path
    import subprocess

    scripts = store.find_all("scripts")
    script = sorted(scripts, key=lambda r: getattr(r, "revision", 0), reverse=True)[0]
    videos = store.find_all("videos")
    video = videos[0] if videos else None

    failures = []

    # Text moderation
    narration = script.raw_json.get("narration", [])
    full_text = " ".join(n["text"] for n in narration)
    mod = moderate_text(full_text)
    if mod["flagged"]:
        failures.append({"check": "content_moderation", "detail": f"risk={mod['risk_score']}"})

    # Duration
    if video and video.duration_s:
        if video.duration_s < 15:
            failures.append({"check": "duration", "detail": f"Too short: {video.duration_s:.1f}s"})
        elif video.duration_s > 60:
            failures.append({"check": "duration", "detail": f"Too long: {video.duration_s:.1f}s"})

    run_date = str(run.run_date)
    vpath = final_video_path(run_date)
    if vpath.exists():
        try:
            res = subprocess.run(
                ["ffmpeg", "-i", str(vpath), "-af", "volumedetect", "-f", "null", "-"],
                capture_output=True, text=True, timeout=30,
            )
            for line in res.stderr.splitlines():
                if "mean_volume" in line:
                    lufs = float(line.split(":")[1].strip().replace(" dB", ""))
                    if lufs < -30:
                        failures.append({"check": "audio", "detail": f"Too quiet: {lufs:.1f}dB"})
        except Exception:
            pass

    qa_report = {"passed": len(failures) == 0, "failures": failures}
    if video:
        video.qa_passed = 1 if qa_report["passed"] else 0
        video.qa_report = json.dumps(qa_report)

    return qa_report


def _run_publisher(run_id: str, run: _Row, store: _Store) -> str:
    from app.services.tiktok_publish.mode_c import export_package

    jobs = store.find_all("publish_jobs")
    job = jobs[0]
    run_date = str(run.run_date)
    caption = job.caption or ""
    hashtags = json.loads(job.hashtags) if isinstance(job.hashtags, str) else (job.hashtags or [])
    metadata = json.loads(job.metadata_json) if isinstance(job.metadata_json, str) else (job.metadata_json or {})

    export_path = export_package(
        run_date=run_date,
        caption=caption,
        hashtags=hashtags,
        metadata=metadata,
    )

    job.status = "READY_TO_POST"
    job.export_path = export_path
    run.status = "DONE"
    store.persist_run(run)
    return export_path


# ── CLI ───────────────────────────────────────────────────────────────────────

@click.command()
@click.option("--date", "run_date", default=None, help="YYYY-MM-DD (default: today)")
@click.option("--force", is_flag=True, help="Re-run even if output exists")
def main(run_date: str | None, force: bool) -> None:
    """Run the real AI pipeline — requires OPENAI_API_KEY in .env"""

    run_date = run_date or str(date.today())

    if not settings.OPENAI_API_KEY:
        click.echo("ERROR: OPENAI_API_KEY not set in .env", err=True)
        sys.exit(1)

    out_dir = Path(settings.ARTIFACTS_DIR) / run_date
    if (out_dir / "final.mp4").exists() and not force:
        click.echo(f"Output already exists at {out_dir}. Use --force to re-run.")
        sys.exit(0)

    click.echo(f"\n{'='*60}")
    click.echo(f"  Faceless Pipeline — REAL AI RUN")
    click.echo(f"  Date: {run_date}")
    click.echo(f"  Model: GPT-4o + DALL-E 3 + TTS nova")
    click.echo(f"  Output: {out_dir}")
    click.echo(f"{'='*60}\n")

    # Bootstrap SQLite
    engine = create_engine(_SQLITE_URL, connect_args={"check_same_thread": False})
    _bootstrap_db(engine)

    # Clean up stale run for this date if --force
    if force:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM runs WHERE run_date=:d"), {"d": run_date})

    store = _Store(engine)

    # Create run record
    run_id = str(uuid.uuid4())
    run = _Row("runs", id=run_id, run_date=date.fromisoformat(run_date),
               status="PENDING", cost_usd=Decimal("0"))
    store.add(run)
    store.persist_run(run)

    stages = [
        ("Trend Research",    lambda: _run_trend_research(run_id, run, store)),
        ("Topic Selection",   lambda: _run_topic_selection(run_id, run, store)),
        ("Scriptwriter",      lambda: _run_scriptwriter(run_id, run, store)),
        ("Storyboard",        lambda: _run_storyboard(run_id, run, store)),
        ("Asset Generation",  lambda: _run_asset_generation(run_id, run, store)),
        ("Video Assembly",    lambda: _run_video_assembly(run_id, run, store)),
        ("Metadata",          lambda: _run_metadata(run_id, run, store)),
        ("QA",                lambda: _run_qa(run_id, run, store)),
        ("Publisher",         lambda: _run_publisher(run_id, run, store)),
    ]

    for name, fn in stages:
        click.echo(f"[{name}]")
        try:
            result = fn()
            click.echo(f"  ✓ done\n")
        except Exception as e:
            click.echo(f"  ✗ FAILED: {e}", err=True)
            traceback.print_exc()
            sys.exit(1)

    # Summary
    scripts = store.find_all("scripts")
    script = sorted(scripts, key=lambda r: getattr(r, "revision", 0), reverse=True)[0] if scripts else None
    videos = store.find_all("videos")
    video = videos[0] if videos else None

    click.echo(f"\n{'='*60}")
    click.echo(f"  Pipeline complete! Status: {run.status}")
    click.echo(f"{'='*60}")
    click.echo(f"  Topic:     {store.find_first('topics', is_selected=1).title if store.find_first('topics', is_selected=1) else '?'}")
    if script:
        click.echo(f"  Title:     {script.raw_json.get('title', '?')}")
    if video:
        click.echo(f"  Duration:  {video.duration_s:.1f}s")
    click.echo(f"  Cost:      ~${float(run.cost_usd):.3f} USD")
    click.echo(f"\n  Output files in: {out_dir}/")
    click.echo(f"    final.mp4")
    click.echo(f"    thumbnail.jpg")
    click.echo(f"    caption.txt")
    click.echo(f"    hashtags.txt")
    click.echo(f"    metadata.json")
    click.echo(f"\n  To play: ffplay {out_dir}/final.mp4")
    click.echo(f"{'='*60}\n")


if __name__ == "__main__":
    main()
