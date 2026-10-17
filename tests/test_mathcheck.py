import pytest

from mathfix.mathcheck.quick import quick_solve
from mathfix.mathcheck.safe import UnsafeExpression, check_text
from mathfix.mathcheck.sandbox import Sandbox, SandboxTimeout
from mathfix.mathcheck.text import is_hard, latex_to_text, problem_key, to_ascii_math
from mathfix.mathcheck.verify import verify


@pytest.mark.parametrize("q,answer", [
    ("2x+3=11", "x = 4"),
    ("Solve 2x² − 8x + 6 = 0", "x = 1 or x = 3"),
    ("15% of 240", "36"),
    ("3/4 + 5/6", "19/12 ≈ 1.58333"),
    ("what is 12*7?", "84"),
    ("x^2+1=0", "no real solutions"),
    ("0.1+0.2", "3/10 ≈ 0.3"),
    ("Find x: 3 × 4 − 2 = x", "x = 10"),
])
def test_quick_solve(q, answer):
    assert quick_solve(q)["answer_text"] == answer


@pytest.mark.parametrize("q", ["x+y=3", "x^3+x=1", "sin(x)=0.5", "prove that root 2 is irrational", ""])
def test_quick_solve_leaves_hard_ones_to_ai(q):
    assert quick_solve(q) is None


@pytest.mark.parametrize("bad", ["__import__('os')", "x._class_", "lambda: 1", "open(1)", "a" * 400, "eval(1)"])
def test_unsafe_input_rejected(bad):
    with pytest.raises(UnsafeExpression):
        check_text(bad)
    assert quick_solve(bad) is None


@pytest.mark.parametrize("check,status", [
    ({"type": "equation_solutions", "expr": "2*x**2-8*x+6", "values": ["1", "3"]}, "verified"),
    ({"type": "equation_solutions", "expr": "2*x**2-8*x+6", "values": ["1"]}, "failed"),     # missing root
    ({"type": "equation_solutions", "expr": "2*x**2-8*x+6", "values": ["2", "3"]}, "failed"),
    ({"type": "derivative", "expr": "x^3*sin(x)", "value": "3x^2 sin(x) + x^3 cos(x)"}, "verified"),
    ({"type": "derivative", "expr": "x^3*sin(x)", "value": "3x^2 cos(x)"}, "failed"),
    ({"type": "antiderivative", "expr": "2x cos(x^2)", "value": "sin(x^2)"}, "verified"),
    ({"type": "definite_integral", "expr": "x^2", "lower": "0", "upper": "3", "value": "9"}, "verified"),
    ({"type": "definite_integral", "expr": "x^2", "lower": "0", "upper": "3", "value": "8"}, "failed"),
    ({"type": "limit", "expr": "sin(x)/x", "point": "0", "value": "1"}, "verified"),
    ({"type": "simplify_equal", "expr": "(x+1)^2", "value": "x^2+2x+1"}, "verified"),
    ({"type": "simplify_equal", "expr": "(x+1)^2", "value": "x^2+1"}, "failed"),
    ({"type": "numeric", "expr": "pi*7^2", "value": "153.94"}, "verified"),
    ({"type": "numeric", "expr": "pi*7^2", "value": "150"}, "failed"),
    ({"type": "expression_value", "expr": "3/4+5/6", "value": "19/12"}, "verified"),
    ({"type": "none", "expr": ""}, "unchecked"),
    ({"type": "expression_value", "expr": "import os", "value": "1"}, "unchecked"),   # unsafe -> never "verified"
])
def test_verify(check, status):
    assert verify(check)["status"] == status


def test_latex_to_text():
    assert latex_to_text(r"x=\frac{-b\pm\sqrt{b^{2}-4ac}}{2a}") == "x=(-b±√(b²-4ac))/2a"
    assert latex_to_text(r"x=1 \text{ or } x=3") == "x=1 or x=3"
    assert latex_to_text(r"\left(\frac{1}{2}\right)^{n+1}") == "(1/2)ⁿ⁺¹"


def test_problem_key_ignores_wording_and_spaces():
    assert problem_key("Solve 2x + 3 = 11") == problem_key("2x+3=11?")
    assert problem_key("2x+3=11") != problem_key("2x+3=12")
    assert to_ascii_math("Solve 2x² − 8x = 0") == "2x^2 - 8x = 0"


def test_is_hard():
    assert is_hard("d/dx x^2 sin x") and is_hard("∫ x dx") and not is_hard("2x + 3 = 11")


def _sleep_forever():
    import time
    time.sleep(30)


async def test_real_sandbox_kills_runaway_work():
    sb = Sandbox(workers=1)
    try:
        assert (await sb.run(quick_solve, "2x+3=11", timeout=60))["answer_text"] == "x = 4"
        with pytest.raises(SandboxTimeout):
            await sb.run(_sleep_forever, timeout=0.5)
        # the pool was restarted and still works
        assert (await sb.run(verify, {"type": "numeric", "expr": "2+2", "value": "4"}, timeout=60))["status"] == "verified"
    finally:
        await sb.close()
