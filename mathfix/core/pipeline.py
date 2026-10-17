"""The solve pipeline: cache -> (read photo) -> SymPy quick path -> solve -> verify -> second opinion.

AI is used only to read photos and to write the explanation; SymPy decides what is correct.
The handwritten image is NOT made here: it is rendered only when the student taps the button.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

import imagehash
from PIL import Image, ImageOps

from ..ai import prompts
from ..ai.router import AllModelsBusy, Router
from ..db import Repo
from ..mathcheck.quick import quick_solve
from ..mathcheck.sandbox import Sandbox, SandboxTimeout
from ..mathcheck.text import is_hard, problem_key
from ..mathcheck.verify import verify
from ..schemas import Check, Reading, Solution, Step

log = logging.getLogger(__name__)
Progress = Callable[[str, str], Awaitable[None]]


async def _no_progress(stage: str, info: str = "") -> None:
    return None


@dataclass
class Outcome:
    status: str                       # solved | unreadable | not_math | refused | busy | capacity
    solution_id: int | None = None
    solution: Solution | None = None
    verified: str = "unchecked"
    problem_text: str = ""
    problem_latex: str = ""
    other_problems: list[str] = field(default_factory=list)
    from_cache: bool = False
    model: str = ""
    latency_ms: int = 0


def preprocess_image(data: bytes, max_side: int = 1024) -> tuple[bytes, str]:
    """Rotate per EXIF, shrink to <= max_side (1024 px reads fast and is enough for handwriting),
    re-encode as JPEG q85, and compute a perceptual hash."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    img.thumbnail((max_side, max_side))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)
    return out.getvalue(), str(imagehash.phash(img))


def _same_answer(a: str, b: str) -> bool:
    norm = lambda s: re.sub(r"[\s$\\{}]|text|or|and|,", "", (s or "").lower())  # noqa: E731
    return bool(a) and norm(a) == norm(b)


