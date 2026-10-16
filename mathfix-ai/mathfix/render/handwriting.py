"""Handwritten-style solution image: notebook paper, blue ink, boxed red answer. No AI involved.

render_solution() is a plain function so it can run in the sandbox worker processes.
Same input (same seed) -> identical image, which is why the Telegram file_id can be reused.
"""
from __future__ import annotations

import io
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..mathcheck.text import latex_to_text

FONT_DIR = Path(__file__).parent / "assets" / "fonts"
WIDTH = 1080
RULE = 64                      # ruled line spacing
LEFT = 110                     # text starts right of the red margin
RIGHT_PAD = 50
MAX_W = WIDTH - LEFT - RIGHT_PAD
PAPER = (253, 251, 245)
RULE_COLOR = (186, 210, 236)
MARGIN_COLOR = (230, 140, 140)
INK = (26, 58, 143)
RED = (198, 40, 40)
GREY = (140, 140, 150)

_ready = False


def _setup() -> None:
    global _ready
    if _ready:
        return
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import font_manager, rcParams
    for f in FONT_DIR.glob("*.ttf"):
        font_manager.fontManager.addfont(str(f))
    rcParams.update({
        "mathtext.fontset": "custom", "mathtext.rm": "Kalam", "mathtext.it": "Kalam",
        "mathtext.bf": "Kalam:bold", "mathtext.cal": "Kalam", "mathtext.sf": "Kalam",
        "mathtext.fallback": "stix",
    })
    _ready = True


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_DIR / ("Kalam-Bold.ttf" if bold else "Kalam-Regular.ttf")
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default(size)


def _math_image(latex: str, size: int, color: tuple) -> Image.Image | None:
    """Render one line of LaTeX with matplotlib mathtext. None if mathtext can't parse it."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    latex = (latex or "").strip().strip("$")
    if not latex or "\\begin" in latex or "\\\\" in latex:
        return None
    fig = Figure(figsize=(0.01, 0.01), dpi=100)
    FigureCanvasAgg(fig)
    fig.text(0, 0, f"${latex}$", fontsize=size * 0.75, color=tuple(c / 255 for c in color))
    buf = io.BytesIO()
    try:
        fig.savefig(buf, format="png", dpi=100, bbox_inches="tight", pad_inches=0.04, transparent=True)
    except (ValueError, RuntimeError):
        return None
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGBA")


def _text_image(text: str, font: ImageFont.FreeTypeFont, color: tuple, max_w: int = MAX_W) -> Image.Image:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if font.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    lines = lines or [""]
    line_h = int(font.size * 1.45)
    img = Image.new("RGBA", (max_w, line_h * len(lines) + 6), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        d.text((0, i * line_h), line, font=font, fill=color)
    return img.crop(img.getbbox() or (0, 0, 1, 1))


def _math_or_text(latex: str, fallback: str, size: int, color: tuple) -> Image.Image:
    img = _math_image(latex, size, color)
    if img is not None and img.width > MAX_W:
        scale = MAX_W / img.width
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS) if scale >= 0.6 else None
    if img is None:
        img = _text_image(fallback or latex_to_text(latex), _font(size), color)
    return img


def _jitter(img: Image.Image, rng: random.Random) -> Image.Image:
    return img.rotate(rng.uniform(-1.2, 1.2), resample=Image.BICUBIC, expand=True)


def _wobbly_box(d: ImageDraw.ImageDraw, box: tuple, rng: random.Random, color: tuple) -> None:
    x0, y0, x1, y1 = box
    pts = []
    for (ax, ay), (bx, by) in [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]:
        for i in range(8):
            t = i / 8
            pts.append((ax + (bx - ax) * t + rng.uniform(-2.5, 2.5), ay + (by - ay) * t + rng.uniform(-2.5, 2.5)))
    pts.append(pts[0])
    d.line(pts, fill=color, width=4, joint="curve")


def render_solution(data: dict) -> bytes:
    """data: problem_text, problem_latex, steps [{say, math}], final_answer, final_answer_latex, seed."""
    _setup()
    rng = random.Random(data.get("seed", 0))
    items: list[tuple[Image.Image, str]] = []   # (image, kind)

    items.append((_text_image("Question", _font(46, bold=True), INK), "title"))
    items.append((_math_or_text(data.get("problem_latex", ""), data.get("problem_text", ""), 44, INK), "line"))
    items.append((Image.new("RGBA", (1, 1)), "gap"))
    for i, step in enumerate(data.get("steps", [])[:12], start=1):
        items.append((_text_image(f"{i}. {step.get('say', '')}", _font(40), INK), "line"))
        if step.get("math"):
            items.append((_math_or_text(step["math"], latex_to_text(step["math"]), 44, INK), "math"))
    items.append((Image.new("RGBA", (1, 1)), "gap"))
    answer = _math_or_text(data.get("final_answer_latex", ""), data.get("final_answer", ""), 50, RED)
    items.append((answer, "answer"))

    # layout: every item snaps to the ruled lines
    placed, y = [], RULE * 2
    for img, kind in items:
        img = _jitter(img, rng) if kind in ("line", "math", "answer") else img
        rows = max(1, -(-(img.height + 4) // RULE))
        x = LEFT + (40 if kind == "math" else 0) + (20 if kind == "answer" else 0) + rng.randint(-3, 3)
        top = y + rows * RULE - img.height - 10 + rng.randint(-3, 3)
        placed.append((img, kind, x, top))
        y += rows * RULE + (RULE // 2 if kind == "answer" else 0)
    height = y + RULE * 2

    page = Image.new("RGB", (WIDTH, height), PAPER)
    d = ImageDraw.Draw(page)
    for ry in range(RULE * 2, height, RULE):
        d.line([(0, ry), (WIDTH, ry)], fill=RULE_COLOR, width=2)
    d.line([(LEFT - 20, 0), (LEFT - 20, height)], fill=MARGIN_COLOR, width=3)
    for img, kind, x, top in placed:
        page.paste(img, (x, top), img)
        if kind == "answer":
            _wobbly_box(d, (x - 18, top - 14, x + img.width + 18, top + img.height + 14), rng, RED)
    footer = _font(28)
    label = "mathfix.ai · @mathfixbot"
    d.text((WIDTH - RIGHT_PAD - footer.getlength(label), height - RULE + 10), label, font=footer, fill=GREY)

    out = io.BytesIO()
    page.save(out, format="PNG", optimize=False)
    return out.getvalue()
