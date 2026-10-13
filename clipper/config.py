"""Runtime settings, read from environment variables (and the repo's .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = Path(__file__).resolve().parent
load_dotenv(REPO_ROOT / ".env")


def _env(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    campaigns_file: Path
    timezone: ZoneInfo
    slots: tuple[str, ...]
    clips_per_day: int
    min_score: float
    min_free_gb: float
    whisper_model: str
    claude_bin: str
    claude_model: str | None
    allowed_account_ids: frozenset[str]
    api_key: str | None
    open_report: bool
    transcript_keep_days: int
    max_post_attempts: int

    @property
    def db_path(self) -> Path:
        return self.data_dir / "clipper.db"

    def subdir(self, name: str) -> Path:
        path = self.data_dir / name
        path.mkdir(parents=True, exist_ok=True)
        return path


def load_settings() -> Settings:
    data_dir = Path(_env("CLIPPER_DATA_DIR", str(Path.home() / "clipper-data"))).expanduser()
    data_dir.mkdir(parents=True, exist_ok=True)
    allowed = frozenset(
        x.strip() for x in os.environ.get("POSTFORME_ALLOWED_ACCOUNT_IDS", "").split(",") if x.strip()
    )
    slots = tuple(s.strip() for s in _env("CLIPPER_SLOTS", "08:15,12:15,17:15").split(",") if s.strip())
    return Settings(
        data_dir=data_dir,
        campaigns_file=Path(_env("CLIPPER_CAMPAIGNS_FILE", str(PACKAGE_DIR / "campaigns.yaml"))),
        timezone=ZoneInfo(_env("CLIPPER_TIMEZONE", "Africa/Lagos")),
        slots=slots,
        clips_per_day=int(_env("CLIPPER_CLIPS_PER_DAY", "3")),
        min_score=float(_env("CLIPPER_MIN_SCORE", "7")),
        min_free_gb=float(_env("CLIPPER_MIN_FREE_GB", "5")),
        whisper_model=_env("CLIPPER_WHISPER_MODEL", "small"),
        claude_bin=_env("CLIPPER_CLAUDE_BIN", "claude"),
        claude_model=os.environ.get("CLIPPER_CLAUDE_MODEL", "").strip() or None,
        allowed_account_ids=allowed,
        api_key=os.environ.get("POSTFORME_API_KEY", "").strip() or None,
        open_report=_env("CLIPPER_OPEN_REPORT", "1") == "1",
        transcript_keep_days=int(_env("CLIPPER_TRANSCRIPT_KEEP_DAYS", "45")),
        max_post_attempts=int(_env("CLIPPER_MAX_POST_ATTEMPTS", "3")),
    )
