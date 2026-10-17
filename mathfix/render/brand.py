"""MathFix brand kit: colours, logo, QR codes.

Logo files (transparent PNGs, made from the official MathFix logo):
  mathfix/render/assets/logo.png        the "M" mark (square)
  mathfix/render/assets/logo_full.png   mark + "MathFix.ai" wordmark
Replace them to update the logo everywhere. If they are missing, a placeholder is drawn in code.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).parent / "assets"
FONTS = ASSETS / "fonts"
CUSTOM_LOGO = ASSETS / "logo.png"
CUSTOM_LOGO_FULL = ASSETS / "logo_full.png"

# brand colours, sampled from the MathFix logo
CYAN = (1, 227, 253)             # #01E3FD  gradient start
PRIMARY = (0, 110, 252)          # #006EFC  main blue
PRIMARY_DARK = (0, 61, 227)      # #003DE3  gradient end
NAVY = (5, 23, 68)               # #051744  "Math" in the wordmark
SLATE = (82, 94, 119)            # #525E77  ".ai"
ACCENT = (255, 176, 32)          # amber, for highlights only
SUCCESS = (18, 161, 80)          # green   #12A150
INK = (18, 52, 140)              # handwriting blue
TEXT_DARK = NAVY
PAPER = (252, 253, 255)
WHITE = (255, 255, 255)


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(FONTS / name), size)
    except OSError:
        return ImageFont.load_default(size)


@lru_cache(maxsize=16)
def logo_mark(size: int) -> Image.Image:
    """Square app icon: the custom logo if provided, else an indigo tile with a white √ and amber x."""
    if CUSTOM_LOGO.exists():
        img = Image.open(CUSTOM_LOGO).convert("RGBA")
        img.thumbnail((size, size), Image.LANCZOS)
        return img
    scale = 4                                              # draw big, then shrink for smooth edges
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.24), fill=PRIMARY)
    w = max(4, int(s * 0.085))
    pts = [(s * 0.17, s * 0.55), (s * 0.30, s * 0.50), (s * 0.43, s * 0.78), (s * 0.60, s * 0.22), (s * 0.86, s * 0.22)]
    d.line(pts, fill=WHITE, width=w, joint="curve")
    xf = font("DejaVuSans-Bold.ttf", int(s * 0.30))
    d.text((s * 0.62, s * 0.30), "x", font=xf, fill=ACCENT)
    return img.resize((size, size), Image.LANCZOS)


def wordmark(height: int, color=TEXT_DARK, accent=PRIMARY) -> Image.Image:
    """'MathFix.ai' text, with '.ai' in the accent colour."""
    f = font("DejaVuSans-Bold.ttf", int(height * 0.78))
    a, b = "MathFix", ".ai"
    wa, wb = f.getlength(a), f.getlength(b)
    img = Image.new("RGBA", (int(wa + wb) + 4, height + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((0, 0), a, font=f, fill=color)
    d.text((wa, 0), b, font=f, fill=accent)
    return img.crop(img.getbbox())


def gradient(width: int, height: int, start=CYAN, end=PRIMARY_DARK) -> Image.Image:
    """Left-to-right brand gradient."""
    img = Image.new("RGBA", (width, height))
    d = ImageDraw.Draw(img)
    for x in range(width):
        t = x / max(1, width - 1)
        d.line([(x, 0), (x, height)], fill=tuple(int(start[i] * (1 - t) + end[i] * t) for i in range(3)))
    return img


def logo_full(height: int, color=TEXT_DARK, accent=PRIMARY) -> Image.Image:
    """Mark + wordmark: the official logo file if present, else a drawn placeholder."""
    if CUSTOM_LOGO_FULL.exists():
        img = Image.open(CUSTOM_LOGO_FULL).convert("RGBA")
        return img.resize((int(img.width * height / img.height), height), Image.LANCZOS)
    mark = logo_mark(height)
    word = wordmark(int(height * 0.62), color, accent)
    gap = int(height * 0.28)
    img = Image.new("RGBA", (mark.width + gap + word.width, height), (0, 0, 0, 0))
    img.paste(mark, (0, 0), mark)
    img.paste(word, (mark.width + gap, (height - word.height) // 2), word)
    return img


def faded(img: Image.Image, opacity: float) -> Image.Image:
    img = img.copy()
    alpha = img.getchannel("A").point(lambda v: int(v * opacity))
    img.putalpha(alpha)
    return img


def qr_image(url: str, size: int, color=TEXT_DARK) -> Image.Image:
    """QR code for a URL with the logo in the middle. Level Q + a 16% logo was the most robust combination
    in testing: at 220 px it still decodes when the image is shown at 40% size."""
    import qrcode
    from qrcode.constants import ERROR_CORRECT_Q

    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_Q, box_size=10, border=1)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color=color, back_color="white").convert("RGBA").resize((size, size), Image.NEAREST)
    m = int(size * 0.16)
    pad = int(m * 0.12)
    backing = Image.new("RGBA", (m + 2 * pad, m + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(backing).rounded_rectangle((0, 0, backing.width - 1, backing.height - 1), radius=pad * 2, fill=WHITE)
    c = (size - backing.width) // 2
    img.paste(backing, (c, c), backing)
    mark = logo_mark(m)
    img.paste(mark, (c + pad, c + pad), mark)
    return img
