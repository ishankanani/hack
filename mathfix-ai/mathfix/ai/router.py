"""Picks a model for each step and makes the most of every free tier.

For each request the router walks the step's model list (config/models.yaml) and uses the first
model that is enabled, can handle the input (vision), is not cooling down after an error and has
budget left. Per-minute limits make it wait briefly (the student sees "busy, you're in line");
daily limits make it move on. Bad JSON gets one retry on the same model, then the next model.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

import httpx
from pydantic import BaseModel, ValidationError

from ..db import Repo
from . import prompts
from .budget import Budget, ModelSpec, utc_day

log = logging.getLogger(__name__)


class AllModelsBusy(Exception):
    """No model can take the request now (daily budgets spent, or still busy after the queue wait)."""

    def __init__(self, daily: bool):
        super().__init__("daily budget exhausted" if daily else "busy")
        self.daily = daily


class _RateLimited(Exception):
    def __init__(self, retry_after: float):
        self.retry_after = retry_after


class _Transient(Exception):
    pass


class _BadRequest(Exception):
    pass


class _BadOutput(Exception):
    pass


@dataclass
class Result:
    data: BaseModel | str
    model: str
    latency_ms: int


def extract_json(text: str) -> dict:
    """Models sometimes wrap JSON in ``` fences or add a sentence; take the outermost {...}."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise _BadOutput("no JSON object found")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        raise _BadOutput(f"invalid JSON: {e.msg}") from None


def build_specs(cfg: dict) -> dict[str, ModelSpec]:
    specs = {}
    pool_of = {m: name for name, p in (cfg.get("shared_pools") or {}).items() for m in p.get("models", [])}
    for name, m in cfg["models"].items():
        prov = cfg["providers"][m["provider"]]
        base_url = prov["base_url"]
        for var in re.findall(r"\{(\w+)\}", base_url):
            if os.environ.get(var):
                base_url = base_url.replace("{" + var + "}", os.environ[var])
        n = m.get("neurons_per_m_tokens") or {}
        specs[name] = ModelSpec(
            name=name, provider=m["provider"], id=str(m["id"]), base_url=base_url.rstrip("/"),
            api_key=os.environ.get(prov["api_key_env"], ""), vision=bool(m.get("vision")),
            json_mode=bool(m.get("json_mode")), reasoning_effort=bool(m.get("reasoning_effort")),
            max_tokens=int(m.get("max_tokens", 1500)), limits=dict(m.get("limits") or {}),
            neurons_in=n.get("input", 0) / 1e6, neurons_out=n.get("output", 0) / 1e6, pool=pool_of.get(name))
    return specs


class Router:
    def __init__(self, cfg: dict, repo: Repo | None = None, transport: httpx.AsyncBaseTransport | None = None,
                 clock=time.monotonic, sleep: Callable[[float], Awaitable] = asyncio.sleep):
        self.cfg = cfg
        self.repo = repo
        self.specs = build_specs(cfg)
        pools = {k: {"neurons_per_day": v["neurons_per_day"]} for k, v in (cfg.get("shared_pools") or {}).items()}
        self.budget = Budget(pools, clock=clock)
        for s in self.specs.values():
            self.budget.register(s)
        self.clock = clock
        self.sleep = sleep
        self._clients: dict[str, httpx.AsyncClient] = {}
        self._transport = transport

    async def start(self) -> None:
        if self.repo:
            day = utc_day()
            self.budget.load(day, await self.repo.provider_day(day))
        missing = [n for n, s in self.specs.items() if not s.enabled]
        if missing:
            log.warning("models disabled (no API key or id not filled in): %s", ", ".join(missing))

    async def close(self) -> None:
        for c in self._clients.values():
            await c.aclose()

    def _client(self, spec: ModelSpec) -> httpx.AsyncClient:
        # one keep-alive client per provider: saves the TLS handshake on every call
        if spec.provider not in self._clients:
            headers = {"Authorization": f"Bearer {spec.api_key}"}
            if spec.provider == "openrouter":
                headers.update({"HTTP-Referer": "https://mathfix.ai", "X-Title": "MathFix AI"})
            self._clients[spec.provider] = httpx.AsyncClient(
                headers=headers, transport=self._transport,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20))
        return self._clients[spec.provider]

    def enabled_models(self, step: str) -> list[ModelSpec]:
        return [self.specs[n] for n in self.cfg["steps"][step] if n in self.specs and self.specs[n].enabled]

    # ---------------------------------------------------------------- main entry
    async def run(self, step: str, messages: list[dict], *, schema: type[BaseModel] | None = None,
                  effort: str | None = None, need_vision: bool = False,
                  on_wait: Callable[[], Awaitable] | None = None) -> Result:
        est = int(self.cfg.get("est_tokens", {}).get(step, 1500))
        timeout = float(self.cfg.get("timeouts", {}).get(step, 20))
        deadline = self.clock() + float(self.cfg.get("queue_wait_seconds", 30))
        waited = False
        while True:
            considered = day_blocked = 0
            can_wait = False          # some model may free up within the queue wait
            for spec in self.enabled_models(step):
                if need_vision and not spec.vision:
                    continue
                considered += 1
                cool = self.budget.cooling(spec.name)
                if cool > 0:
                    can_wait |= cool <= 60
                    continue
                ok, why = self.budget.has_room(spec, est)
                if not ok:
                    if why == "day":
                        day_blocked += 1
                    else:
                        can_wait = True
                    continue
                try:
                    return await self._attempt(spec, messages, schema, effort, timeout)
                except _RateLimited as e:
                    self.budget.cool(spec.name, min(max(e.retry_after, 5), 300))
                    can_wait |= e.retry_after <= 60
                except (_Transient, _BadOutput) as e:
                    log.info("model %s failed (%s), trying next", spec.name, e)
                    self.budget.cool(spec.name, 20)
                    can_wait = True
                except _BadRequest as e:
                    log.warning("model %s rejected the request (%s); cooling 10 min", spec.name, e)
                    self.budget.cool(spec.name, 600)
            if considered == 0 or day_blocked == considered:
                raise AllModelsBusy(daily=True)
            if can_wait and self.clock() < deadline:
                if on_wait and not waited:
                    waited = True
                    await on_wait()
                await self.sleep(1.5)
                continue
            raise AllModelsBusy(daily=False)

    async def _attempt(self, spec: ModelSpec, messages: list[dict], schema, effort, timeout) -> Result:
        msgs = list(messages)
        for attempt in range(2):
            text, latency = await self._call(spec, msgs, schema is not None, effort, timeout)
            if schema is None:
                if not text.strip():
                    raise _BadOutput("empty reply")
                return Result(text.strip(), spec.name, latency)
            try:
                return Result(schema.model_validate(extract_json(text)), spec.name, latency)
            except (_BadOutput, ValidationError) as e:
                if attempt == 1:
                    raise _BadOutput(str(e)[:200]) from None
                err = str(e).splitlines()[0][:150]
                msgs = msgs + [{"role": "assistant", "content": text[:4000]},
                               {"role": "user", "content": prompts.JSON_RETRY.format(error=err)}]
        raise _BadOutput("unreachable")

    async def _call(self, spec: ModelSpec, messages: list[dict], want_json: bool, effort: str | None,
                    timeout: float) -> tuple[str, int]:
        body: dict = {"model": spec.id, "messages": messages, "max_tokens": spec.max_tokens}
        if want_json and spec.json_mode:
            body["response_format"] = {"type": "json_object"}
        if effort and spec.reasoning_effort:
            body["reasoning_effort"] = effort
        t0 = time.monotonic()
        ok, limited, tin, tout = False, False, 0, 0
        try:
            resp = await self._client(spec).post(f"{spec.base_url}/chat/completions", json=body, timeout=timeout)
            if resp.status_code == 429:
                limited = True
                raise _RateLimited(float(resp.headers.get("retry-after", "30") or 30))
            if resp.status_code >= 500:
                raise _Transient(f"HTTP {resp.status_code}")
            if resp.status_code >= 400:
                raise _BadRequest(f"HTTP {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            msg = (data.get("choices") or [{}])[0].get("message") or {}
            text = msg.get("content") or ""
            usage = data.get("usage") or {}
            tin = int(usage.get("prompt_tokens") or _rough_tokens(messages))
            tout = int(usage.get("completion_tokens") or len(text) // 4)
            ok = True
            return text, int((time.monotonic() - t0) * 1000)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            raise _Transient(type(e).__name__) from None
        finally:
            # every attempt counts against the budget, failed or not (providers count them too)
            neurons = self.budget.record(spec, tin, tout)
            if self.repo:
                await self.repo.record_provider(
                    self.budget.day, spec.name, tokens_in=tin, tokens_out=tout, neurons=neurons, ok=ok,
                    rate_limited=limited, latency_ms=int((time.monotonic() - t0) * 1000))

    # ---------------------------------------------------------------- capacity
    def pool_used(self, step: str = "solve") -> float:
        """Fraction (0..1) of today's free capacity used, over the enabled models of a step."""
        est = int(self.cfg.get("est_tokens", {}).get(step, 1500))
        total = used = 0.0
        for spec in self.enabled_models(step):
            cap = self.budget.daily_capacity(spec, est)
            total += cap
            used += cap * self.budget.fraction_used(spec)
        return used / total if total else 1.0

    def status(self) -> list[dict]:
        rows = []
        for name, spec in self.specs.items():
            t = self.budget.today[name]
            rows.append({"model": name, "enabled": spec.enabled, "requests": t["requests"],
                         "tokens": t["tokens"], "neurons": round(t["neurons"], 1),
                         "used": round(self.budget.fraction_used(spec), 3),
                         "cooling_s": round(self.budget.cooling(name))})
        return rows


def _rough_tokens(messages: list[dict]) -> int:
    n = 0
    for m in messages:
        c = m.get("content")
        if isinstance(c, str):
            n += len(c) // 4
        elif isinstance(c, list):
            for part in c:
                n += len(part.get("text", "")) // 4 if part.get("type") == "text" else 1000
    return n