class Pipeline:
    def __init__(self, router: Router, repo: Repo, sandbox: Sandbox):
        self.router = router
        self.repo = repo
        self.sandbox = sandbox

    # ---------------------------------------------------------------- photo
    async def solve_photo(self, image: bytes, lang: str = "English", progress: Progress = _no_progress) -> Outcome:
        jpeg, phash = await asyncio.to_thread(preprocess_image, image)
        cached = await self.repo.get_image(phash)
        if cached:
            row = await self.repo.get_solution(cached["solution_id"])
            if row and not row["flagged"] and row["wrong_reports"] < 2 and row["verified"] != "failed":
                out = self._from_row(row)
                out.other_problems = json.loads(cached["problems_json"] or "[]")[1:]
                return out

        b64 = base64.b64encode(jpeg).decode()
        messages = [
            {"role": "system", "content": prompts.READ_SYSTEM},
            {"role": "user", "content": [
                {"type": "text", "text": "Read the maths question in this photo."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ]},
        ]
        try:
            res = await self.router.run("read_photo", messages, schema=Reading, need_vision=True,
                                        on_wait=lambda: progress("queue", ""))
        except AllModelsBusy as e:
            return Outcome(status="capacity" if e.daily else "busy")
        reading: Reading = res.data
        if not reading.readable:
            return Outcome(status="unreadable")
        if not reading.is_math:
            return Outcome(status="not_math")
        problems = reading.problems or [reading.problem_text]
        text = reading.problem_text or problems[0]
        if not text.strip():
            return Outcome(status="unreadable")
        await progress("read", text)
        out = await self.solve_text(text, lang, progress, latex=reading.problem_latex)
        out.other_problems = problems[1:]
        if out.status == "solved" and out.solution_id:
            await self.repo.put_image(phash, out.solution_id, problems)
        return out

    # ---------------------------------------------------------------- text
    async def solve_text(self, text: str, lang: str = "English", progress: Progress = _no_progress,
                         latex: str = "") -> Outcome:
        t0 = time.monotonic()
        text = text.strip()[:2000]
        key = problem_key(text)
        row = await self.repo.find_solution(key)
        if row:
            return self._from_row(row)

        quick = await self._sandboxed(quick_solve, text, timeout=2.0)
        hard = is_hard(text)
        user = prompts.SOLVE_USER.format(problem=text)
        if quick:
            user += prompts.KNOWN_ANSWER.format(answer=quick["answer_text"])
        messages = [{"role": "system", "content": prompts.SOLVE_SYSTEM.replace("{language}", lang)},
                    {"role": "user", "content": user}]
        await progress("solve", "")
        try:
            res = await self.router.run("solve", messages, schema=Solution, effort="medium" if hard else "low",
                                        on_wait=lambda: progress("queue", ""))
            sol, model = res.data, res.model
        except AllModelsBusy as e:
            if not quick:
                return Outcome(status="capacity" if e.daily else "busy")
            # no AI available, but SymPy already knows the answer: still help the student
            sol = Solution(steps=[Step(say="Worked out exactly with our maths engine.", math=quick["answer_latex"])],
                           final_answer=quick["answer_text"], final_answer_latex=quick["answer_latex"])
            model = "sympy"
        if sol.topic == "refused" or (not sol.steps and not sol.final_answer):
            return Outcome(status="refused")

        if quick:  # the exact answer wins; the model only explained it
            sol.final_answer, sol.final_answer_latex = quick["answer_text"], quick["answer_latex"]
            sol.check = Check(**quick["check"])
        status = await self._verify(sol.check)

        needs_second = (status == "failed" or sol.confidence < 0.7
                        or (hard and status == "unchecked" and not quick))
        if needs_second:
            await progress("double_check", "")
            sol, status, model = await self._second_opinion(text, lang, sol, status, model)

        sid = await self.repo.add_solution(
            problem_key=key, problem_text=text, problem_latex=latex, topic=sol.topic, difficulty=sol.difficulty,
            solution_json=sol.model_dump_json(), verified=status, model_used=model,
            latency_ms=int((time.monotonic() - t0) * 1000))
        return Outcome(status="solved", solution_id=sid, solution=sol, verified=status, problem_text=text,
                       problem_latex=latex, model=model, latency_ms=int((time.monotonic() - t0) * 1000))

    async def _second_opinion(self, text: str, lang: str, sol: Solution, status: str, model: str):
        reason = "verification failed" if status == "failed" else "low confidence or not machine-checkable"
        messages = [{"role": "system", "content": prompts.SOLVE_SYSTEM.replace("{language}", lang)},
                    {"role": "user", "content": prompts.ESCALATE_USER.format(
                        problem=text, previous=sol.final_answer, reason=reason)}]
        try:
            res = await self.router.run("escalate", messages, schema=Solution, effort="high")
        except AllModelsBusy:
            return sol, status, model
        sol2: Solution = res.data
        status2 = await self._verify(sol2.check)
        if status2 == "verified":
            return sol2, "verified", res.model
        if status == "verified":
            return sol, status, model
        if status == "unchecked" and status2 == "unchecked":
            if _same_answer(sol.final_answer, sol2.final_answer):
                return sol, "agreed", model
            return sol2, "unchecked", res.model
        if status == "failed" and status2 == "unchecked":
            return sol2, "unchecked", res.model
        return sol2, status2, res.model

    async def _verify(self, check: Check) -> str:
        if check.type == "none":
            return "unchecked"
        result = await self._sandboxed(verify, check.model_dump(), timeout=3.0)
        return (result or {}).get("status", "unchecked")

    async def _sandboxed(self, fn, *args, timeout: float):
        try:
            return await self.sandbox.run(fn, *args, timeout=timeout)
        except SandboxTimeout:
            return None
        except Exception:  # noqa: BLE001 - a broken check must never break the answer
            log.exception("sandbox call %s failed", getattr(fn, "__name__", fn))
            return None

    @staticmethod
    def _from_row(row: dict) -> Outcome:
        return Outcome(status="solved", solution_id=row["id"], solution=Solution.model_validate_json(row["solution_json"]),
                       verified=row["verified"], problem_text=row["problem_text"],
                       problem_latex=row["problem_latex"] or "", from_cache=True, model=row["model_used"])
