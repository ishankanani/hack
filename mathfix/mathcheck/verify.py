"""Answer verification with SymPy (runs inside the sandbox worker).

verify(check) returns {"status": "verified" | "failed" | "unchecked", "reason": str}.
A crash or unsupported check is "unchecked", never "verified".
"""
from __future__ import annotations

import re
import unicodedata

import mpmath
import sympy as sp

from .safe import UnsafeExpression, parse, parse_equation

SAMPLE_POINTS = [0.37, 1.23, 2.71, -0.83, 3.14, 0.59, -1.7]
TOL = 1e-8


def _num(expr) -> complex | None:
    try:
        v = complex(sp.N(expr, 30))
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if v != v or abs(v) == float("inf"):
        return None
    return v


def _close(a, b) -> bool:
    va, vb = _num(a), _num(b)
    if va is None or vb is None:
        return False
    return abs(va - vb) <= TOL * max(1.0, abs(va), abs(vb))


def _zero_at_points(expr: sp.Expr, needed: int = 3) -> bool | None:
    """True if expr == 0 at every sampled point (None if too few valid points)."""
    free = sorted(expr.free_symbols, key=lambda s: s.name)
    if not free:
        v = _num(expr)
        return None if v is None else abs(v) <= TOL
    good = 0
    for i, p in enumerate(SAMPLE_POINTS):
        subs = {s: p + 0.11 * j * (i + 1) for j, s in enumerate(free)}
        v = _num(expr.subs(subs))
        if v is None:
            continue
        if abs(v) > 1e-6:
            return False
        good += 1
    return True if good >= needed else None


def _result(ok: bool | None, reason: str = "") -> dict:
    if ok is None:
        return {"status": "unchecked", "reason": reason or "could not evaluate"}
    return {"status": "verified" if ok else "failed", "reason": reason}


def _real_roots(eq: sp.Expr, var: sp.Symbol) -> list | None:
    try:
        sols = sp.solve(eq, var)
    except (NotImplementedError, ValueError, TypeError):
        return None
    out = []
    for s in sols:
        v = _num(s)
        if v is not None and abs(v.imag) < 1e-9:
            out.append(v.real)
    return out


def _equation_solutions(check: dict) -> dict:
    var = sp.Symbol(check.get("variable") or "x")
    eq = parse_equation(check["expr"])
    values = [parse(v) for v in check.get("values", []) if str(v).strip()]
    for val in values:
        residual = eq.subs(var, val)
        try:
            if sp.simplify(residual) == 0:
                continue
        except Exception:  # noqa: BLE001 - simplify can fail on odd input; fall back to numbers
            pass
        if not _close(residual, 0):
            return _result(False, f"{val} does not satisfy the equation")
    roots = _real_roots(eq, var) if eq.is_polynomial(var) or len(eq.free_symbols) == 1 else None
    if roots is not None:
        given = [_num(v) for v in values]
        for r in roots:
            if not any(g is not None and abs(g - r) <= 1e-7 * max(1.0, abs(r)) for g in given):
                return _result(False, f"missing solution {r:g}")
        return _result(True)
    return _result(True if values else None, "" if values else "no values given")


def _derivative(check: dict) -> dict:
    var = sp.Symbol(check.get("variable") or "x")
    return _result(_zero_at_points(sp.diff(parse(check["expr"]), var) - parse(check["value"])))


def _antiderivative(check: dict) -> dict:
    var = sp.Symbol(check.get("variable") or "x")
    return _result(_zero_at_points(sp.diff(parse(check["value"]), var) - parse(check["expr"])))


def _definite_integral(check: dict) -> dict:
    var = sp.Symbol(check.get("variable") or "x")
    f = sp.lambdify(var, parse(check["expr"]), "mpmath")
    lo, hi = _num(parse(check["lower"])), _num(parse(check["upper"]))
    if lo is None or hi is None:
        return _result(None)
    numeric = mpmath.quad(f, [lo.real, hi.real])
    return _result(_close(sp.Float(str(numeric)), parse(check["value"])))


def _limit(check: dict) -> dict:
    var = sp.Symbol(check.get("variable") or "x")
    lim = sp.limit(parse(check["expr"]), var, parse(check["point"]))
    return _result(_close(lim, parse(check["value"])) or lim == parse(check["value"]))


def _value(check: dict) -> dict:
    return _result(_close(parse(check["expr"]), parse(check["value"])))


