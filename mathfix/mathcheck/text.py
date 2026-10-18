"""Text helpers with no SymPy dependency: Unicode/LaTeX conversion and problem keys."""
from __future__ import annotations

import hashlib
import re
import unicodedata

_SUP = str.maketrans("0123456789+-−=()abcdefghijklmnoprstuvwxyzT",
                     "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻⁼⁽⁾ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻᵀ")
_SUB = str.maketrans("0123456789+-−=()aehijklmnoprstuvx", "₀₁₂₃₄₅₆₇₈₉₊₋₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ")
_SUP_OK = set("0123456789+-−=()abcdefghijklmnoprstuvwxyzT")
_SUB_OK = set("0123456789+-−=()aehijklmnoprstuvx")
_UNICODE_TO_ASCII = {
    "×": "*", "·": "*", "÷": "/", "−": "-", "–": "-", "—": "-", "π": "pi", "√": "sqrt",
    "²": "^2", "³": "^3", "⁴": "^4", "≤": "<=", "≥": ">=", "θ": "theta", "α": "alpha", "β": "beta",
    "½": "(1/2)", "¼": "(1/4)", "¾": "(3/4)",
}
# \name -> Unicode. Matched as whole command names, so \in never eats \int and \pm never eats \pmod.
_LATEX_SYMBOLS = {
    "times": "×", "cdot": "·", "div": "÷", "pm": "±", "mp": "∓", "ast": "*", "star": "⋆",
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε", "zeta": "ζ",
    "eta": "η", "theta": "θ", "vartheta": "θ", "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν",
    "xi": "ξ", "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "phi": "φ", "varphi": "φ", "chi": "χ",
    "psi": "ψ", "omega": "ω", "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π",
    "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
    "infty": "∞", "leq": "≤", "le": "≤", "leqslant": "≤", "geq": "≥", "ge": "≥", "geqslant": "≥",
    "lt": "<", "gt": ">", "neq": "≠", "ne": "≠", "approx": "≈", "equiv": "≡", "sim": "∼", "simeq": "≃",
    "cong": "≅", "propto": "∝", "to": "→", "rightarrow": "→", "longrightarrow": "→", "leftarrow": "←",
    "Rightarrow": "⇒", "implies": "⇒", "Leftarrow": "⇐", "iff": "⇔", "Leftrightarrow": "⇔", "mapsto": "↦",
    "in": "∈", "notin": "∉", "ni": "∋", "subset": "⊂", "subseteq": "⊆", "supset": "⊃", "supseteq": "⊇",
    "cup": "∪", "cap": "∩", "setminus": "∖", "emptyset": "∅", "varnothing": "∅", "forall": "∀",
    "exists": "∃", "neg": "¬", "land": "∧", "lor": "∨", "wedge": "∧", "vee": "∨", "oplus": "⊕",
    "otimes": "⊗", "partial": "∂", "nabla": "∇", "int": "∫", "iint": "∬", "oint": "∮", "sum": "Σ",
    "prod": "Π", "perp": "⊥", "parallel": "∥", "mid": "|", "vert": "|", "lvert": "|", "rvert": "|",
    "Vert": "‖", "lVert": "‖", "rVert": "‖", "langle": "⟨", "rangle": "⟩", "lfloor": "⌊", "rfloor": "⌋",
    "lceil": "⌈", "rceil": "⌉", "cdots": "⋯", "ldots": "…", "dots": "…", "vdots": "⋮", "prime": "′",
    "circ": "°", "degree": "°", "angle": "∠", "triangle": "△", "therefore": "∴", "because": "∵",
    "quad": " ", "qquad": " ", "left": "", "right": "", "big": "", "Big": "", "bigg": "", "Bigg": "",
    "bigl": "", "bigr": "", "Bigl": "", "Bigr": "", "displaystyle": "", "textstyle": "", "limits": "",
    "nolimits": "", "top": "ᵀ", "intercal": "ᵀ", "dagger": "†", "hbar": "ħ", "ell": "ℓ", "Re": "Re",
    "Im": "Im",
}
_LATEX_CHARS = {"|": "‖", ",": " ", ";": " ", ":": " ", "!": "", " ": " ", "%": "%", "&": "&", "#": "#",
                "{": "\x01", "}": "\x02", "$": "\x03", "_": "_"}
_BLACKBOARD = {"R": "ℝ", "N": "ℕ", "Z": "ℤ", "Q": "ℚ", "C": "ℂ", "P": "ℙ"}
_ACCENTS = {"bar": "\u0304", "overline": "\u0305", "hat": "\u0302", "widehat": "\u0302", "tilde": "\u0303",
            "widetilde": "\u0303", "dot": "\u0307", "vec": "\u20d7", "overrightarrow": "\u20d7"}
