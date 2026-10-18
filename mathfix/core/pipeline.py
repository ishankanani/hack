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
from ..mathcheck.text import is_big, is_hard, problem_key
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


def cache_key(text: str, lang: str = "en") -> str:
    """Same question, same explanation language -> same cached answer."""
    key = problem_key(text)
    return key if lang in ("", "en") else f"{key}:{lang}"


def _system(grade: str | None, lang: str) -> str:
    student, language = prompts.student_context(grade, lang)
    # SOLVE_SYSTEM contains literal JSON braces, so fill it with replace(), not format()
    return prompts.SOLVE_SYSTEM.replace("{student}", student).replace("{language}", language)


def _same_answer(a: str, b: str) -> bool:
    norm = lambda s: re.sub(r"[\s$\\{}]|text|or|and|,", "", (s or "").lower())  # noqa: E731
    return bool(a) and norm(a) == norm(b)


class Pipeline:
    def __init__(self, router: Router, repo: Repo, sandbox: Sandbox):
        self.router = router
        self.repo = repo
        self.sandbox = sandbox

    # ---------------------------------------------------------------- photo
    async def solve_photo(self, image: bytes, progress: Progress = _no_progress, *, grade: str | None = None,
                          lang: str = "en", explain: bool = True) -> Outcome:
        jpeg, phash = await asyncio.to_thread(preprocess_image, image)
        if lang not in ("", "en"):
            phash = f"{phash}:{lang}"               # cached explanations are per language
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
        text = (reading.problem_text or next((p for p in reading.problems if p.strip()), "")).strip()
        if not text:
            return Outcome(status="unreadable")
        # "problems" holds the other questions on the photo (older readers also repeat the first one there)
        others = [p.strip() for p in reading.problems if p.strip() and problem_key(p) != problem_key(text)]
        await progress("read", text)
        out = await self.solve_text(text, progress, latex=reading.problem_latex, grade=grade, lang=lang,
                                    explain=explain)
        out.other_problems = others
        if out.status == "solved" and out.solution_id:
            await self.repo.put_image(phash, out.solution_id, [text, *others])
        return out

    # ---------------------------------------------------------------- text
    async def solve_text(self, text: str, progress: Progress = _no_progress, latex: str = "", *,
                         grade: str | None = None, lang: str = "en", explain: bool = True) -> Outcome:
        """explain=False: when today's free AI quota is nearly used up, questions the maths engine can
        answer get the exact answer without an AI explanation, so they cost no quota at all."""
        t0 = time.monotonic()
        text = text.strip()[:4000]
        key = cache_key(text, lang)
        row = await self.repo.find_solution(key)
        if row:
            return self._from_row(row)

        quick = await self._sandboxed(quick_solve, text, timeout=2.0)
        hard, big = is_hard(text), is_big(text)
        user = prompts.SOLVE_USER.format(problem=text)
        if quick:
            # the exact answer is known in milliseconds: show it now, the AI only has to explain it
            await progress("instant", quick["answer_text"])
            user += prompts.KNOWN_ANSWER.format(answer=quick["answer_text"])
            hard = big = False
        messages = [{"role": "system", "content": _system(grade, lang)},
                    {"role": "user", "content": user}]
        await progress("solve", "")
        sol = None
        if explain or not quick:
            try:
                res = await self.router.run("solve", messages, schema=Solution, effort="medium" if hard else "low",
                                            big=big, on_wait=lambda: progress("queue", ""))
                sol, model = res.data, res.model
            except AllModelsBusy as e:
                if not quick:
                    return Outcome(status="capacity" if e.daily else "busy")
        if sol is None:
            # no AI (busy, or saving quota), but the engine already knows the answer: still help the student
            sol = Solution(steps=[Step(say="Worked out exactly with our maths engine.", math=quick["answer_latex"])],
                           final_answer=quick["answer_text"], final_answer_latex=quick["answer_latex"])
            model = "sympy"
        if sol.topic == "refused" or (not sol.steps and not sol.final_answer):
            return Outcome(status="refused")

        if quick:  # the exact answer wins; the model only explained it
            sol.final_answer, sol.final_answer_latex = quick["answer_text"], quick["answer_latex"]
            sol.check = Check(**quick["check"])
        status = await self._verify(sol.check, sol.final_answer)
        if quick and quick.get("exact") and status == "unchecked":
            status = "verified"      # computed exactly by the engine (e.g. HCF, matrices), not by the model

        # Big derivations can rarely be machine-checked; a full second solve would double the wait and
        # use the whole free per-minute token budget, so they get one only when something looks wrong.
        needs_second = (status == "failed" or sol.confidence < 0.7
                        or (hard and not big and status == "unchecked" and not quick))
        if needs_second:
            await progress("double_check", "")
            sol, status, model = await self._second_opinion(text, grade, lang, sol, status, model, big)

        sid = await self.repo.add_solution(
            problem_key=key, problem_text=text, problem_latex=latex, topic=sol.topic, difficulty=sol.difficulty,
            solution_json=sol.model_dump_json(), verified=status, model_used=model,
            latency_ms=int((time.monotonic() - t0) * 1000))
        return Outcome(status="solved", solution_id=sid, solution=sol, verified=status, problem_text=text,
                       problem_latex=latex, model=model, latency_ms=int((time.monotonic() - t0) * 1000))

    async def _second_opinion(self, text: str, grade: str | None, lang: str, sol: Solution, status: str,
                              model: str, big: bool = False):
        reason = "verification failed" if status == "failed" else "low confidence or not machine-checkable"
        messages = [{"role": "system", "content": _system(grade, lang)},
                    {"role": "user", "content": prompts.ESCALATE_USER.format(
                        problem=text, previous=sol.final_answer, reason=reason)}]
        try:
            # high effort on a big problem would spend the whole output budget on reasoning
            res = await self.router.run("escalate", messages, schema=Solution, effort="medium" if big else "high",
                                        big=big)
        except AllModelsBusy:
            return sol, status, model
        sol2: Solution = res.data
        status2 = await self._verify(sol2.check, sol2.final_answer)
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

    async def _verify(self, check: Check, answer: str = "") -> str:
        if check.type == "none":
            return "unchecked"
        result = await self._sandboxed(verify, check.model_dump(), answer, timeout=3.0)
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
