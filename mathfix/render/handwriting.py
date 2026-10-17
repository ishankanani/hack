"""Branded, handwritten-style solution image. No AI involved.

Layout: brand header (logo, topic) → maths grid paper with a faint logo watermark → question →
numbered steps → key idea note → boxed final answer with a "verified" stamp → watch-out tip →
footer with a QR code that opens this solution in the bot.

render_solution() is a plain function so it can run in the sandbox worker processes.
Same input → identical image, so the Telegram file_id can be reused for everyone.
"""
from __future__ import annotations

import io
import random
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..mathcheck.text import latex_to_text
from . import brand
from .brand import CYAN, INK, NAVY, PAPER, PRIMARY, SLATE, SUCCESS, TEXT_DARK, WHITE

FONT_DIR = Path(__file__).parent / "assets" / "fonts"
WIDTH = 1080
LEFT = 120                     # content starts right of the red margin
RIGHT_PAD = 60
MAX_W = WIDTH - LEFT - RIGHT_PAD
GRID = 40
HEADER_H = 170
FOOTER_H = 300
GRID_COLOR = (225, 236, 252)
MARGIN_COLOR = (236, 150, 150)
RED = (205, 45, 45)
NOTE_BG = (255, 244, 194)
ANSWER_BG = (234, 248, 239)

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


# ------------------------------------------------------------------ text with symbol fallback
@lru_cache(maxsize=4)
def _glyphs(path: str) -> frozenset[int]:
    from fontTools.ttLib import TTFont
    return frozenset(TTFont(path).getBestCmap().keys())


class Pen:
    """Writes in the handwriting font, switching to DejaVu for symbols it lacks (√ π ≤ ∞ …),
    so nothing shows as a box."""

    def __init__(self, size: int, bold: bool = False):
        main = FONT_DIR / ("Kalam-Bold.ttf" if bold else "Kalam-Regular.ttf")
        self.main = brand.font(main.name, size)
        self.fallback = brand.font("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", int(size * 0.84))
        self.cmap = _glyphs(str(main)) if main.exists() else frozenset()
        self.size = size

    def runs(self, text: str) -> list[tuple[str, ImageFont.FreeTypeFont]]:
        out: list[tuple[str, ImageFont.FreeTypeFont]] = []
        for ch in text:
            f = self.main if (ord(ch) in self.cmap or ch == " ") else self.fallback
            if out and out[-1][1] is f:
                out[-1] = (out[-1][0] + ch, f)
            else:
                out.append((ch, f))
        return out

    def length(self, text: str) -> float:
        return sum(f.getlength(t) for t, f in self.runs(text))

    def draw(self, d: ImageDraw.ImageDraw, x: float, baseline: float, text: str, fill) -> None:
        for t, f in self.runs(text):
            d.text((x, baseline), t, font=f, fill=fill, anchor="ls")
            x += f.getlength(t)


