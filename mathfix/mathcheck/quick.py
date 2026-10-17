"""Instant answers with SymPy for simple typed questions (runs inside the sandbox worker).

Covers: arithmetic, fractions, "x% of y", and one-variable equations of degree <= 2.
The AI then only explains the steps for an answer that is already known to be correct.
"""
from __future__ import annotations

import re

import sympy as sp

from .safe import parse, parse_equation
from .text import to_ascii_math

_PERCENT_OF = re.compile(r"^\s*([\d.]+)\s*%\s*of\s*([\d.]+)\s*$", re.IGNORECASE)
_PURE_ARITH = re.compile(r"^[\d\s+\-*/^().%]+$")


def _fmt(v: sp.Expr) -> tuple[str, str]:
    v = sp.nsimplify(v) if isinstance(v, sp.Float) else v
    if isinstance(v, sp.Rational) and not isinstance(v, sp.Integer):
        dec = sp.N(v, 8)
        return f"{v} ≈ {float(dec):g}", f"{sp.latex(v)} \\approx {float(dec):g}"
    if v.is_number and not v.is_Integer and not v.is_Rational:
        return f"{sp.sstr(v)} ≈ {float(sp.N(v)):g}", f"{sp.latex(v)} \\approx {float(sp.N(v)):g}"
    return sp.sstr(v), sp.latex(v)


def quick_solve(text: str) -> dict | None:
    s = to_ascii_math(text)
    if not s:
        return None
    m = _PERCENT_OF.match(s)
    if m:
        expr = f"{m.group(1)}/100*{m.group(2)}"
        val = sp.nsimplify(parse(expr))
        txt, tex = _fmt(val)
        return {"answer_text": txt, "answer_latex": tex,
                "check": {"type": "expression_value", "expr": expr, "value": sp.sstr(val)}}
    try:
        if "=" in s:
            eq = parse_equation(s)
            free = list(eq.free_symbols)
            if len(free) != 1:
                return None
            var = free[0]
            poly = sp.Poly(eq, var) if eq.is_polynomial(var) else None
            if poly is None or poly.degree() < 1 or poly.degree() > 2:
                return None
            roots = [r for r in sp.solve(eq, var) if r.is_real]
            if not roots:
                return {"answer_text": "no real solutions", "answer_latex": r"\text{no real solutions}",
                        "check": {"type": "none"}}
            roots = sorted(roots, key=lambda r: float(r))
            txt = " or ".join(f"{var} = {_fmt(r)[0]}" for r in roots)
            tex = r" \text{ or } ".join(f"{var} = {sp.latex(r)}" for r in roots)
            return {"answer_text": txt, "answer_latex": tex,
                    "check": {"type": "equation_solutions", "expr": sp.sstr(eq), "variable": str(var),
                              "values": [sp.sstr(r) for r in roots]}}
        if not _PURE_ARITH.match(s) or "%" in s:
            return None
        val = parse(s)
        if val.free_symbols or not val.is_number:
            return None
        txt, tex = _fmt(sp.nsimplify(val) if val.is_Float else val)
        return {"answer_text": txt, "answer_latex": tex,
                "check": {"type": "expression_value", "expr": s, "value": sp.sstr(val)}}
    except Exception:  # noqa: BLE001 - anything SymPy can't handle simply goes to the AI path
        return None