_ENVS = {"pmatrix": ("(", ")"), "bmatrix": ("[", "]"), "Bmatrix": ("\x01", "\x02"), "vmatrix": ("|", "|"),
         "Vmatrix": ("‖", "‖")}
_OPS_OVER = ("argmin", "argmax", "min", "max", "sup", "inf")
_STRIP_WORDS = re.compile(
    r"^(please\s+)?(solve|find|calculate|compute|evaluate|simplify|what\s+is|what's|work\s+out)\s*[:,]?\s*",
    re.IGNORECASE)


def _script(content: str, mark: str) -> str:
    """Superscript/subscript content -> Unicode (x², aₙ₊₁, Aᵀ), or ^(…) / _(…) when Unicode has no glyph."""
    t = content.replace(" ", "")
    ok, table = (_SUP_OK, _SUP) if mark == "^" else (_SUB_OK, _SUB)
    if t and all(c in ok for c in t):
        return t.translate(table)
    if t in ("*", "∗", "ᵀ", "′", "°", "†"):
        return t
    return f"{mark}{t}" if len(t) == 1 else f"{mark}({content.strip()})"


def _single_scripts(s: str) -> str:
    """x^2, x^n, x_1, A^T without braces."""
    s = re.sub(r"\^(-?\d+)(?![\d.])|\^([A-Za-z*])(?!\w)", lambda m: _script(m.group(1) or m.group(2), "^"), s)
    return re.sub(r"_(\d+)(?![\d.])|_([A-Za-z*])(?!\w)", lambda m: _script(m.group(1) or m.group(2), "_"), s)


def _op_under(m: re.Match) -> str:
    op, under = m.group(1), (m.group(2) or m.group(3) or "").strip()
    return f"{op} ({under}) " if op in ("lim", "liminf", "limsup") else f"{op} (over {under}) "


def _accent(m: re.Match) -> str:
    body = m.group(2)
    return body + _ACCENTS[m.group(1)] if len(body) == 1 else body


def latex_to_text(latex: str) -> str:
    """Best-effort LaTeX -> readable Unicode for Telegram messages (Telegram can't render LaTeX).
    e.g.  \\frac{1}{n}\\|XW-y\\|_2^2 + \\lambda\\|W\\|_*  ->  (1/n)‖XW-y‖₂² + λ‖W‖*"""
    s = (latex or "").replace("\\\\", " ; ")                  # line breaks in aligned / cases / matrices
    s = re.sub(r"\\(?:left|right)\.", "", s)
    s = re.sub(r"\\begin\{array\}\{[^{}]*\}", "", s)
    s = re.sub(r"\\(begin|end)\{(\w+\*?)\}",
               lambda m: _ENVS.get(m.group(2), ("", ""))[m.group(1) == "end"] + " ", s)
    s = re.sub(r"\\mathbb\s*\{?\s*([A-Z])\s*\}?", lambda m: _BLACKBOARD.get(m.group(1), m.group(1)), s)
    s = re.sub(r"\\(mathbf|mathrm|mathit|mathsf|mathcal|boldsymbol|bm|text|textbf|operatorname\*?)\s+(\w)",
               r"\\\1{\2}", s)                                # braceless \mathbf 1 -> \mathbf{1}
    s = re.sub(r"\^\s*\{?\s*\\circ\s*\}?", "°", s)
    s = re.sub(r"\\pmod\s*\{([^{}]*)\}", r" (mod \1)", s)
    s = re.sub(r"\\(?:bmod|mod)(?![A-Za-z])", " mod ", s)
    s = re.sub(r"\\([A-Za-z]+)( ?)|\\(.)", _symbol, s)
    s = s.replace("||", "‖")
    for _ in range(8):  # innermost braces first, so nested \frac / \sqrt / ^{} unwrap step by step
        s = _single_scripts(s)
        s = re.sub(r"\\(?:text|textbf|textit|mbox)\{([^{}]*)\}", r"\1", s)
        s = re.sub(r"\\(?:mathrm|mathbf|mathit|mathsf|mathcal|boldsymbol|bm|operatorname\*?)\{([^{}]*)\}", r"\1", s)
        s = re.sub(r"\\(" + "|".join(_ACCENTS) + r")\{([^{}]*)\}", _accent, s)
        s = re.sub(r"\\sqrt\[([^\]]+)\]\{([^{}]*)\}", lambda m: f"{_script(m.group(1), '^')}√({m.group(2)})", s)
        s = re.sub(r"\\sqrt\{([^{}]*)\}", lambda m: f"√{_wrap(m.group(1))}", s)
        s = re.sub(r"\\[dt]?frac\{([^{}]*)\}\{([^{}]*)\}", _frac, s)
        s = re.sub(r"\b(" + "|".join(_OPS_OVER + ("liminf", "limsup", "lim")) + r")\s*_(?:\{([^{}]*)\}|(\w))\s*",
                   _op_under, s)
        s = re.sub(r"\^\{([^{}]*)\}", lambda m: _script(m.group(1), "^"), s)
        s = re.sub(r"_\{([^{}]*)\}", lambda m: _script(m.group(1), "_"), s)
    s = re.sub(r"\\sqrt\s*(\w)", r"√\1", s)
    s = _single_scripts(s)
    s = s.replace("{", "").replace("}", "").replace("$", "").replace("&", " ")
    s = s.replace("\x01", "{").replace("\x02", "}").replace("\x03", "$")
    s = re.sub(r"\\([A-Za-z]+)", r"\1", s)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\(\s+", "(", re.sub(r"\s+\)", ")", s))
    return re.sub(r"\s*;\s*;\s*", "; ", s).strip(" ;")


