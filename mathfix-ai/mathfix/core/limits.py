"""Per-user daily limits, burst protection and the global capacity guard (docs/05-daily-limits.md)."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass

from ..ai.router import Router
from ..config import Settings
from ..db import Repo

UNLIMITED = 10**6


@dataclass
class Reservation:
    user_id: int
    day: str
    kind: str       # "solves" | "tutor"


class Limits:
    def __init__(self, settings: Settings, repo: Repo, router: Router, clock=time.monotonic):
        self.s = settings
        self.repo = repo
        self.router = router
        self.clock = clock
        self.cfg = settings.limits
        self._in_flight: dict[int, int] = defaultdict(int)
        self._recent: dict[int, deque] = defaultdict(deque)

    # ---------- burst ----------
    def begin(self, user_id: int) -> bool:
        """One request at a time and at most N per minute. Call end() in a finally block."""
        burst = self.cfg.get("burst", {})
        q, now = self._recent[user_id], self.clock()
        while q and now - q[0] > 60:
            q.popleft()
        if self._in_flight[user_id] >= burst.get("max_in_flight", 1) or len(q) >= burst.get("max_per_minute", 5):
            return False
        self._in_flight[user_id] += 1
        q.append(now)
        return True

    def end(self, user_id: int) -> None:
        self._in_flight[user_id] = max(0, self._in_flight[user_id] - 1)

    # ---------- capacity guard ----------
    async def guard_mode(self) -> str:
        forced = await self.repo.get_setting("guard_mode")
        if forced in ("normal", "soft", "hard"):
            return forced
        g = self.cfg.get("capacity_guard", {})
        used = self.router.pool_used("solve")
        if used >= g.get("hard_at", 0.98):
            return "hard"
        if used >= g.get("soft_at", 0.85):
            return "soft"
        return "normal"

    async def base_limit(self, kind: str) -> int:
        override = await self.repo.get_setting(f"limit_{kind}")
        if override is not None:
            return int(override)
        return int(self.cfg.get("per_user_daily", {}).get(kind, 0))

    async def effective_limit(self, user_id: int, kind: str) -> int:
        if user_id in self.s.admin_user_ids:
            return UNLIMITED
        user = await self.repo.get_user(user_id)
        if user and user["is_banned"]:
            return 0
        mode = await self.guard_mode()
        limit = await self.base_limit(kind)
        if mode == "soft":
            limit = min(limit, int(self.cfg["capacity_guard"]["soft_limits"].get(kind, limit)))
        if mode == "hard" and kind == "solves":
            return 0
        if kind == "solves":
            limit += (await self.repo.usage(user_id, self.s.user_day()))["bonus_solves"]
        return limit

    # ---------- reserve -> finish ----------
    async def reserve(self, user_id: int, kind: str) -> tuple[Reservation | None, str | None]:
        """Returns (reservation, None) or (None, reason) with reason in banned | limit | capacity."""
        day = self.s.user_day()
        limit = await self.effective_limit(user_id, kind)
        if limit == 0:
            user = await self.repo.get_user(user_id)
            return None, "banned" if user and user["is_banned"] else "capacity"
        if not await self.repo.reserve(user_id, day, kind, limit):
            mode = await self.guard_mode()
            return None, "capacity" if mode == "soft" else "limit"
        return Reservation(user_id, day, kind), None

    async def finish(self, r: Reservation, counted: bool) -> None:
        await self.repo.finish(r.user_id, r.day, r.kind, counted)

    async def refund_wrong(self, user_id: int) -> bool:
        return await self.repo.refund_solve(user_id, self.s.user_day(),
                                            int(self.cfg.get("wrong_report_refunds_per_day", 3)))

    async def status(self, user_id: int) -> dict:
        u = await self.repo.usage(user_id, self.s.user_day())
        solves = await self.effective_limit(user_id, "solves")
        tutor = await self.effective_limit(user_id, "tutor")
        return {"solves_left": max(0, solves - u["solves_used"]), "solves_limit": solves,
                "tutor_left": max(0, tutor - u["tutor_used"]), "tutor_limit": tutor,
                "reset_in_s": self.s.seconds_to_reset(), "mode": await self.guard_mode()}