def _text_image(text: str, pen: Pen, color: tuple, max_w: int = MAX_W) -> Image.Image:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if pen.length(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    lines = lines or [""]
    line_h = int(pen.size * 1.45)
    img = Image.new("RGBA", (max_w + 20, line_h * len(lines) + pen.size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        pen.draw(d, 0, i * line_h + pen.size * 1.05, line, color)
    return img.crop(img.getbbox() or (0, 0, 1, 1))


def _math_image(latex: str, size: int, color: tuple) -> Image.Image | None:
    """One line of LaTeX via matplotlib mathtext. None if mathtext can't parse it."""
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


def _math_or_text(latex: str, fallback: str, size: int, color: tuple, max_w: int = MAX_W) -> Image.Image:
    img = _math_image(latex, size, color)
    if img is not None and img.width > max_w:
        scale = max_w / img.width
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS) if scale >= 0.6 else None
    if img is None:
        img = _text_image(fallback or latex_to_text(latex), Pen(size), color, max_w)
    return img


def _jitter(img: Image.Image, rng: random.Random, deg: float = 1.0) -> Image.Image:
    return img.rotate(rng.uniform(-deg, deg), resample=Image.BICUBIC, expand=True)


# ------------------------------------------------------------------ blocks
def _pill(text: str, bg: tuple, fg: tuple, size: int = 24) -> Image.Image:
    f = brand.font("DejaVuSans-Bold.ttf", size)
    w, h = int(f.getlength(text)) + size * 2, int(size * 1.9)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=bg)
    d.text((w / 2, h / 2), text, font=f, fill=fg, anchor="mm")
    return img


def _stack(parts: list[tuple[Image.Image, int]], gap: int = 10) -> Image.Image:
    """Stack (image, x_offset) pairs vertically into one transparent block."""
    w = max(x + im.width for im, x in parts)
    h = sum(im.height for im, _ in parts) + gap * (len(parts) - 1)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    y = 0
    for im, x in parts:
        out.paste(im, (x, y), im)
        y += im.height + gap
    return out


def _step_block(n: int, say: str, math_latex: str, rng: random.Random) -> Image.Image:
    badge_d = 52
    text_x = badge_d + 22
    text = _jitter(_text_image(say, Pen(38), INK, MAX_W - text_x), rng, 0.6)
    parts = [(text, 0)]
    if math_latex:
        parts.append((_jitter(_math_or_text(math_latex, latex_to_text(math_latex), 44, INK, MAX_W - text_x - 30),
                              rng, 0.8), 30))
    body = _stack(parts, gap=12)
    out = Image.new("RGBA", (max(body.width + text_x, text_x + 10), max(body.height, badge_d)), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    d.ellipse((0, 2, badge_d, badge_d + 2), fill=PRIMARY)
    d.text((badge_d / 2, badge_d / 2 + 2), str(n), font=brand.font("DejaVuSans-Bold.ttf", 26), fill=WHITE, anchor="mm")
    out.paste(body, (text_x, 0), body)
    return out


def _note_block(title: str, text: str, bg: tuple, title_color: tuple) -> Image.Image:
    pad = 26
    title_img = _text_image(title, Pen(30, bold=True), title_color, MAX_W - 2 * pad)
    body = _text_image(text, Pen(34), TEXT_DARK, MAX_W - 2 * pad)
    inner = _stack([(title_img, 0), (body, 0)], gap=8)
    out = Image.new("RGBA", (MAX_W, inner.height + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(out).rounded_rectangle((0, 0, out.width - 1, out.height - 1), radius=22, fill=bg)
    out.paste(inner, (pad, pad), inner)
    return out


def _wobbly_rect(d: ImageDraw.ImageDraw, box: tuple, rng: random.Random, color: tuple, width: int = 4) -> None:
    x0, y0, x1, y1 = box
    pts = []
    for (ax, ay), (bx, by) in [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]:
        for i in range(10):
            t = i / 10
            pts.append((ax + (bx - ax) * t + rng.uniform(-2.5, 2.5), ay + (by - ay) * t + rng.uniform(-2.5, 2.5)))
    pts.append(pts[0])
    d.line(pts, fill=color, width=width, joint="curve")


def _stamp(text: str, color: tuple, d_px: int = 150) -> Image.Image:
    img = Image.new("RGBA", (d_px, d_px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, d_px - 4, d_px - 4), outline=color, width=5)
    d.ellipse((16, 16, d_px - 16, d_px - 16), outline=color, width=2)
    d.text((d_px / 2, d_px / 2 - 12), "✓", font=brand.font("DejaVuSans-Bold.ttf", 40), fill=color, anchor="mm")
    d.text((d_px / 2, d_px / 2 + 26), text, font=brand.font("DejaVuSans-Bold.ttf", 17), fill=color, anchor="mm")
    return brand.faded(img.rotate(-14, resample=Image.BICUBIC), 0.85)


def _answer_block(latex: str, text: str, verified: str, rng: random.Random) -> Image.Image:
    label = _pill("✓ FINAL ANSWER", SUCCESS, WHITE, 22)
    ans = _jitter(_math_or_text(latex, text, 56, TEXT_DARK, MAX_W - 220), rng, 0.6)
    pad = 30
    box_w, box_h = min(MAX_W - 160, ans.width + 2 * pad), ans.height + 2 * pad
    box = Image.new("RGBA", (box_w + 12, box_h + 12), (0, 0, 0, 0))
    d = ImageDraw.Draw(box)
    d.rounded_rectangle((6, 6, box_w + 6, box_h + 6), radius=18, fill=ANSWER_BG)
    _wobbly_rect(d, (6, 6, box_w + 6, box_h + 6), rng, SUCCESS)
    box.paste(ans, (6 + pad, 6 + (box_h - ans.height) // 2), ans)
    block = _stack([(label, 0), (box, 0)], gap=14)
    if verified in ("verified", "agreed"):
        stamp = _stamp("VERIFIED" if verified == "verified" else "DOUBLE-CHECKED", SUCCESS)
        out = Image.new("RGBA", (MAX_W, max(block.height, stamp.height)), (0, 0, 0, 0))
        out.paste(block, (0, 0), block)
        out.paste(stamp, (min(box.width + 10, MAX_W - stamp.width), max(0, block.height - stamp.height)), stamp)
        return out
    return block


# ------------------------------------------------------------------ page parts
def _header(topic: str, difficulty: int) -> Image.Image:
    """White band with the full MathFix logo, topic chip, level dots and a brand gradient strip."""
    img = Image.new("RGBA", (WIDTH, HEADER_H), WHITE)
    d = ImageDraw.Draw(img)
    logo = brand.logo_full(96)
    img.paste(logo, (40, (HEADER_H - 8 - logo.height) // 2), logo)
    if topic:
        chip = _pill(topic[:28], PRIMARY, WHITE, 22)
        img.paste(chip, (WIDTH - chip.width - 40, 30), chip)
    lvl = max(1, min(5, difficulty))
    f = brand.font("DejaVuSans.ttf", 22)
    dots_x = WIDTH - 40
    for i in reversed(range(5)):                             # level dots, right-aligned
        dots_x -= 26
        d.ellipse((dots_x, 104, dots_x + 16, 120), fill=PRIMARY if i < lvl else (205, 220, 245))
    d.text((dots_x - 12, 112), "Level", font=f, fill=SLATE, anchor="rm")
    strip = brand.gradient(WIDTH, 8)
    img.paste(strip, (0, HEADER_H - 8), strip)
    return img


def _footer(qr_url: str) -> Image.Image:
    img = Image.new("RGBA", (WIDTH, FOOTER_H), WHITE)
    strip = brand.gradient(WIDTH, 6)
    img.paste(strip, (0, 0), strip)
    d = ImageDraw.Draw(img)
    x = 50
    if qr_url:
        qr = brand.qr_image(qr_url, 220, NAVY)
        img.paste(qr, (x, 30), qr)
        d.text((x + 110, 272), "Scan to open", font=brand.font("DejaVuSans-Bold.ttf", 20), fill=PRIMARY, anchor="mm")
        x += 260
    bold = brand.font("DejaVuSans-Bold.ttf", 34)
    reg = brand.font("DejaVuSans.ttf", 24)
    d.text((x, 70), "Solved with MathFix.ai", font=bold, fill=NAVY)
    d.text((x, 122), "Free maths help on Telegram:", font=reg, fill=SLATE)
    d.text((x, 156), "@mathfixbot", font=brand.font("DejaVuSans-Bold.ttf", 26), fill=PRIMARY)
    d.text((x, 198), "Photo → answer · steps · tutor", font=reg, fill=SLATE)
    mark = brand.logo_mark(96)                               # corner logo
    img.paste(mark, (WIDTH - 96 - 34, FOOTER_H - 96 - 26), mark)
    return img


def _topic_label(topic: str) -> str:
    t = (topic or "").replace("_", " ").strip()
    return "" if t.lower() in ("", "general", "refused") else t[:1].upper() + t[1:]


def render_solution(data: dict) -> bytes:
    """data: problem_text, problem_latex, steps [{say, math}], final_answer, final_answer_latex, seed,
    and optional topic, difficulty, key_idea, tip, verified, qr_url."""
    _setup()
    rng = random.Random(data.get("seed", 0))

    blocks: list[tuple[Image.Image, int, int]] = []          # (image, x, space_after)
    blocks.append((_pill("QUESTION", CYAN, NAVY, 22), LEFT, 16))
    q = _math_or_text(data.get("problem_latex", ""), data.get("problem_text", ""), 46, INK)
    blocks.append((_jitter(q, rng, 0.6), LEFT, 40))
    if data.get("steps"):
        blocks.append((_pill("STEP BY STEP", PRIMARY, WHITE, 22), LEFT, 22))
        for i, step in enumerate(data["steps"][:12], start=1):
            blocks.append((_step_block(i, step.get("say", ""), step.get("math", ""), rng), LEFT, 28))
    if data.get("key_idea"):
        blocks.append((_note_block("★ Key idea", data["key_idea"], NOTE_BG, (150, 100, 0)), LEFT, 30))
    blocks.append((_answer_block(data.get("final_answer_latex", ""), data.get("final_answer", ""),
                                 data.get("verified", ""), rng), LEFT, 30))
    if data.get("tip"):
        blocks.append((_note_block("⚠ Watch out", data["tip"], (253, 234, 234), RED), LEFT, 20))

    body_h = 60 + sum(im.height + gap for im, _, gap in blocks) + 40
    height = HEADER_H + body_h + FOOTER_H
    page = Image.new("RGBA", (WIDTH, height), PAPER)
    d = ImageDraw.Draw(page)
    top, bottom = HEADER_H, HEADER_H + body_h
    for gx in range(0, WIDTH, GRID):                         # maths grid paper
        d.line([(gx, top), (gx, bottom)], fill=GRID_COLOR, width=1)
    for gy in range(top, bottom, GRID):
        d.line([(0, gy), (WIDTH, gy)], fill=GRID_COLOR, width=1)
    d.line([(LEFT - 26, top), (LEFT - 26, bottom)], fill=MARGIN_COLOR, width=3)

    wm = brand.faded(brand.logo_mark(min(520, int(body_h * 0.6))), 0.06)    # centre watermark
    page.paste(wm, ((WIDTH - wm.width) // 2, top + (body_h - wm.height) // 2), wm)
    diag = Image.new("RGBA", (WIDTH, body_h), (0, 0, 0, 0))   # faint repeated brand text
    dd = ImageDraw.Draw(diag)
    wf = brand.font("DejaVuSans-Bold.ttf", 30)
    for row, y in enumerate(range(80, body_h, 320)):
        for x in range(-200 + (row % 2) * 220, WIDTH, 440):
            dd.text((x, y), "mathfix.ai", font=wf, fill=PRIMARY + (13,))
    diag = diag.rotate(18, resample=Image.BICUBIC)
    page.paste(diag, (0, top), diag)

    y = top + 60
    for im, x, gap in blocks:
        page.paste(im, (x, y), im)
        y += im.height + gap

    header = _header(_topic_label(data.get("topic", "")), int(data.get("difficulty", 2) or 2))
    page.paste(header, (0, 0), header)
    footer = _footer(data.get("qr_url", ""))
    page.paste(footer, (0, height - FOOTER_H), footer)

    out = io.BytesIO()
    page.convert("RGB").save(out, format="PNG", optimize=False)
    return out.getvalue()
