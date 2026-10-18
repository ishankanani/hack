"""Instant, exact answers with SymPy (runs inside the sandbox worker, well under a second).

Covers the most common typed or photographed questions:
  arithmetic, fractions, roots, factorials, percentages, HCF / LCM, prime factorisation,
  mean / median / mode / range, polynomial and rational equations (degree <= 4),
  systems of linear equations, linear and quadratic inequalities,
  derivatives, integrals (indefinite and definite), limits,
  factorise / expand / simplify, and 2x2 to 4x4 matrices (determinant, inverse, eigenvalues,
  transpose, rank).
The answer is shown to the student at once; the AI then only explains the steps for an answer
that is already known to be correct. Anything else returns None and goes to the AI path.
"""
from __future__ import annotations

import re
import statistics
import unicodedata
from fractions import Fraction

import mpmath
import sympy as sp
from sympy.integrals.manualintegrate import manualintegrate

from .safe import parse, parse_equation
from .text import _UNICODE_TO_ASCII, strip_end_punctuation, to_ascii_math

_PERCENT_OF = re.compile(r"^\s*([\d.]+)\s*%\s*of\s*([\d.]+)\s*$", re.IGNORECASE)
_LEAD = re.compile(r"^(?:please\s+)?(?:find|calculate|compute|evaluate|determine|work out|solve|get|what is|"
                   r"what's|whats)?(?:\s+for\s+[a-z](?![a-z]))?\s*:?\s*(?:the\s+)?", re.IGNORECASE)
# results that are correct but mean nothing to a school student: let the AI explain instead
_SPECIAL = (sp.erf, sp.erfi, sp.erfc, sp.Ei, sp.Si, sp.Ci, sp.li, sp.gamma, sp.uppergamma, sp.lowergamma,
            sp.polylog, sp.LambertW, sp.Piecewise, sp.hyper, sp.meijerg, sp.fresnels, sp.fresnelc)
_NUM = r"-?\d+(?:\.\d+)?"
_MAX_DEGREE = 4
_MAX_OPS = 60          # skip simplify() on big expressions: it can take seconds


# ------------------------------------------------------------------ formatting
def _fmt(v: sp.Expr) -> tuple[str, str]:
    v = sp.nsimplify(v) if isinstance(v, sp.Float) else v
    if isinstance(v, sp.Rational) and not isinstance(v, sp.Integer):
        dec = sp.N(v, 8)
        return f"{v} ≈ {float(dec):g}", f"{sp.latex(v)} \\approx {float(dec):g}"
    if v.is_number and not v.is_Integer and not v.is_Rational:
        return f"{sp.sstr(v)} ≈ {float(sp.N(v)):g}", f"{sp.latex(v)} \\approx {float(sp.N(v)):g}"
    return sp.sstr(v), sp.latex(v)


def _txt(e: sp.Expr) -> str:
    """Readable plain text: x**2 -> x^2, exp(x) -> e^x, log -> ln (SymPy's log is natural)."""
    s = sp.sstr(e).replace("**", "^")
    s = re.sub(r"\bexp\((\w+)\)", r"e^\1", s)
    s = re.sub(r"\bexp\(", "e^(", s)
    return re.sub(r"\blog\(", "ln(", s)


def _plain_school(e: sp.Expr) -> bool:
    return not e.has(*_SPECIAL)


def _answer(text: str, latex: str, check: dict | None = None, *, kind: str) -> dict:
    """check: a re-checkable verify() spec; without one the result is still exact (computed here)."""
    return {"answer_text": text, "answer_latex": latex, "check": check or {"type": "none"},
            "exact": True, "kind": kind}


def _ascii(text: str) -> str:
    s = text or ""
    for k, v in _UNICODE_TO_ASCII.items():
        s = s.replace(k, v)
    s = (s.replace("∫", " integral ").replace("→", "->").replace("∞", "oo").replace("₹", "")
         .replace("≤", "<=").replace("≥", ">=").replace("∂", "d"))
    s = unicodedata.normalize("NFKC", s)
    return strip_end_punctuation(re.sub(r"\s+", " ", s))


