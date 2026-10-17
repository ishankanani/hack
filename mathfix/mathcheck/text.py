"""Text helpers with no SymPy dependency: Unicode/LaTeX conversion and problem keys."""
from __future__ import annotations

import hashlib
import re
import unicodedata

_SUP = str.maketrans("0123456789+-()n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁽⁾ⁿ")
_UNICODE_TO_ASCII = {
    "×": "*", "·": "*", "÷": "/", "−": "-", "–": "-", "—": "-", "π": "pi", "√": "sqrt",
    "²": "^2", "³": "^3", "⁴": "^4", "≤": "<=", "≥": ">=", "θ": "theta", "α": "alpha", "β": "beta",
    "½": "(1/2)", "¼": "(1/4)", "¾": "(3/4)",
}
_LATEX_SYMBOLS = {
    r"\times": "×", r"\cdot": "·", r"\div": "÷", r"\pm": "±", r"\mp": "∓", r"\pi": "π",
    r"\theta": "θ", r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\Delta": "Δ", r"\delta": "δ",
    r"\lambda": "λ", r"\mu": "μ", r"\sigma": "σ", r"\infty": "∞", r"\leq": "≤", r"\le": "≤",
    r"\geq": "≥", r"\ge": "≥", r"\neq": "≠", r"\ne": "≠", r"\approx": "≈", r"\to": "→",
    r"\rightarrow": "→", r"\Rightarrow": "⇒", r"\implies": "⇒", r"\int": "∫", r"\sum": "Σ",
    r"\prod": "Π", r"\lim": "lim", r"\sin": "sin", r"\cos": "cos", r"\tan": "tan", r"\log": "log",
    r"\ln": "ln", r"\exp": "exp", r"\circ": "°", r"\degree": "°", r"\angle": "∠", r"\triangle": "△",
    r"\quad": " ", r"\qquad": " ", r"\,": " ", r"\;": " ", r"\!": "", r"\left": "", r"\right": "",
    r"\%": "%", r"\{": "{", r"\}": "}",
}
_STRIP_WORDS = re.compile(
    r"^(please\s+)?(solve|find|calculate|compute|evaluate|simplify|what\s+is|what's|work\s+out)\s*[:,]?\s*",
    re.IGNORECASE)


def _sup(s: str) -> str:
    return s.translate(_SUP) if all(c in "0123456789+-()n" for c in s) else f"^({s})"


def latex_to_text(latex: str) -> str:
    """Best-effort LaTeX -> readable Unicode for Telegram messages (Telegram can't render LaTeX)."""
    s = latex or ""
    for _ in range(6):  # innermost braces first, so nested \frac / \sqrt / ^{} unwrap step by step
        s = re.sub(r"\^\{([^{}]*)\}", lambda m: _sup(m.group(1)), s)
        s = re.sub(r"\\text\{([^{}]*)\}", r"\1", s)
        s = re.sub(r"\\(?:mathrm|mathbf|operatorname)\{([^{}]*)\}", r"\1", s)
        s = re.sub(r"\\sqrt\[([^\]]+)\]\{([^{}]*)\}", lambda m: f"{_sup(m.group(1))}√({m.group(2)})", s)
        s = re.sub(r"\\sqrt\{([^{}]*)\}", lambda m: f"√{_wrap(m.group(1))}", s)
        s = re.sub(r"\\[dt]?frac\{([^{}]*)\}\{([^{}]*)\}",
                   lambda m: f"{_wrap(m.group(1))}/{_wrap(m.group(2))}", s)
    s = re.sub(r"\^([0-9n])", lambda m: _sup(m.group(1)), s)
    s = re.sub(r"_\{([^{}]*)\}", r"_\1", s)
    for k in sorted(_LATEX_SYMBOLS, key=len, reverse=True):
        s = s.replace(k, _LATEX_SYMBOLS[k])
    s = s.replace("{", "").replace("}", "").replace("\\\\", "; ").replace("&", "")
    s = re.sub(r"\\([A-Za-z]+)", r"\1", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _wrap(s: str) -> str:
    s = s.strip()
    return s if re.fullmatch(r"[\w.]+", s) else f"({s})"


def to_ascii_math(text: str) -> str:
    """User/Unicode maths -> ASCII maths SymPy can parse (after whitelisting)."""
    s = text or ""
    for k, v in _UNICODE_TO_ASCII.items():  # before NFKC, which would turn "²" into a plain "2"
        s = s.replace(k, v)
    s = unicodedata.normalize("NFKC", s)
    s = _STRIP_WORDS.sub("", s.strip())
    s = re.sub(r"^(?:(?:find|solve\s+for)\s+)?[a-z]\s*:\s*", "", s, flags=re.IGNORECASE)  # "Find x: ..."
    s = re.sub(r"\s*(for|in terms of)\s+[a-z]\s*$", "", s, flags=re.IGNORECASE)
    return s.strip().rstrip("?.!").strip()


def problem_key(text: str) -> str:
    """Cache key: the same question typed slightly differently maps to the same key."""
    s = to_ascii_math(text).lower()
    s = re.sub(r"\s+", "", s)
    s = s.replace("**", "^").replace("·", "*")
    return hashlib.sha256(s.encode()).hexdigest()[:32]


HARD_HINTS = re.compile(
    r"(\\int|∫|integra|d/dx|deriv|differentia|\\lim|limit|lim_|\\sum|Σ|sin|cos|tan|log|ln|proof|prove|"
    r"show that|matrix|determinant|probability|series|vector)", re.IGNORECASE)


def is_hard(text: str) -> bool:
    """Cheap difficulty guess (no AI): decides reasoning effort low vs medium."""
    return bool(HARD_HINTS.search(text or "")) or len(text or "") > 200 or (text or "").count("=") > 2
