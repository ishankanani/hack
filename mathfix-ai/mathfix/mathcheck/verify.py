"""Answer verification with SymPy (runs inside the sandbox worker).

verify(check) returns {"status": "verified" | "failed" | "unchecked", "reason": str}.
A crash or unsupported check is "unchecked", never "verified".
"""
from __future__ import annotations

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
    """'numeric' answers are often rounded: allow half a unit in the last decimal given."""
    exact, given = _num(parse(check["expr"])), _num(parse(check["value"]))
    if exact is None or given is None:
        return _result(None)
    decimals = len(check["value"].split(".")[1]) if "." in check["value"] else 0
    tol = max(0.5 * 10 ** -decimals + 1e-12, TOL * max(1.0, abs(exact)))
    return _result(abs(exact - given) <= tol)


def _simplify_equal(check: dict) -> dict:
    return _result(_zero_at_points(parse(check["expr"]) - parse(check["value"])))


CHECKS = {
    "equation_solutions": _equation_solutions,
    "expression_value": _value,
    "numeric": _rounded,
    "simplify_equal": _simplify_equal,
    "derivative": _derivative,
    "antiderivative": _antiderivative,
    "definite_integral": _definite_integral,
    "limit": _limit,
}


def verify(check: dict) -> dict:
    fn = CHECKS.get(check.get("type", "none"))
    if fn is None or not check.get("expr"):
        return {"status": "unchecked", "reason": "no machine check"}
    try:
        return fn(check)
    except UnsafeExpression as e:
        return {"status": "unchecked", "reason": f"unsafe/unsupported: {e}"}
    except Exception as e:  # noqa: BLE001 - any SymPy failure means "can't check", not "verified"
        return {"status": "unchecked", "reason": f"error: {type(e).__name__}"}