def _strip_lead(s: str) -> str:
    return _LEAD.sub("", s, count=1).strip()


def _var(expr: sp.Expr, hint: str | None = None) -> sp.Symbol | None:
    if hint:
        return sp.Symbol(hint)
    free = sorted(expr.free_symbols, key=lambda v: v.name)
    if len(free) == 1:
        return free[0]
    return sp.Symbol("x") if sp.Symbol("x") in free else None


def _tidy(e: sp.Expr) -> sp.Expr:
    return sp.simplify(e) if sp.count_ops(e) <= _MAX_OPS else e


# ------------------------------------------------------------------ numbers
def _numbers(s: str) -> list[Fraction]:
    return [Fraction(n) for n in re.findall(_NUM, s)]


def _percent(s: str) -> dict | None:
    m = _PERCENT_OF.match(to_ascii_math(s))
    if m:
        expr = f"{m.group(1)}/100*{m.group(2)}"
        val = sp.nsimplify(parse(expr))
        txt, tex = _fmt(val)
        return _answer(txt, tex, {"type": "expression_value", "expr": expr, "value": sp.sstr(val)}, kind="percent")
    m = re.match(rf"^what (?:percent|percentage) of ({_NUM}) is ({_NUM})$", s, re.I) or \
        re.match(rf"^({_NUM}) is what (?:percent|percentage) of ({_NUM})$", s, re.I)
    if m:
        whole, part = (m.group(1), m.group(2)) if s.lower().startswith("what") else (m.group(2), m.group(1))
        val = sp.nsimplify(parse(f"{part}/{whole}*100"))
        return _answer(f"{_fmt(val)[0]}%", f"{_fmt(val)[1]}\\%", kind="percent")
    m = re.match(rf"^(increase|decrease|reduce) ({_NUM}) by ({_NUM}) ?%$", s, re.I)
    if m:
        sign = 1 if m.group(1).lower() == "increase" else -1
        val = sp.nsimplify(parse(f"{m.group(2)}*(1 + ({sign})*{m.group(3)}/100)"))
        return _answer(_fmt(val)[0], _fmt(val)[1], kind="percent")
    return None


def _hcf_lcm(s: str) -> dict | None:
    m = re.match(r"^(hcf|gcd|gcf|lcm|highest common factor|greatest common divisor|least common multiple|"
                 r"lowest common multiple)\s*(?:of)?\s*([\d,\s]+(?:and\s+\d+)?)$", s, re.I)
    if not m:
        return None
    nums = [int(n) for n in re.findall(r"\d+", m.group(2))]
    if len(nums) < 2 or max(nums) > 10**12:
        return None
    is_lcm = m.group(1).lower().startswith(("lcm", "least", "lowest"))
    val = sp.ilcm(*nums) if is_lcm else sp.igcd(*nums)
    name = "LCM" if is_lcm else "HCF"
    return _answer(f"{name} = {val}", f"\\text{{{name}}} = {val}", kind="hcf_lcm")


def _prime_factors(s: str) -> dict | None:
    m = re.match(r"^(?:prime factori[sz]ation|prime factors)\s*(?:of)?\s*(\d+)$", s, re.I)
    if not m or int(m.group(1)) < 2 or int(m.group(1)) > 10**15:
        return None
    n = int(m.group(1))
    parts = sorted(sp.factorint(n).items())
    sup = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
    txt = " × ".join(f"{p}{str(k).translate(sup) if k > 1 else ''}" for p, k in parts)
    tex = r" \times ".join(f"{p}^{{{k}}}" if k > 1 else str(p) for p, k in parts)
    return _answer(f"{n} = {txt}", f"{n} = {tex}", kind="prime_factors")


