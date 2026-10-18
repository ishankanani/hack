"""Check every enabled model with your real keys before launch (uses a little free quota).

    .venv/bin/python -m scripts.smoke_test            # all steps
    .venv/bin/python -m scripts.smoke_test read_photo # one step
"""
from __future__ import annotations

import asyncio
import base64
import io
import sys
import time

from PIL import Image, ImageDraw, ImageFont

from mathfix.ai import prompts
from mathfix.ai.router import Router
from mathfix.config import load_settings
from mathfix.db import Repo
from mathfix.render.handwriting import FONT_DIR
from mathfix.schemas import Reading, Solution


def sample_photo() -> str:
    img = Image.new("RGB", (1200, 500), "white")
    font = ImageFont.truetype(str(FONT_DIR / "Kalam-Regular.ttf"), 90)
    ImageDraw.Draw(img).text((80, 160), "Solve: 3x - 7 = 11", font=font, fill=(20, 20, 90))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


async def main(only: str | None) -> None:
    settings = load_settings()
    repo = Repo(settings.database_path)          # the bot's database: these calls use the same free quota
    await repo.init()
    router = Router(settings.models, repo)
    await router.start()
    photo = sample_photo()
    cases = {
        "read_photo": ([{"role": "system", "content": prompts.READ_SYSTEM},
                        {"role": "user", "content": [{"type": "text", "text": "Read the maths question in this photo."},
                                                     {"type": "image_url",
                                                      "image_url": {"url": f"data:image/jpeg;base64,{photo}"}}]}],
                       Reading, "low"),
        "solve": ([{"role": "system", "content": prompts.SOLVE_SYSTEM.replace("{language}", "English")},
                   {"role": "user", "content": "Problem: x^3 - x = 6"}], Solution, "low"),
        "tutor": ([{"role": "system", "content": "You are a maths tutor. Reply in one sentence."},
                   {"role": "user", "content": "Give me a hint for 2x + 3 = 11"}], None, "low"),
    }
    cases["escalate"] = cases["solve"]
    for step, (messages, schema, effort) in cases.items():
        if only and step != only:
            continue
        print(f"\n== {step} ==")
        for name in settings.models["steps"][step]:
            spec = router.specs[name]
            if not spec.enabled:
                print(f"  {name:18} DISABLED (missing key or id)")
                continue
            t0 = time.monotonic()
            try:
                res = await router._attempt(spec, messages, schema, effort, timeout=40)
                out = res.data if isinstance(res.data, str) else res.data.model_dump(include={
                    "problem_text", "final_answer", "check", "readable", "is_math"})
                print(f"  {name:18} OK   {time.monotonic() - t0:5.1f}s  {str(out)[:150]}")
            except Exception as e:  # noqa: BLE001 - report every failure and keep going
                print(f"  {name:18} FAIL {time.monotonic() - t0:5.1f}s  {type(e).__name__}: {e}")
    await router.close()
    await repo.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