def _rounded(check: dict) -> dict:
    """'numeric' answers are often rounded: allow half a unit in the last decimal given.
    Several numbers (a vector, both coordinates...): expr "f1; f2" with values ["v1", "v2"]."""
    exprs = [e for e in check["expr"].split(";") if e.strip()]
    values = [str(v) for v in check.get("values") or [] if str(v).strip()] or [str(check.get("value", ""))]
    if len(exprs) != len(values):
        return _result(None, "expr and values don't match")
    for expr, value in zip(exprs, values):
        exact, given = _num(parse(expr)), _num(parse(value.strip()))
        if exact is None or given is None:
            return _result(None)
        decimals = len(value.split(".")[1]) if "." in value else 0
        tol = max(0.5 * 10 ** -decimals + 1e-12, TOL * max(1.0, abs(exact)))
        if abs(exact - given) > tol:
            return _result(False, f"{value} should be {complex(exact).real:.6g}")
    return _result(True)


def _system(check: dict) -> dict:
    """Simultaneous equations: expr "eq1; eq2" (each "lhs - (rhs)" or "lhs = rhs"), values ["x=3", "y=2"]."""
    eqs = [parse_equation(e) for e in check["expr"].split(";") if e.strip()]
    sol = {}
    for item in check.get("values") or []:
        name, _, val = str(item).partition("=")
        if name.strip() and val.strip():
            sol[sp.Symbol(name.strip())] = parse(val.strip())
    if not eqs or not sol:
        return _result(None, "no values given")
    for eq in eqs:
        residual = eq.subs(sol)
        if residual.free_symbols:
            return _result(None, "not every unknown has a value")
        if not _close(residual, 0):
            return _result(False, "the values don't satisfy every equation")
    return _result(True)


def _simplify_equal(check: dict) -> dict:
    return _result(_zero_at_points(parse(check["expr"]) - parse(check["value"])))


CHECKS = {
    "equation_solutions": _equation_solutions,
    "system": _system,
    "expression_value": _value,
    "numeric": _rounded,
    "simplify_equal": _simplify_equal,
    "derivative": _derivative,
    "antiderivative": _antiderivative,
    "definite_integral": _definite_integral,
    "limit": _limit,
}


_NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?")


def _decimals(s: str) -> int:
    return len(s.split(".")[1]) if "." in s else 0


def _answer_numbers(text: str) -> list[tuple[float, int]]:
    """(value, decimals shown) for every number in the answer the student will see; a/b counts as a/b."""
    s = unicodedata.normalize("NFKC", text or "").replace("−", "-").replace("–", "-")
    out = []
    for m in _NUMBER.finditer(s):
        tok = m.group(0).replace(" ", "")
        if "/" in tok:
            a, b = tok.split("/")
            if float(b):
                out.append((float(a) / float(b), 12))
            tok = a
        out.append((float(tok), _decimals(tok)))
    return out


def _checked_values(check: dict) -> list[tuple[float, int]]:
    """The rational values a check confirmed, with the decimals the model gave (irrational ones are skipped:
    the answer may show them as π/4 or √2, which has no comparable number in the text)."""
    kind = check.get("type")
    if kind in ("numeric", "expression_value", "definite_integral", "limit"):
        raw = [str(v) for v in check.get("values") or [] if str(v).strip()] or [str(check.get("value", ""))]
    elif kind == "equation_solutions":
        raw = [str(v) for v in check.get("values") or []]
    elif kind == "system":
        raw = [str(v).partition("=")[2] for v in check.get("values") or []]
    else:
        return []                                   # symbolic answers (derivatives, simplifying): nothing to compare
    out = []
    for r in raw:
        r = r.strip()
        if not r:
            continue
        v = parse(r)
        if v.is_number and (v.is_Rational or "." in r):
            out.append((float(v), _decimals(r) if "." in r else (0 if v.is_Integer else 12)))
    return out


def answer_agrees(check: dict, answer: str) -> bool:
    """A verified check only counts if the answer shown to the student contains the same values.
    (A model can write correct check values and a different, wrong number in its final answer.)"""
    expected = _checked_values(check)
    if not expected or not answer.strip():
        return True
    shown = _answer_numbers(answer)
    for v, dv in expected:
        if not any(abs(a - v) <= 0.5 * 10 ** -min(dv, da) + 1e-9 * max(1.0, abs(v)) for a, da in shown):
            return False
    return True


def verify(check: dict, answer: str = "") -> dict:
    fn = CHECKS.get(check.get("type", "none"))
    if fn is None or not check.get("expr"):
        return {"status": "unchecked", "reason": "no machine check"}
    try:
        result = fn(check)
        if result["status"] == "verified" and not answer_agrees(check, answer):
            return _result(False, "the final answer doesn't match the checked values")
        return result
    except UnsafeExpression as e:
        return {"status": "unchecked", "reason": f"unsafe/unsupported: {e}"}
    except Exception as e:  # noqa: BLE001 - any SymPy failure means "can't check", not "verified"
        return {"status": "unchecked", "reason": f"error: {type(e).__name__}"}
