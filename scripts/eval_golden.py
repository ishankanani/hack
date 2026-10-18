"""Measure accuracy and speed on the golden problems with your real API keys (uses some free quota).

    .venv/bin/python -m scripts.eval_golden                       # all 40 problems
    .venv/bin/python -m scripts.eval_golden machine-learning      # one category
    .venv/bin/python -m scripts.eval_golden --limit 5

For every problem it records whether the final answer contains the expected numbers, the verification
status, which model answered, the time until the student first sees an answer (the engine's instant
answer, or the full answer) and the total time. A fresh database is used for answers, so nothing comes from cache; model usage is recorded in the bot's
database, because these calls spend the same free quota.
The full report is saved to data/golden-report.json.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import tempfile
import time
import unicodedata
from pathlib import Path

import yaml

from mathfix.ai.router import Router
from mathfix.config import ROOT, load_settings
from mathfix.core.pipeline import Pipeline
from mathfix.db import Repo
from mathfix.mathcheck.sandbox import Sandbox

GOLDEN = ROOT / "tests" / "golden" / "problems.yaml"
REPORT = ROOT / "data" / "golden-report.json"


def numbers_in(text: str) -> list[float]:
    """Every number in an answer, with fractions like 1/6 as their value."""
    s = unicodedata.normalize("NFKC", text or "").replace("−", "-").replace(",", " , ")
    out = []
    for m in re.finditer(r"-?\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?", s):
        tok = m.group(0).replace(" ", "")
        if "/" in tok:
            a, b = tok.split("/")
            if float(b) != 0:
                out.append(float(a) / float(b))
        out.append(float(tok.split("/")[0]))
    return out


def correct(answer: str, expected: list[float]) -> bool:
    found = numbers_in(answer)
    for e in expected:
        decimals = len(str(e).split(".")[1]) if "." in str(e) else 0
        tol = max(0.5 * 10 ** -decimals, 0.005 * abs(e), 1e-9) if decimals else max(1e-6, 1e-6 * abs(e))
        if not any(abs(f - e) <= tol for f in found):
            return False
    return True


def pct(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))] if xs else 0.0


async def main(category: str | None, limit: int | None) -> None:
    settings = load_settings()
    problems = yaml.safe_load(GOLDEN.read_text())
    if category:
        problems = [p for p in problems if p["cat"] == category]
    problems = problems[:limit] if limit else problems
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(Path(tmp) / "golden.db")
        await repo.init()
        usage = Repo(settings.database_path)
        await usage.init()
        sandbox = Sandbox(workers=2)
        await sandbox.start()
        router = Router(settings.models, usage)
        await router.start()
        pipeline = Pipeline(router, repo, sandbox)
        rows = []
        try:
            for i, p in enumerate(problems, 1):
                t0 = time.monotonic()
                first = {"t": None}

                async def progress(stage: str, info: str = "") -> None:
                    if stage == "instant" and first["t"] is None:
                        first["t"] = time.monotonic() - t0

                out = await pipeline.solve_text(p["q"], progress)
                total = time.monotonic() - t0
                answer = out.solution.final_answer if out.solution else ""
                ok = out.status == "solved" and correct(answer, [float(a) for a in p["answer"]])
                row = {"cat": p["cat"], "q": p["q"], "expected": p["answer"], "answer": answer, "ok": ok,
                       "status": out.status, "verified": out.verified, "model": out.model,
                       "instant": first["t"] is not None, "first_s": round(first["t"] or total, 2),
                       "total_s": round(total, 2)}
                rows.append(row)
                mark = "✅" if ok else "❌"
                print(f"{i:>2}. {mark} {row['first_s']:>5.1f}s / {row['total_s']:>5.1f}s  {row['model'] or '-':<14} "
                      f"{row['verified'] or out.status:<10} {p['q'][:60]}")
                if not ok:
                    print(f"      expected {p['answer']}, got: {answer[:120] or out.status}")
        finally:
            await router.close()
            await sandbox.close()
            await repo.close()
            await usage.close()

    print("\nCategory            correct   verified   first answer p50/p95   total p50/p95")
    for cat in sorted({r["cat"] for r in rows}) + ["ALL"]:
        rs = [r for r in rows if cat in ("ALL", r["cat"])]
        good = sum(r["ok"] for r in rs)
        ver = sum(r["verified"] in ("verified", "agreed") for r in rs)
        first, total = [r["first_s"] for r in rs], [r["total_s"] for r in rs]
        print(f"{cat:<18} {good:>3}/{len(rs):<4} {ver:>5}/{len(rs):<4}   {pct(first, .5):>5.1f}s / {pct(first, .95):>5.1f}s"
              f"       {pct(total, .5):>5.1f}s / {pct(total, .95):>5.1f}s")
    instant = sum(r["instant"] for r in rows)
    print(f"\nInstant engine answers: {instant}/{len(rows)}   "
          f"median total time: {statistics.median([r['total_s'] for r in rows]) if rows else 0:.1f}s")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    print(f"Report saved to {REPORT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("category", nargs="?", help="school-engine, school-ai, college-calculus or machine-learning")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    asyncio.run(main(args.category, args.limit))
