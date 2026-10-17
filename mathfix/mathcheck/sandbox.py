"""Run CPU-heavy or untrusted-input work (SymPy, image rendering) in worker processes.

Each call has a hard timeout. On timeout the whole pool is killed and recreated, because a
hung SymPy call cannot be cancelled any other way. Workers are started with 'spawn' so they
don't inherit the bot's event loop and threads.
"""
from __future__ import annotations

import asyncio
import logging
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Callable

log = logging.getLogger(__name__)


def _warm() -> None:
    """Import SymPy and set up matplotlib fonts once per worker, so the first real call is fast."""
    from ..render import handwriting
    from . import quick, verify  # noqa: F401

    handwriting._setup()


class SandboxTimeout(Exception):
    pass


class Sandbox:
    def __init__(self, workers: int = 2):
        self.workers = workers
        self._pool: ProcessPoolExecutor | None = None
        self._lock = asyncio.Lock()

    def _new_pool(self) -> ProcessPoolExecutor:
        return ProcessPoolExecutor(max_workers=self.workers, mp_context=mp.get_context("spawn"),
                                   initializer=_warm)

    async def start(self) -> None:
        self._pool = self._new_pool()
        # start every worker now so the first user doesn't wait for imports
        await asyncio.gather(*(self.run(_noop, timeout=60) for _ in range(self.workers)))

    async def run(self, fn: Callable, *args: Any, timeout: float = 2.0) -> Any:
        if self._pool is None:
            self._pool = self._new_pool()
        pool = self._pool
        fut = asyncio.wrap_future(pool.submit(fn, *args))
        try:
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            log.warning("sandbox timeout in %s; restarting pool", getattr(fn, "__name__", fn))
            await self._restart(pool)
            raise SandboxTimeout from None

    async def _restart(self, old: ProcessPoolExecutor) -> None:
        async with self._lock:
            if self._pool is not old:
                return
            for p in list(getattr(old, "_processes", {}).values()):
                p.kill()
            old.shutdown(wait=False, cancel_futures=True)
            self._pool = self._new_pool()

    async def close(self) -> None:
        if self._pool:
            self._pool.shutdown(wait=False, cancel_futures=True)


def _noop() -> bool:
    return True