_ORDINARY = set("αβγδεζηθικλμνξπρστφχψωΓΔΘΛΞΠΣΦΨΩ∞∂∇ħℓ")
_KEEP = {"frac", "dfrac", "tfrac", "sqrt", "text", "textbf", "textit", "mbox", "mathrm", "mathbf", "mathit",
         "mathsf", "mathcal", "boldsymbol", "bm", "operatorname", *_ACCENTS}


def _symbol(m: re.Match) -> str:
    name, space, char = m.group(1), m.group(2) or "", m.group(3)
    if char is not None:
        return _LATEX_CHARS.get(char, char)
    if name in _KEEP:
        return m.group(0)                                    # handled with its {argument} below
    if name in _LATEX_SYMBOLS:
        sym = _LATEX_SYMBOLS[name]
        return sym if sym in _ORDINARY else sym + space      # like LaTeX: \lambda G -> λG, but x \in A -> x ∈ A
    if name in ("sin", "cos", "tan", "log", "ln", "exp", "det", "gcd", "lcm"):
        return name + space
    return m.group(0)


def _wrap(s: str) -> str:
    """Brackets for a denominator unless it is one number or one symbol: 1/2, 1/x², 1/(2a)."""
    s = s.strip()
    return s if re.fullmatch(r"\d+(?:\.\d+)?|[^\W\d_][ᵀ′⁰¹²³⁴-⁹]*|√\w", s) else f"({s})"


def _wrap_top(s: str) -> str:
    """Brackets for a numerator only when it has a top-level + − = etc: (x+1)/2 but 2a/3 and n(n+1)/2."""
    s, flat = s.strip(), s.strip()
    while re.search(r"\([^()]*\)", flat):
        flat = re.sub(r"\([^()]*\)", "", flat)
    return f"({s})" if re.search(r"[-+±∓=/ ,<>≤≥−]", flat) else s


def _frac(m: re.Match) -> str:
    """a/b, bracketed when glued to its neighbours: 2\\frac{1}{2} -> 2 1/2 (mixed number), \\frac{1}{n}x -> (1/n)x."""
    num, den = m.group(1).strip(), m.group(2).strip()
    if re.fullmatch(r"[d∂]\s*\w*", num) and re.fullmatch(r"[d∂]\s*\w[⁰¹²³⁴-⁹]*", den):
        return f"{num.replace(' ', '')}/{den.replace(' ', '')} "             # dy/dx, d/dx, ∂f/∂x
    f = f"{_wrap_top(num)}/{_wrap(den)}"
    before, after = m.string[max(0, m.start() - 1):m.start()], m.string[m.end():m.end() + 1]
    if before.isdigit():
        return " " + f
    glued = before.isalnum() or before == ")" or (after != "" and (after.isalnum() or after in "‖(√\\"))
    return f"({f})" if glued else f


_LATEXY = re.compile(r"\\[A-Za-z|{}]|[\^_]\{")
_INLINE_MATH = re.compile(r"\\\((.+?)\\\)|\\\[(.+?)\\\]|\$\$(.+?)\$\$|\$(?=\S)([^$\n]+?)(?<=\S)\$", re.S)


