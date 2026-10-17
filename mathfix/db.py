"""SQLite storage (one file, WAL mode). Photos are never stored."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiosqlite

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS users (
  user_id        INTEGER PRIMARY KEY,
  username       TEXT,
  first_name     TEXT,
  lang           TEXT DEFAULT 'en',
  tutor_mode     INTEGER DEFAULT 0,
  start_source   TEXT,
  is_banned      INTEGER DEFAULT 0,
  created_at     TEXT NOT NULL,
  last_seen_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usage_daily (
  user_id         INTEGER NOT NULL,
  day             TEXT    NOT NULL,
  solves_used     INTEGER DEFAULT 0,
  solves_reserved INTEGER DEFAULT 0,
  tutor_used      INTEGER DEFAULT 0,
  tutor_reserved  INTEGER DEFAULT 0,
  bonus_solves    INTEGER DEFAULT 0,
  refunds         INTEGER DEFAULT 0,
  PRIMARY KEY (user_id, day)
);

CREATE TABLE IF NOT EXISTS provider_usage (
  day            TEXT NOT NULL,
  model          TEXT NOT NULL,
  requests       INTEGER DEFAULT 0,
  tokens_in      INTEGER DEFAULT 0,
  tokens_out     INTEGER DEFAULT 0,
  neurons        REAL    DEFAULT 0,
  errors_429     INTEGER DEFAULT 0,
  errors_other   INTEGER DEFAULT 0,
  latency_ms_sum INTEGER DEFAULT 0,
  PRIMARY KEY (day, model)
);

CREATE TABLE IF NOT EXISTS solutions (
  id             INTEGER PRIMARY KEY,
  problem_key    TEXT NOT NULL,
  problem_text   TEXT NOT NULL,
  problem_latex  TEXT,
  topic          TEXT,
  difficulty     INTEGER,
  solution_json  TEXT NOT NULL,
  verified       TEXT NOT NULL,
  model_used     TEXT NOT NULL,
  latency_ms     INTEGER,
  wrong_reports  INTEGER DEFAULT 0,
  flagged        INTEGER DEFAULT 0,
  image_file_id  TEXT,
  created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_solutions_key ON solutions(problem_key);

CREATE TABLE IF NOT EXISTS image_cache (
  phash          TEXT PRIMARY KEY,
  solution_id    INTEGER NOT NULL,
  problems_json  TEXT,
  created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tutor_turns (
  id             INTEGER PRIMARY KEY,
  user_id        INTEGER NOT NULL,
  solution_id    INTEGER,
  role           TEXT NOT NULL,
  text           TEXT NOT NULL,
  created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tutor_user ON tutor_turns(user_id, solution_id);

CREATE TABLE IF NOT EXISTS events (
  id             INTEGER PRIMARY KEY,
  user_id        INTEGER,
  name           TEXT NOT NULL,
  props_json     TEXT,
  created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_day ON events(created_at);

CREATE TABLE IF NOT EXISTS settings (
  key            TEXT PRIMARY KEY,
  value          TEXT NOT NULL
);
"""

# Columns added after the first release. init() adds any that are missing, so an existing
# data/mathfix.db upgrades in place without losing data.
USER_COLUMNS = {
    "grade": "TEXT",                         # class band chosen at onboarding, e.g. "9-10"
    "explain_lang": "TEXT DEFAULT 'en'",     # en | hinglish
    "plan": "TEXT DEFAULT 'free'",           # free | premium (premium not sold yet)
    "onboarded": "INTEGER DEFAULT 0",
    "referred_by": "INTEGER",
    "ref_rewarded": "INTEGER DEFAULT 0",     # referrer already rewarded for this user
    "total_solves": "INTEGER DEFAULT 0",
    "streak": "INTEGER DEFAULT 0",
    "best_streak": "INTEGER DEFAULT 0",
    "last_solve_day": "TEXT",
}
PROFILE_FIELDS = {"grade", "explain_lang", "plan", "onboarded", "tutor_mode", "is_banned"}

