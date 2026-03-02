"""Artifact manager — save and load files for a run."""
import json
import shutil
from pathlib import Path
from typing import Any

from app.utils.logging import get_logger

log = get_logger(__name__)


class LocalStorage:
    """Simple wrapper around the local filesystem for pipeline artifacts."""

    def __init__(self, base_dir: str | Path) -> None:
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)

    # ── Bytes / binary ────────────────────────────────────────────────────────

    def save_bytes(self, relative_path: str, data: bytes) -> Path:
        dest = self.base / relative_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        log.debug("storage.saved", path=str(dest), size=len(data))
        return dest

    def load_bytes(self, relative_path: str) -> bytes:
        return (self.base / relative_path).read_bytes()

    # ── JSON ──────────────────────────────────────────────────────────────────

    def save_json(self, relative_path: str, obj: Any) -> Path:
        dest = self.base / relative_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(obj, indent=2, default=str))
        return dest

    def load_json(self, relative_path: str) -> Any:
        return json.loads((self.base / relative_path).read_text())

    # ── Text ──────────────────────────────────────────────────────────────────

    def save_text(self, relative_path: str, text: str) -> Path:
        dest = self.base / relative_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        return dest

    # ── Copy ─────────────────────────────────────────────────────────────────

    def copy_file(self, src: Path, relative_dest: str) -> Path:
        dest = self.base / relative_dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return dest

    # ── Existence ─────────────────────────────────────────────────────────────

    def exists(self, relative_path: str) -> bool:
        return (self.base / relative_path).exists()

    def path(self, relative_path: str) -> Path:
        return self.base / relative_path