def _stats(s: str) -> dict | None:
    m = re.match(r"^(mean|average|median|mode|range)\s*(?:of)?\s*[:\-]?\s*([-\d.,\s]+(?:and\s+-?[\d.]+)?)$", s, re.I)
    if not m:
        return None
    data = _numbers(m.group(2))
    if len(data) < 2:
        return None
    what = m.group(1).lower()
    if what in ("mean", "average"):
        val = sp.Rational(sum(data) / len(data))
    elif what == "median":
        val = sp.Rational(statistics.median(data))
    elif what == "range":
        val = sp.Rational(max(data) - min(data))
    else:
        modes = statistics.multimode(data)
        if len(modes) == len(set(data)):
            return _answer("no mode (every value appears equally often)", r"\text{no mode}", kind="stats")
        vals = ", ".join(_fmt(sp.Rational(v))[0] for v in sorted(modes))
        return _answer(f"mode = {vals}", f"\\text{{mode}} = {vals}", kind="stats")
    txt, tex = _fmt(val)
    return _answer(f"{what} = {txt}", f"\\text{{{what}}} = {tex}", kind="stats")


# ------------------------------------------------------------------ calculus
def _derivative(s: str) -> dict | None:
    m = (re.match(r"^d/d([a-z])\s*(?:of\s+)?(.+)$", s, re.I)
         or re.match(r"^(?:derivative|differentiation|differential coefficient)\s+of\s+(.+?)"
                     r"(?:\s+(?:with respect to|wrt|w\.r\.t\.?)\s+([a-z]))?$", s, re.I)
         or re.match(r"^differentiate\s+(.+?)(?:\s+(?:with respect to|wrt|w\.r\.t\.?)\s+([a-z]))?$", s, re.I)
         or re.match(r"^dy/dx\s*(?:of|if|for|when|where)?\s*y\s*=\s*(.+)$", s, re.I)
         or re.match(r"^(?:if\s+)?y\s*=\s*(.+?)\s*,?\s*(?:then\s+)?(?:find\s+)?dy/dx$", s, re.I))
    if not m:
        return None
    if s.lower().startswith("d/d"):
        var_name, body = m.group(1), m.group(2)
    else:
        body, var_name = m.group(1), (m.group(2) if m.lastindex and m.lastindex >= 2 else None)
    f = parse(re.sub(r"^(?:y|f\(x\))\s*=\s*", "", body.strip()))
    x = _var(f, var_name)
    if x is None:
        return None
    d = _tidy(sp.diff(f, x))
    if not _plain_school(d):
        return None
    return _answer(f"dy/d{x} = {_txt(d)}", f"\\frac{{d}}{{d{x}}}\\left({sp.latex(f)}\\right) = {sp.latex(d)}",
                   {"type": "derivative", "expr": sp.sstr(f), "variable": str(x), "value": sp.sstr(d)},
                   kind="derivative")


def _integral(s: str) -> dict | None:
    m = re.match(r"^(?:integrate|integral(?: of)?|antiderivative of|indefinite integral of|definite integral of)\s+"
                 r"(.+?)\s*(?:d([a-z]))?\s*(?:from\s+(\S+)\s+to\s+(\S+))?$", s, re.I)
    if not m:
        return None
    body, var_name, lo, hi = m.group(1), m.group(2), m.group(3), m.group(4)
    bounds = re.match(r"^_\{?([^}\s^]+)\}?\s*\^\{?([^}\s]+)\}?\s*(.+)$", body)   # integral_0^1 x^2 dx
    if bounds:
        lo, hi, body = bounds.group(1), bounds.group(2), bounds.group(3)
    f = parse(body)
    x = _var(f, var_name)
    if x is None:
        return None
    F = manualintegrate(f, x)
    if F.has(sp.Integral) or not _plain_school(F):
        return None
    F = _tidy(F)
    if lo is None:
        return _answer(f"{_txt(F)} + C", f"\\int {sp.latex(f)}\\,d{x} = {sp.latex(F)} + C",
                       {"type": "antiderivative", "expr": sp.sstr(f), "variable": str(x), "value": sp.sstr(F)},
                       kind="integral")
    a, b = parse(lo), parse(hi)
    val = _tidy(F.subs(x, b) - F.subs(x, a))
    numeric = mpmath.quad(sp.lambdify(x, f, "mpmath"), [float(sp.N(a)), float(sp.N(b))])
    if not val.is_number or abs(complex(sp.N(val)) - complex(numeric)) > 1e-6 * max(1.0, abs(complex(numeric))):
        return None          # discontinuity or an odd antiderivative: let the AI handle it
    txt, tex = _fmt(val)
    return _answer(txt, f"\\int_{{{sp.latex(a)}}}^{{{sp.latex(b)}}} {sp.latex(f)}\\,d{x} = {tex}",
                   {"type": "definite_integral", "expr": sp.sstr(f), "variable": str(x), "lower": sp.sstr(a),
                    "upper": sp.sstr(b), "value": sp.sstr(val)}, kind="integral")


