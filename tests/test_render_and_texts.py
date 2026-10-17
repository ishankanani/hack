import io

from PIL import Image

from mathfix.bot import keyboards, texts
from mathfix.render.handwriting import render_solution
from mathfix.schemas import Solution


def test_render_solution_png():
    data = {"problem_text": "Solve 2x² − 8x + 6 = 0", "problem_latex": "2x^{2}-8x+6=0",
            "steps": [{"say": "Divide everything by 2", "math": "x^{2}-4x+3=0"},
                      {"say": "Broken latex falls back to text", "math": r"\begin{matrix}1\end{matrix}"}],
            "final_answer": "x = 1 or x = 3", "final_answer_latex": r"x=1 \text{ or } x=3", "seed": 7}
    png = render_solution(data)
    img = Image.open(io.BytesIO(png))
    assert img.width == 1080 and 600 < img.height < 3000
    assert render_solution(data) == png                     # deterministic -> file_id reuse is safe


def test_answer_message_and_keyboard():
    sol = Solution.model_validate({"steps": [{"say": "Use <this>", "math": r"\frac{1}{2}"}],
                                   "final_answer": "x = 1/2"})
    msg = texts.answer(sol, "2x = 1", "verified", from_photo=True, tutor_first=False, other_problems=["x=2"])
    assert "I read:" in msg and "&lt;this&gt;" in msg and "1/2" in msg and "Checked" in msg and "1 more" in msg
    tutor_msg = texts.answer(sol, "2x = 1", "verified", from_photo=False, tutor_first=True, other_problems=[])
    assert "x = 1/2" not in tutor_msg
    kbd = keyboards.answer_kb(42, from_photo=True, tutor_first=False, n_others=1)
    datas = [b.callback_data for row in kbd.inline_keyboard for b in row]
    assert datas[0] == "img:42" and "fix:42" in datas and "q:42:0" in datas
    assert all(len(d.encode()) <= 64 for d in datas)


def test_usage_text():
    st = {"solves_left": 2, "solves_limit": 5, "tutor_left": 9, "tutor_limit": 15, "reset_in_s": 5 * 3600 + 12 * 60}
    assert "2 of 5" in texts.usage(st) and "5 h 12 m" in texts.usage(st)