def _plain_math(s: str) -> str:
    """Light touch for typed maths: x^2 -> x², θ^(new) -> θⁿᵉʷ, x_0 -> x₀, e * x -> e·x, <= -> ≤."""
    s = s.replace("**", "^")
    s = re.sub(r"\^\(([^()\s]{1,6})\)", lambda m: _script(m.group(1), "^") if all(c in _SUP_OK for c in m.group(1))
               else m.group(0), s)
    s = re.sub(r"\^(-?\d+)(?![\d.])|\^([A-Za-z])(?![A-Za-z(])", lambda m: _script(m.group(1) or m.group(2), "^"), s)
    s = re.sub(r"_(\d+)(?![\d.])|_([a-z])(?![A-Za-z])", lambda m: _script(m.group(1) or m.group(2), "_"), s)
    s = re.sub(r"(?<=[\w)\]⁰¹²³⁴-⁹₀-₉ᵀ])\s*\*\s*(?=[\w(\[−-])", "·", s)
    s = re.sub(r"\bsqrt\s*\(", "√(", s)
    s = re.sub(r"\bpi\b", "π", s)
    for a, b in (("<=", "≤"), (">=", "≥"), ("!=", "≠"), ("->", "→"), ("=>", "⇒"), ("||", "‖")):
        s = s.replace(a, b)
    return s


def pretty_math(text: str) -> str:
    """A maths field (question, answer, step) as clean Unicode, whether it came in as LaTeX or typed maths.
    Line breaks are kept."""
    text = _INLINE_MATH.sub(lambda m: next(g for g in m.groups() if g is not None), text or "")
    lines = [latex_to_text(ln) if _LATEXY.search(ln) else _plain_math(ln.strip()) for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def pretty_text(text: str) -> str:
    """A sentence that may contain maths: converts $…$ / \\(…\\) and stray LaTeX, drops markdown bold."""
    text = _INLINE_MATH.sub(lambda m: latex_to_text(next(g for g in m.groups() if g is not None)), text or "")
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    return "\n".join(latex_to_text(ln) if _LATEXY.search(ln) else ln.rstrip() for ln in text.splitlines()).strip()


def to_ascii_math(text: str) -> str:
    """User/Unicode maths -> ASCII maths SymPy can parse (after whitelisting)."""
    s = text or ""
    for k, v in _UNICODE_TO_ASCII.items():  # before NFKC, which would turn "²" into a plain "2"
        s = s.replace(k, v)
    s = unicodedata.normalize("NFKC", s)
    s = _STRIP_WORDS.sub("", s.strip())
    s = re.sub(r"^(?:(?:find|solve\s+for)\s+)?[a-z]\s*:\s*", "", s, flags=re.IGNORECASE)  # "Find x: ..."
    s = re.sub(r"\s*(for|in terms of)\s+[a-z]\s*$", "", s, flags=re.IGNORECASE)
    return strip_end_punctuation(s)


def strip_end_punctuation(s: str) -> str:
    """Drop a trailing ? . ! but keep a factorial: "5!" stays "5!"."""
    s = re.sub(r"(?<![\d)])!+\s*$", "", s.strip())
    return s.rstrip("?.").strip()


def problem_key(text: str) -> str:
    """Cache key: the same question typed slightly differently maps to the same key."""
    s = to_ascii_math(text).lower()
    s = re.sub(r"\s+", "", s)
    s = s.replace("**", "^").replace("·", "*")
    return hashlib.sha256(s.encode()).hexdigest()[:32]


# University maths: machine learning, optimisation, linear algebra, statistics
ADVANCED_HINTS = re.compile(
    r"(gradient|∇|\\nabla|hessian|jacobian|loss function|cross.entropy|regression|classifier|neural|backprop|"
    r"softmax|sigmoid|logistic|entropy|likelihood|posterior|eigen|singular value|\bsvd\b|\bnorm\b|\\\||‖|\|\||"
    r"optimi[sz]|argmin|argmax|\\min|\\max|lagrang|\bkkt\b|convex function|convex optim|covariance|gaussian|"
    r"kernel|\bsvm\b|\bpca\b|markov|transpose|(?-i:\^\{?T\}?)|\\top|\\mathbb|\bmatrix rank\b)", re.IGNORECASE)

HARD_HINTS = re.compile(
    r"(\\int|∫|integra|d/dx|deriv|differentia|\\lim|limit|lim_|\\sum|Σ|sin|cos|tan|log|ln|proof|prove|"
    r"show that|matrix|determinant|probability|series|vector)", re.IGNORECASE)


def is_hard(text: str) -> bool:
    """Cheap difficulty guess (no AI): decides reasoning effort low vs medium."""
    t = text or ""
    return bool(HARD_HINTS.search(t) or ADVANCED_HINTS.search(t)) or len(t) > 200 or t.count("=") > 2


def is_big(text: str) -> bool:
    """Long or university-level (e.g. machine learning): needs a bigger output budget and more time."""
    t = text or ""
    return len(t) > 350 or bool(ADVANCED_HINTS.search(t))