def _limit(s: str) -> dict | None:
    m = (re.match(r"^lim(?:it)?\s*_?\{?\s*([a-z])\s*->\s*([^\s}]+)\s*\}?\s*(?:of\s+)?(.+)$", s, re.I)
         or re.match(r"^lim(?:it)?\s+of\s+(.+?)\s+as\s+([a-z])\s*(?:->|approaches|tends to)\s*(\S+)$", s, re.I))
    if not m:
        return None
    if " as " in s.lower() and s.lower().startswith(("limit of", "lim of")):
        body, var_name, point = m.group(1), m.group(2), m.group(3)
    else:
        var_name, point, body = m.group(1), m.group(2), m.group(3)
    f, x = parse(body), sp.Symbol(var_name)
    p = sp.oo if point.lower() in ("oo", "inf", "infinity") else -sp.oo if point.lower() in ("-oo", "-inf") \
        else parse(point)
    val = sp.limit(f, x, p)
    if val.has(sp.Limit) or val is sp.nan or isinstance(val, sp.AccumBounds) or not _plain_school(val):
        return None
    txt, tex = (("∞", r"\infty") if val is sp.oo else ("-∞", r"-\infty") if val is -sp.oo else _fmt(val))
    return _answer(txt, f"\\lim_{{{x} \\to {sp.latex(p)}}} {sp.latex(f)} = {tex}",
                   {"type": "limit", "expr": sp.sstr(f), "variable": str(x), "point": sp.sstr(p),
                    "value": sp.sstr(val)}, kind="limit")


# ------------------------------------------------------------------ algebra
def _rewrite(s: str) -> dict | None:
    m = re.match(r"^(factori[sz]e|factor|expand|simplify)\s*:?\s*(.+)$", s, re.I)
    if not m:
        return None
    op, f = m.group(1).lower(), parse(m.group(2))
    if not f.free_symbols:
        return None
    out = sp.factor(f) if op.startswith("factor") else sp.expand(f) if op == "expand" else sp.simplify(f)
    return _answer(_txt(out), sp.latex(out), {"type": "simplify_equal", "expr": sp.sstr(f), "value": sp.sstr(out)},
                   kind=op[:6])


def _split_equations(s: str) -> list[str]:
    parts = re.split(r"\s*(?:;|,|\band\b|\n)\s*", s)
    return [p for p in parts if p.strip()]


def _system(s: str) -> dict | None:
    parts = _split_equations(s)
    if len(parts) < 2 or any(p.count("=") != 1 for p in parts) or len(parts) > 4:
        return None
    eqs = [parse_equation(p) for p in parts]
    syms = sorted(set().union(*(e.free_symbols for e in eqs)), key=lambda v: v.name)
    if len(syms) != len(eqs) or any(sp.Poly(e, *syms).total_degree() != 1 for e in eqs):
        return None
    sol = sp.solve(eqs, syms, dict=True)
    if len(sol) != 1 or len(sol[0]) != len(syms):
        return None
    sol = sol[0]
    txt = ", ".join(f"{v} = {_fmt(sol[v])[0]}" for v in syms)
    tex = ",\\ ".join(f"{v} = {sp.latex(sol[v])}" for v in syms)
    return _answer(txt, tex, {"type": "system", "expr": "; ".join(sp.sstr(e) for e in eqs),
                              "values": [f"{v}={sp.sstr(sol[v])}" for v in syms]}, kind="system")


