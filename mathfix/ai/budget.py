"""Per-model free-tier budgets: requests/tokens per minute and per day, plus Cloudflare neurons.

The router asks `has_room()` BEFORE calling a model, so we skip a model that is about to hit its
limit instead of waiting on a 429. Daily counters are stored in SQLite (provider_usage) so they
survive restarts; per-minute windows live in memory.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

SAFETY = 1.0  # limits in models.yaml are already "console number x 0.9"


@dataclass
class ModelSpec:
    name: str
    provider: str
    id: str
    base_url: str
    api_key: str
    vision: bool = False
    json_mode: bool = False
    reasoning_effort: bool = False
    max_tokens: int = 1500
    max_tokens_big: int = 0      # output room for big problems (0 = same as max_tokens)
    limits: dict = field(default_factory=dict)
    neurons_in: float = 0.0      # neurons per token
    neurons_out: float = 0.0
    pool: str | None = None      # shared daily pool (e.g. all Cloudflare models)
    allow_paid: bool = False     # OpenRouter: allow a model that isn't ":free" (it would be billed)

    @property
    def paid_risk(self) -> bool:
        """An OpenRouter model that is not a free variant would spend account credit."""
        return (self.provider == "openrouter" and "<" not in self.id and not self.id.endswith(":free")
                and not self.allow_paid)

    @property
    def enabled(self) -> bool:
        return bool(self.api_key) and "<" not in self.id and "{" not in self.base_url and not self.paid_risk

    def neurons(self, tokens_in: int, tokens_out: int) -> float:
        return tokens_in * self.neurons_in + tokens_out * self.neurons_out


def utc_day() -> str:
    return datetime.now(timezone.utc).date().isoformat()


class Budget:
    def __init__(self, pools: dict[str, dict] | None = None, clock=time.monotonic):
        self.clock = clock
        self.pools = pools or {}                  # name -> {"neurons_per_day": n}
        self.day = utc_day()
        self.today: dict[str, dict] = defaultdict(lambda: {"requests": 0, "tokens": 0, "neurons": 0.0})
        self.minute: dict[str, deque] = defaultdict(deque)   # (t, tokens)
        self.cooldown_until: dict[str, float] = {}
        self._pool_of: dict[str, str] = {}        # model name -> shared pool name

    def load(self, day: str, rows: dict[str, dict]) -> None:
        self.day = day
        self.today.clear()
        for model, r in rows.items():
            self.today[model] = {"requests": r["requests"], "tokens": r["tokens_in"] + r["tokens_out"],
                                 "neurons": r["neurons"]}

    def _roll_day(self) -> None:
        day = utc_day()
        if day != self.day:
            self.day = day
            self.today.clear()

    def _minute(self, name: str) -> deque:
        q, now = self.minute[name], self.clock()
        while q and now - q[0][0] > 60:
            q.popleft()
        return q

    def _pool_neurons(self, pool: str) -> float:
        return sum(v["neurons"] for k, v in self.today.items() if self._pool_of.get(k) == pool)

    def register(self, spec: ModelSpec) -> None:
        if spec.pool:
            self._pool_of[spec.name] = spec.pool

    def has_room(self, spec: ModelSpec, est_tokens: int) -> tuple[bool, str | None]:
        """(ok, reason) where reason is 'day' (wait until tomorrow) or 'minute' (wait a few seconds)."""
        self._roll_day()
        lim, t = spec.limits, self.today[spec.name]
        est_neurons = spec.neurons(int(est_tokens * 0.6), int(est_tokens * 0.4))
        if "rpd" in lim and t["requests"] + 1 > lim["rpd"] * SAFETY:
            return False, "day"
        if "tpd" in lim and t["tokens"] + est_tokens > lim["tpd"] * SAFETY:
            return False, "day"
        if "neurons_per_day" in lim and t["neurons"] + est_neurons > lim["neurons_per_day"] * SAFETY:
            return False, "day"
        if spec.pool and spec.pool in self.pools:
            if self._pool_neurons(spec.pool) + est_neurons > self.pools[spec.pool]["neurons_per_day"] * SAFETY:
                return False, "day"
        q = self._minute(spec.name)
        if "rpm" in lim and len(q) + 1 > lim["rpm"]:
            return False, "minute"
        if "tpm" in lim and sum(x[1] for x in q) + est_tokens > lim["tpm"]:
            return False, "minute"
        return True, None

    def record(self, spec: ModelSpec, tokens_in: int, tokens_out: int) -> float:
        self._roll_day()
        neurons = spec.neurons(tokens_in, tokens_out)
        t = self.today[spec.name]
        t["requests"] += 1
        t["tokens"] += tokens_in + tokens_out
        t["neurons"] += neurons
        self._minute(spec.name).append((self.clock(), tokens_in + tokens_out))
        return neurons

    def cool(self, name: str, seconds: float) -> None:
        self.cooldown_until[name] = self.clock() + seconds

    def cooling(self, name: str) -> float:
        """Seconds of cooldown left (0 if available)."""
        return max(0.0, self.cooldown_until.get(name, 0) - self.clock())

    def fraction_used(self, spec: ModelSpec) -> float:
        self._roll_day()
        lim, t = spec.limits, self.today[spec.name]
        parts = [0.0]
        if lim.get("rpd"):
            parts.append(t["requests"] / lim["rpd"])
        if lim.get("tpd"):
            parts.append(t["tokens"] / lim["tpd"])
        if lim.get("neurons_per_day"):
            parts.append(t["neurons"] / lim["neurons_per_day"])
        if spec.pool and spec.pool in self.pools:
            parts.append(self._pool_neurons(spec.pool) / self.pools[spec.pool]["neurons_per_day"])
        return min(1.0, max(parts))

    def daily_capacity(self, spec: ModelSpec, est_tokens: int) -> float:
        """How many calls of `est_tokens` this model can make per day (for the capacity guard)."""
        lim = spec.limits
        caps = []
        if lim.get("rpd"):
            caps.append(lim["rpd"])
        if lim.get("tpd"):
            caps.append(lim["tpd"] / max(1, est_tokens))
        npd = lim.get("neurons_per_day")
        if npd:
            caps.append(npd / max(1e-9, spec.neurons(int(est_tokens * 0.6), int(est_tokens * 0.4))))
        return min(caps) if caps else 1000.0
