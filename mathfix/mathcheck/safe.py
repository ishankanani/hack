"""Safe parsing of maths text into SymPy.

SymPy's parse_expr uses Python eval, so text from users or models is whitelisted first:
only maths characters, known function names and single-letter variables. Everything here
runs inside the sandbox worker process (see sandbox.py), never in the bot process.
"""
from __future__ import annotations

import re

import sympy as sp
from sympy.parsing.sympy_parser import (
    convert_xor, implicit_multiplication_application, parse_expr, rationalize, standard_transformations,
)

MAX_LEN = 300
_ALLOWED_CHARS = re.compile(r"^[0-9a-zA-Z+\-*/^().,=!\s]*$")
_IDENT = re.compile(r"[A-Za-z]+")

FUNCTIONS = {
    "sin": sp.sin, "cos": sp.cos, "tan": sp.tan, "cot": sp.cot, "sec": sp.sec, "csc": sp.csc,
    "asin": sp.asin, "acos": sp.acos, "atan": sp.atan, "arcsin": sp.asin, "arccos": sp.acos,
    "arctan": sp.atan, "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh,
    "log": sp.log, "ln": sp.log, "exp": sp.exp, "sqrt": sp.sqrt, "Abs": sp.Abs, "abs": sp.Abs,
    "factorial": sp.factorial, "binomial": sp.binomial, "floor": sp.floor, "ceiling": sp.ceiling,
}
CONSTANTS = {"pi": sp.pi, "E": sp.E, "e": sp.E, "I": sp.I, "oo": sp.oo, "inf": sp.oo, "infinity": sp.oo}
VARIABLES = set("abcdhkmnpqrstuvwxyz") | {"theta", "alpha", "beta"}

# rationalize: 0.1 is parsed as exactly 1/10, so 0.1 + 0.2 == 3/10
_TRANSFORMS = standard_transformations + (implicit_multiplication_application, convert_xor, rationalize)
_GLOBALS = {
    "Integer": sp.Integer, "Float": sp.Float, "Number": sp.Number, "Rational": sp.Rational, "Symbol": sp.Symbol,
    "Function": sp.Function, "factorial": sp.factorial, **FUNCTIONS, **CONSTANTS,
}


class UnsafeExpression(ValueError):
    pass


def check_text(text: str) -> str:
    text = (text or "").strip()
    if not text or len(text) > MAX_LEN:
        raise UnsafeExpression("empty or too long")
    if "__" in text or "_" in text or not _ALLOWED_CHARS.match(text):
        raise UnsafeExpression("characters not allowed")
    for word in _IDENT.findall(text):
        if word in FUNCTIONS or word in CONSTANTS or word in VARIABLES:
            continue
        # implicit multiplication of single letters, e.g. "xy" or "2ab"
        if all(ch in VARIABLES for ch in word) and len(word) <= 3:
            continue
        raise UnsafeExpression(f"unknown name: {word}")
    return text


def parse(text: str) -> sp.Expr:
    """Parse one expression (no '=')."""
    text = check_text(text)
    if "=" in text:
        raise UnsafeExpression("use parse_equation for '='")
    symbols = {v: sp.Symbol(v) for v in VARIABLES}
    symbols["e"] = sp.E
    return parse_expr(text, local_dict=symbols, global_dict=dict(_GLOBALS), transformations=_TRANSFORMS,
                      evaluate=True)


def parse_equation(text: str) -> sp.Expr:
    """'lhs = rhs' -> lhs - rhs; a bare expression is treated as '= 0'."""
    text = check_text(text)
    if text.count("=") > 1:
        raise UnsafeExpression("more than one '='")
    if "=" in text:
        lhs, rhs = text.split("=")
        return parse(lhs) - parse(rhs)
    return parse(text)
