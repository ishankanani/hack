"""The golden set and the scoring used by scripts/eval_golden.py (offline: no API calls)."""
import pytest
import yaml

from mathfix.config import ROOT
from mathfix.mathcheck.quick import quick_solve
from scripts.eval_golden import correct, numbers_in

PROBLEMS = yaml.safe_load((ROOT / "tests" / "golden" / "problems.yaml").read_text(encoding="utf-8"))


def test_scoring_reads_numbers_fractions_and_unicode_minus():
    assert numbers_in("θ_new ≈ [0.262, −0.427]")[-2:] == [0.262, -0.427]
    assert correct("x = 16 and y = 9", [16, 9]) and correct("P = 1/6", [0.16667])
    assert correct("≈ 22.17", [22.17]) and not correct("x = 15", [16])
    assert correct("[0.09, 0.245, 0.665]", [0.090, 0.245, 0.665])


@pytest.mark.parametrize("p", [p for p in PROBLEMS if p["cat"] == "school-engine"], ids=lambda p: p["q"])
def test_engine_answers_every_engine_problem_correctly_and_instantly(p):
    out = quick_solve(p["q"])
    assert out is not None and correct(out["answer_text"], [float(a) for a in p["answer"]])
