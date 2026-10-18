import pytest

from mathfix.mathcheck.quick import quick_solve
from mathfix.mathcheck.safe import UnsafeExpression, check_text
from mathfix.mathcheck.sandbox import Sandbox, SandboxTimeout
from mathfix.mathcheck.text import is_hard, latex_to_text, pretty_math, pretty_text, problem_key, to_ascii_math
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
    assert latex_to_text(r"x=\frac{-b\pm\sqrt{b^{2}-4ac}}{2a}") == "x=(-b±√(b²-4ac))/(2a)"
    assert latex_to_text(r"x=1 \text{ or } x=3") == "x=1 or x=3"
    assert latex_to_text(r"\left(\frac{1}{2}\right)^{n+1}") == "(1/2)ⁿ⁺¹"


@pytest.mark.parametrize("latex, text", [
    # from a real answer that showed raw LaTeX in Telegram
    (r"\min_{W,b} \frac{1}{n}\|XW + b\mathbf 1 - y\|_2^2 + \lambda\|W\|_*",
     "min (over W,b) (1/n)‖XW + b1 - y‖₂² + λ‖W‖*"),
    (r"\mathbf{1}^{T}(XW+b\mathbf{1}-y)=0", "1ᵀ(XW+b1-y)=0"),
    (r"X^{\top}R + \lambda G = 0,\; G \in \partial\|W\|_*", "XᵀR + λG = 0, G ∈ ∂‖W‖*"),
    (r"\{UV^{T}+Q \mid \|Q\|_2 \le 1\}", "{UVᵀ+Q | ‖Q‖₂ ≤ 1}"),
    (r"W \in \mathbb{R}^{d \times k}", "W ∈ ℝ^(d × k)"),
    (r"\lim_{x \to 0} \frac{\sin x}{x} = 1", "lim (x → 0) (sin x)/x = 1"),
    (r"\sum_{i=1}^{n} i = \frac{n(n+1)}{2}", "Σᵢ₌₁ⁿ i = n(n+1)/2"),
    (r"\int_0^1 x^2\,dx = \frac{1}{3}", "∫₀¹ x² dx = 1/3"),
    (r"\frac{dy}{dx} = 3x^2", "dy/dx = 3x²"),
    (r"2\frac{1}{2} + x^{10}", "2 1/2 + x¹⁰"),
    (r"\angle ABC = 90^{\circ}", "∠ ABC = 90°"),
    (r"\begin{pmatrix}1 & 2 \\ 3 & 4\end{pmatrix}", "(1 2 ; 3 4)"),
    (r"e^{i\pi} + \pmod{7}", "e^(iπ) + (mod 7)"),
    (r"\int_{0}^{\infty} \neg p \leqslant 3", "∫₀^∞ ¬ p ≤ 3"),     # \in must not eat \int / \infty
])
def test_latex_to_text_covers_university_notation(latex, text):
    assert latex_to_text(latex) == text


def test_pretty_math_and_text():
    assert pretty_math("x^2 - 5x + 6 = 0") == "x² - 5x + 6 = 0"
    assert pretty_math("sqrt(16) + x**3 <= 2") == "√(16) + x³ ≤ 2"
    assert pretty_math(r"min_{W,b} \frac{1}{n}||XW - y||_2^2") == "min (over W,b) (1/n)‖XW - y‖₂²"
    assert pretty_math("Cost is $5 and $7\n15% of 240") == "Cost is $5 and $7\n15% of 240"
    # typed maths from a real logistic-regression answer
    assert pretty_math("g_0 = e * x_0 = (-0.31002552)*2") == "g₀ = e·x₀ = (-0.31002552)·2"
    assert pretty_math("Compute θ^(new), σ(z) = 1/(1+e^(-z)), λ*θ_1") == "Compute θⁿᵉʷ, σ(z) = 1/(1+e⁻ᶻ), λ·θ₁"
    assert pretty_math("h_θ(x) = σ(θ^Tx)") == "h_θ(x) = σ(θ^Tx)"                  # no Unicode form: left as is
    assert pretty_text(r"Subtract \(3\) from **both** sides") == "Subtract 3 from both sides"
    assert pretty_text(r"Use the subgradient of \|W\|_*") == "Use the subgradient of ‖W‖*"
    assert pretty_text("So $x^2 = 4$, cost $5 and $7") == "So x² = 4, cost $5 and $7"


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