def _equation(s: str) -> dict | None:
    s = to_ascii_math(s)
    if s.count("=") != 1:
        return None
    eq = parse_equation(s)
    free = list(eq.free_symbols)
    if len(free) != 1:
        return None
    var = free[0]
    num, den = sp.fraction(sp.together(eq))
    if not num.is_polynomial(var) or not den.is_polynomial(var):
        return None
    poly = sp.Poly(num, var)
    if poly.degree() < 1 or poly.degree() > _MAX_DEGREE:
        return None
    roots = [r for r in sp.solve(num, var) if r.is_real and den.subs(var, r) != 0]
    if not roots:
        return _answer("no real solutions", r"\text{no real solutions}", kind="equation")
    roots = sorted(set(roots), key=lambda r: float(r))
    if poly.degree() > 2 and any(sp.count_ops(r) > 8 for r in roots):
        return None          # cubic formula radicals help nobody; the AI explains a numerical method
    txt = " or ".join(f"{var} = {_fmt(r)[0]}" for r in roots)
    tex = r" \text{ or } ".join(f"{var} = {sp.latex(r)}" for r in roots)
    return _answer(txt, tex, {"type": "equation_solutions", "expr": sp.sstr(eq), "variable": str(var),
                              "values": [sp.sstr(r) for r in roots]}, kind="equation")


_REL = {"<=": sp.Le, ">=": sp.Ge, "<": sp.Lt, ">": sp.Gt}


def _inequality(s: str) -> dict | None:
    s = to_ascii_math(s)
    ops = re.findall(r"<=|>=|<|>", s)
    if len(ops) != 1 or "=" in s.replace("<=", "").replace(">=", ""):
        return None
    lhs, rhs = re.split(r"<=|>=|<|>", s)
    a, b = parse(lhs), parse(rhs)
    free = (a - b).free_symbols
    if len(free) != 1:
        return None
    x = free.pop()
    if not (a - b).is_polynomial(x) or sp.Poly(a - b, x).degree() > 2:
        return None
    sol = sp.solve_univariate_inequality(_REL[ops[0]](a, b), x, relational=False)
    if sol == sp.S.EmptySet:
        return _answer("no real solutions", r"\text{no real solutions}", kind="inequality")
    if sol == sp.S.Reals:
        return _answer("all real numbers", r"x \in \mathbb{R}", kind="inequality")
    return _answer(_interval_text(sol, x), sp.latex(sp.solve_univariate_inequality(_REL[ops[0]](a, b), x)),
                   kind="inequality")


def _interval_text(sol: sp.Set, x: sp.Symbol) -> str:
    def one(iv: sp.Interval) -> str:
        lo = "" if iv.start is -sp.oo else f"{_fmt(iv.start)[0]} {'<' if iv.left_open else '≤'} "
        hi = "" if iv.end is sp.oo else f" {'<' if iv.right_open else '≤'} {_fmt(iv.end)[0]}"
        if not lo:
            return f"{x}{hi}"
        if not hi:
            return f"{x} {'>' if iv.left_open else '≥'} {_fmt(iv.start)[0]}"
        return f"{lo}{x}{hi}"
    pieces = sol.args if isinstance(sol, sp.Union) else (sol,)
    return " or ".join(one(p) for p in pieces if isinstance(p, sp.Interval))


# ------------------------------------------------------------------ matrices
_MATRIX = re.compile(r"\[\s*\[[-\d.,\s\[\]/]+\]\s*\]")


# what the engine can compute for a matrix, and words that mean something else was asked for
_MATRIX_OPS = (("det", r"\bdet|determinant"), ("trace", r"\btrace\b"), ("rank", r"\brank\b"),
               ("inverse", r"inverse|\binv\("), ("transpose", r"transpose"), ("eigen", r"eigen ?values?"))