# column names are fixed here, never taken from user input
_KIND_COLS = {"solves": ("solves_used", "solves_reserved"), "tutor": ("tutor_used", "tutor_reserved")}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Repo:
    def __init__(self, path: Path | str):
        self.path = str(path)
        self.db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = await aiosqlite.connect(self.path)
        self.db.row_factory = aiosqlite.Row
        await self.db.executescript(SCHEMA)
        cur = await self.db.execute("PRAGMA table_info(users)")
        have = {r[1] for r in await cur.fetchall()}
        for col, decl in USER_COLUMNS.items():
            if col not in have:
                await self.db.execute(f"ALTER TABLE users ADD COLUMN {col} {decl}")
        # crash recovery: reservations never survive a restart
        await self.db.execute("UPDATE usage_daily SET solves_reserved = 0, tutor_reserved = 0")
        await self.db.commit()

    async def close(self) -> None:
        if self.db:
            await self.db.close()

    async def ping(self) -> bool:
        cur = await self.db.execute("SELECT 1")
        return (await cur.fetchone())[0] == 1

    # ---------- users ----------
    async def upsert_user(self, user_id: int, username: str | None, first_name: str | None,
                          lang: str | None, start_source: str | None = None) -> bool:
        """Returns True if this is a new user."""
        now = now_iso()
        cur = await self.db.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        exists = await cur.fetchone() is not None
        if exists:
            await self.db.execute(
                "UPDATE users SET username = ?, first_name = ?, last_seen_at = ? WHERE user_id = ?",
                (username, first_name, now, user_id))
        else:
            await self.db.execute(
                "INSERT INTO users(user_id, username, first_name, lang, start_source, created_at, last_seen_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, username, first_name, (lang or "en")[:2], start_source, now, now))
        await self.db.commit()
        return not exists

    async def get_user(self, user_id: int) -> dict | None:
        cur = await self.db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def set_user_flag(self, user_id: int, column: str, value) -> None:
        if column not in PROFILE_FIELDS:
            raise ValueError(column)
        await self.db.execute(f"UPDATE users SET {column} = ? WHERE user_id = ?", (value, user_id))
        await self.db.commit()

    async def set_referrer(self, user_id: int, referrer_id: int) -> bool:
        """Only for brand-new users, never self-referral, never overwritten."""
        if user_id == referrer_id:
            return False
        cur = await self.db.execute(
            "UPDATE users SET referred_by = ? WHERE user_id = ? AND referred_by IS NULL AND total_solves = 0"
            " AND EXISTS (SELECT 1 FROM users WHERE user_id = ?)", (referrer_id, user_id, referrer_id))
        await self.db.commit()
        return cur.rowcount == 1

    async def record_solve(self, user_id: int, day: str, yesterday: str) -> dict:
        """Update total solves and the daily streak. Returns the user's new numbers."""
        u = await self.get_user(user_id) or {}
        last = u.get("last_solve_day")
        streak = u.get("streak") or 0
        if last != day:
            streak = streak + 1 if last == yesterday else 1
        best = max(u.get("best_streak") or 0, streak)
        await self.db.execute(
            "UPDATE users SET total_solves = total_solves + 1, streak = ?, best_streak = ?, last_solve_day = ?"
            " WHERE user_id = ?", (streak, best, day, user_id))
        await self.db.commit()
        return {"total_solves": (u.get("total_solves") or 0) + 1, "streak": streak, "best_streak": best,
                "first_solve": not (u.get("total_solves") or 0), "new_day": last != day}

    async def claim_referral(self, user_id: int) -> int | None:
        """Mark this user's referral as rewarded (once). Returns the referrer id to reward, if any."""
        cur = await self.db.execute(
            "UPDATE users SET ref_rewarded = 1 WHERE user_id = ? AND referred_by IS NOT NULL AND ref_rewarded = 0"
            " RETURNING referred_by", (user_id,))
        row = await cur.fetchone()
        await self.db.commit()
        return row[0] if row else None

    async def count_events(self, user_id: int, name: str, since_iso: str) -> int:
        cur = await self.db.execute("SELECT COUNT(*) FROM events WHERE user_id = ? AND name = ? AND created_at >= ?",
                                    (user_id, name, since_iso))
        return (await cur.fetchone())[0]

    async def referral_count(self, user_id: int) -> int:
        cur = await self.db.execute("SELECT COUNT(*) FROM users WHERE referred_by = ? AND ref_rewarded = 1", (user_id,))
        return (await cur.fetchone())[0]

    async def delete_user(self, user_id: int) -> None:
        for table in ("users", "usage_daily", "tutor_turns", "events"):
            await self.db.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
        await self.db.commit()

    # ---------- daily usage (reserve -> finish) ----------
    async def reserve(self, user_id: int, day: str, kind: str, limit: int) -> bool:
        """Atomically reserve one unit if used + reserved < limit (limit already includes any bonus)."""
        used, reserved = _KIND_COLS[kind]
        await self.db.execute(
            "INSERT OR IGNORE INTO usage_daily(user_id, day) VALUES (?, ?)", (user_id, day))
        cur = await self.db.execute(
            f"UPDATE usage_daily SET {reserved} = {reserved} + 1"
            f" WHERE user_id = ? AND day = ? AND {used} + {reserved} < ?",
            (user_id, day, limit))
        await self.db.commit()
        return cur.rowcount == 1

    async def finish(self, user_id: int, day: str, kind: str, counted: bool) -> None:
        used, reserved = _KIND_COLS[kind]
        await self.db.execute(
            f"UPDATE usage_daily SET {reserved} = MAX({reserved} - 1, 0), {used} = {used} + ?"
            " WHERE user_id = ? AND day = ?", (1 if counted else 0, user_id, day))
        await self.db.commit()

    async def refund_solve(self, user_id: int, day: str, max_refunds: int) -> bool:
        cur = await self.db.execute(
            "UPDATE usage_daily SET solves_used = solves_used - 1, refunds = refunds + 1"
            " WHERE user_id = ? AND day = ? AND solves_used > 0 AND refunds < ?",
            (user_id, day, max_refunds))
        await self.db.commit()
        return cur.rowcount == 1

    async def grant(self, user_id: int, day: str, n: int) -> None:
        await self.db.execute("INSERT OR IGNORE INTO usage_daily(user_id, day) VALUES (?, ?)", (user_id, day))
        await self.db.execute("UPDATE usage_daily SET bonus_solves = bonus_solves + ? WHERE user_id = ? AND day = ?",
                              (n, user_id, day))
        await self.db.commit()

    async def usage(self, user_id: int, day: str) -> dict:
        cur = await self.db.execute("SELECT * FROM usage_daily WHERE user_id = ? AND day = ?", (user_id, day))
        row = await cur.fetchone()
        return dict(row) if row else {"solves_used": 0, "tutor_used": 0, "bonus_solves": 0, "refunds": 0,
                                      "solves_reserved": 0, "tutor_reserved": 0}

    # ---------- provider usage ----------
    async def record_provider(self, day: str, model: str, *, tokens_in: int = 0, tokens_out: int = 0,
                              neurons: float = 0, ok: bool = True, rate_limited: bool = False,
                              latency_ms: int = 0) -> None:
        await self.db.execute("INSERT OR IGNORE INTO provider_usage(day, model) VALUES (?, ?)", (day, model))
        await self.db.execute(
            "UPDATE provider_usage SET requests = requests + 1, tokens_in = tokens_in + ?, tokens_out = tokens_out + ?,"
            " neurons = neurons + ?, errors_429 = errors_429 + ?, errors_other = errors_other + ?,"
            " latency_ms_sum = latency_ms_sum + ? WHERE day = ? AND model = ?",
            (tokens_in, tokens_out, neurons, int(rate_limited), int(not ok and not rate_limited),
             latency_ms, day, model))
        await self.db.commit()

    async def provider_day(self, day: str) -> dict[str, dict]:
        cur = await self.db.execute("SELECT * FROM provider_usage WHERE day = ?", (day,))
        return {r["model"]: dict(r) for r in await cur.fetchall()}

    # ---------- solutions / cache ----------
    async def find_solution(self, problem_key: str) -> dict | None:
        cur = await self.db.execute(
            "SELECT * FROM solutions WHERE problem_key = ? AND flagged = 0 AND wrong_reports < 2"
            " AND verified != 'failed' ORDER BY id DESC LIMIT 1", (problem_key,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def add_solution(self, *, problem_key: str, problem_text: str, problem_latex: str, topic: str,
                           difficulty: int, solution_json: str, verified: str, model_used: str,
                           latency_ms: int) -> int:
        cur = await self.db.execute(
            "INSERT INTO solutions(problem_key, problem_text, problem_latex, topic, difficulty, solution_json,"
            " verified, model_used, latency_ms, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (problem_key, problem_text, problem_latex, topic, difficulty, solution_json, verified,
             model_used, latency_ms, now_iso()))
        await self.db.commit()
        return cur.lastrowid

    async def get_solution(self, solution_id: int) -> dict | None:
        cur = await self.db.execute("SELECT * FROM solutions WHERE id = ?", (solution_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def set_image_file_id(self, solution_id: int, file_id: str) -> None:
        await self.db.execute("UPDATE solutions SET image_file_id = ? WHERE id = ?", (file_id, solution_id))
        await self.db.commit()

    async def report_wrong(self, solution_id: int) -> None:
        await self.db.execute("UPDATE solutions SET wrong_reports = wrong_reports + 1 WHERE id = ?", (solution_id,))
        await self.db.commit()

    async def flag_solution(self, solution_id: int) -> bool:
        cur = await self.db.execute("UPDATE solutions SET flagged = 1 WHERE id = ?", (solution_id,))
        await self.db.commit()
        return cur.rowcount == 1

    async def get_image(self, phash: str) -> dict | None:
        cur = await self.db.execute("SELECT * FROM image_cache WHERE phash = ?", (phash,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def put_image(self, phash: str, solution_id: int, problems: list[str]) -> None:
        await self.db.execute(
            "INSERT OR REPLACE INTO image_cache(phash, solution_id, problems_json, created_at) VALUES (?, ?, ?, ?)",
            (phash, solution_id, json.dumps(problems), now_iso()))
        await self.db.commit()

    # ---------- tutor ----------
    async def add_turn(self, user_id: int, solution_id: int, role: str, text: str) -> None:
        await self.db.execute(
            "INSERT INTO tutor_turns(user_id, solution_id, role, text, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, solution_id, role, text[:2000], now_iso()))
        await self.db.commit()

    async def recent_turns(self, user_id: int, solution_id: int, n: int = 6) -> list[dict]:
        cur = await self.db.execute(
            "SELECT role, text FROM tutor_turns WHERE user_id = ? AND solution_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, solution_id, n))
        return [dict(r) for r in reversed(await cur.fetchall())]

    async def prune(self) -> None:
        """Retention from docs/08: tutor turns 7 days, events 90 days, usage 90 days."""
        now = datetime.now(timezone.utc)
        week = (now - timedelta(days=7)).isoformat(timespec="seconds")
        quarter = (now - timedelta(days=90)).isoformat(timespec="seconds")
        await self.db.execute("DELETE FROM tutor_turns WHERE created_at < ?", (week,))
        await self.db.execute("DELETE FROM events WHERE created_at < ?", (quarter,))
        await self.db.execute("DELETE FROM usage_daily WHERE day < ?", (quarter[:10],))
        await self.db.commit()

    # ---------- events, settings, stats ----------
    async def event(self, user_id: int | None, name: str, **props: Any) -> None:
        await self.db.execute("INSERT INTO events(user_id, name, props_json, created_at) VALUES (?, ?, ?, ?)",
                              (user_id, name, json.dumps(props) if props else None, now_iso()))
        await self.db.commit()

    async def get_setting(self, key: str) -> str | None:
        cur = await self.db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cur.fetchone()
        return row[0] if row else None

    async def set_setting(self, key: str, value: str) -> None:
        await self.db.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)", (key, value))
        await self.db.commit()

    async def stats(self, since_iso: str) -> dict:
        cur = await self.db.execute(
            "SELECT name, COUNT(*) AS n, COUNT(DISTINCT user_id) AS users FROM events"
            " WHERE created_at >= ? GROUP BY name", (since_iso,))
        by_event = {r["name"]: {"n": r["n"], "users": r["users"]} for r in await cur.fetchall()}
        cur = await self.db.execute("SELECT COUNT(DISTINCT user_id) FROM events WHERE created_at >= ?", (since_iso,))
        active = (await cur.fetchone())[0]
        cur = await self.db.execute(
            "SELECT verified, COUNT(*) AS n, AVG(latency_ms) AS ms FROM solutions WHERE created_at >= ?"
            " GROUP BY verified", (since_iso,))
        by_verified = {r["verified"]: {"n": r["n"], "avg_ms": int(r["ms"] or 0)} for r in await cur.fetchall()}
        return {"active_users": active, "events": by_event, "solutions": by_verified}
