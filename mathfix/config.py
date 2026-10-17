"""Settings from environment variables and the YAML config files."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path) -> None:
    """Minimal .env loader: KEY=value lines; existing env vars win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


@dataclass
class Settings:
    bot_token: str
    mode: str                       # "polling" (local dev) or "webhook" (server)
    webhook_base_url: str
    webhook_secret: str
    port: int
    database_path: Path
    admin_user_ids: set[int]
    admin_chat_id: int | None
    log_level: str
    models: dict = field(default_factory=dict)
    limits: dict = field(default_factory=dict)

    @property
    def reset_tz(self) -> ZoneInfo:
        return ZoneInfo(self.limits.get("reset_timezone", "UTC"))

    def user_day(self, now: datetime | None = None) -> str:
        """Day key for per-user limits, in the configured reset timezone."""
        now = now or datetime.now(timezone.utc)
        return now.astimezone(self.reset_tz).date().isoformat()

    def seconds_to_reset(self, now: datetime | None = None) -> int:
        now = (now or datetime.now(timezone.utc)).astimezone(self.reset_tz)
        midnight = datetime.combine(now.date() + timedelta(days=1), time.min, self.reset_tz)
        return max(0, int((midnight - now).total_seconds()))


def _ids(raw: str) -> set[int]:
    return {int(x) for x in raw.replace(" ", "").split(",") if x}


def load_settings(env_file: Path | None = None) -> Settings:
    load_dotenv(env_file or ROOT / ".env")
    models = yaml.safe_load((ROOT / os.environ.get("MODELS_CONFIG", "config/models.yaml")).read_text())
    limits = yaml.safe_load((ROOT / os.environ.get("LIMITS_CONFIG", "config/limits.yaml")).read_text())
    admin_chat = os.environ.get("ADMIN_CHAT_ID", "").strip()
    return Settings(
        bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        mode=os.environ.get("MODE", "polling"),
        webhook_base_url=os.environ.get("WEBHOOK_BASE_URL", "").rstrip("/"),
        webhook_secret=os.environ.get("TELEGRAM_WEBHOOK_SECRET", ""),
        port=int(os.environ.get("PORT", "8080")),
        database_path=Path(os.environ.get("DATABASE_PATH", str(ROOT / "data" / "mathfix.db"))),
        admin_user_ids=_ids(os.environ.get("ADMIN_USER_IDS", "")),
        admin_chat_id=int(admin_chat) if admin_chat else None,
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        models=models,
        limits=limits,
    )