_MATRIX_UNSUPPORTED = re.compile(r"eigen ?vectors?|characteristic|diagonali|null ?space|kernel|basis|orthogon|"
                                 r"\blu\b|\bqr\b|\bsvd\b|singular|norm|power|square of|\^|multiply|product|"
                                 r"\btimes\b|\bsolve\b|system|\bb\s*=|cofactor|adjoint|adjugate|minor|echelon",
                                 re.IGNORECASE)


def _matrix(s: str) -> dict | None:
    """Only when every requested quantity is one the engine computes; a partial answer would be wrong."""
    found = _MATRIX.findall(s)
    if len(found) != 1 or _MATRIX_UNSUPPORTED.search(_MATRIX.sub(" ", s)):
        return None
    rows = re.findall(r"\[([^\[\]]+)\]", found[0])
    data = [[sp.Rational(Fraction(v)) for v in re.split(r"[,\s]+", r.strip()) if v] for r in rows]
    if not (2 <= len(data) <= 4) or len({len(r) for r in data}) != 1:
        return None
    M = sp.Matrix(data)
    asked = [name for name, pattern in _MATRIX_OPS if re.search(pattern, s, re.IGNORECASE)]
    if not asked or (not M.is_square and set(asked) - {"rank", "transpose"}):
        return None
    texts, latex = [], []
    for op in asked:
        if op == "det":
            d = M.det()
            texts.append(f"det = {_fmt(d)[0]}")
            latex.append(f"\\det A = {sp.latex(d)}")
        elif op == "trace":
            texts.append(f"trace = {_fmt(M.trace())[0]}")
            latex.append(f"\\operatorname{{tr}} A = {sp.latex(M.trace())}")
        elif op == "rank":
            texts.append(f"rank = {M.rank()}")
            latex.append(f"\\operatorname{{rank}} A = {M.rank()}")
        elif op == "transpose":
            texts.append(f"transpose = {_matrix_text(M.T)}")
            latex.append(f"A^T = {sp.latex(M.T)}")
        elif op == "inverse":
            if M.det() == 0:
                texts.append("no inverse (the determinant is 0)")
                latex.append(r"\det A = 0")
            else:
                texts.append(f"inverse = {_matrix_text(M.inv())}")
                latex.append(f"A^{{-1}} = {sp.latex(M.inv())}")
        elif op == "eigen":
            vals = []
            for v, k in M.eigenvals().items():
                vals += [v] * k
            if not all(sp.N(v).is_real for v in vals):
                return None
            vals = sorted(vals, key=lambda v: float(sp.N(v)))
            texts.append("eigenvalues: " + ", ".join(_fmt(v)[0] for v in vals))
            latex.append(r"\lambda = " + ",\\ ".join(sp.latex(v) for v in vals))
    return _answer("; ".join(texts), r",\quad ".join(latex), kind="matrix")


def _matrix_text(M: sp.Matrix) -> str:
    return "[" + ", ".join("[" + ", ".join(sp.sstr(v) for v in M.row(i)) + "]" for i in range(M.rows)) + "]"


# ------------------------------------------------------------------ arithmetic
def _arithmetic(s: str) -> dict | None:
    s = to_ascii_math(s)
    if "=" in s or "%" in s or not s:
        return None
    val = parse(s)
    if val.free_symbols or not val.is_number or val.has(sp.I):
        return None
    txt, tex = _fmt(sp.nsimplify(val) if val.is_Float else val)
    return _answer(txt, tex, {"type": "expression_value", "expr": s, "value": sp.sstr(val)}, kind="arithmetic")


_HANDLERS = (_percent, _hcf_lcm, _prime_factors, _stats, _matrix, _derivative, _integral, _limit, _rewrite,
             _system, _inequality, _equation, _arithmetic)


def quick_solve(text: str) -> dict | None:
    """Exact answer for a question the engine recognises, else None. Never raises."""
    s = _strip_lead(_ascii(text))
    if not s or len(s) > 300:
        return None
    for handler in _HANDLERS:
        try:
            out = handler(s)
        except Exception:  # noqa: BLE001 - anything SymPy can't handle simply goes to the AI path
            out = None
        if out:
            return out
    return None
