import io
import sqlite3
from datetime import date, timedelta

from PIL import Image

from mathfix.bot import keyboards, texts
from mathfix.core import share
from mathfix.db import Repo
from mathfix.render.handwriting import Pen, render_solution
from mathfix.schemas import Solution

DATA = {"problem_text": "Solve 2x² − 8x + 6 = 0", "problem_latex": "2x^{2}-8x+6=0",
        "steps": [{"say": "Divide everything by 2 (√, π, ≤, ≠ must not be boxes)", "math": "x^{2}-4x+3=0"},
                  {"say": "Broken latex falls back to text", "math": r"\begin{matrix}1\end{matrix}"}],
        "final_answer": "x = 1 or x = 3", "final_answer_latex": r"x=1 \text{ or } x=3", "seed": 7,
        "topic": "quadratic_equations", "difficulty": 2, "verified": "verified",
        "key_idea": "Factorise, then set each bracket to zero.", "tip": "Don't forget the second root.",
        "qr_url": "https://t.me/mathfixbot?start=s_7_0123456789"}


def test_render_solution_png_is_branded_and_deterministic():
    png = render_solution(DATA)
    img = Image.open(io.BytesIO(png))
    assert img.width == 1080 and 1000 < img.height < 4000
    assert render_solution(DATA) == png                      # same input, same image → file_id reuse is safe
    assert img.convert("RGB").getpixel((5, 5))[2] > 150      # brand-coloured header band
    plain = render_solution({**DATA, "qr_url": "", "key_idea": "", "tip": "", "verified": ""})
    assert len(plain) != len(png)


def test_symbols_missing_from_handwriting_font_use_the_fallback():
    pen = Pen(40)
    runs = pen.runs("x ≤ √π + 2")
    fallback_text = "".join(t for t, f in runs if f is pen.fallback)
    assert set("≤√π") <= set(fallback_text) and "x" not in fallback_text


def test_answer_message_layout_and_keyboard():
    sol = Solution.model_validate({"topic": "linear_equations",
                                   "steps": [{"say": f"Step <{i}>", "math": r"\frac{1}{2}"} for i in range(5)],
                                   "final_answer": "x = 1/2", "key_idea": "Undo in reverse", "tip": "Watch signs"})
    msg = texts.answer(sol, "2x = 1", "verified", from_photo=True, tutor_first=False, other_problems=["x=2"],
                       foot="🧮 2/5 free solves left today")
    assert "<i>Linear equations</i>" in msg and "I read" in msg and "&lt;0&gt;" in msg
    assert "✅ <b>ANSWER:  x = 1/2</b>" in msg and "Key idea" in msg and "Watch out" in msg
    assert "<blockquote expandable>" in msg and "1️⃣" in msg and "5️⃣" in msg and "2/5 free solves" in msg
    tutor_msg = texts.answer(sol, "2x = 1", "verified", from_photo=False, tutor_first=True, other_problems=[],
                             name="Asha")
    assert "ANSWER" not in tutor_msg and "Asha" in tutor_msg
    kbd = keyboards.answer_kb(42, from_photo=True, tutor_first=False, n_others=1, share_url="https://t.me/share/url?x")
    btns = [b for row in kbd.inline_keyboard for b in row]
    assert btns[0].callback_data == "img:42" and any(b.url for b in btns)
    assert all(len(b.callback_data.encode()) <= 64 for b in btns if b.callback_data)


def test_usage_and_profile_text():
    st = {"solves_left": 2, "solves_limit": 5, "tutor_left": 9, "tutor_limit": 15, "reset_in_s": 5 * 3600 + 12 * 60}
    u = texts.usage(st)
    assert "<b>2</b> of 5" in u and "5 h 12 m" in u and "Free plan" in u
    p = texts.profile({"first_name": "Asha", "grade": "9-10", "explain_lang": "hinglish", "streak": 3,
                       "best_streak": 5, "total_solves": 12}, st, 2)
    assert "Class 9–10" in p and "Hinglish" in p and "<b>3</b> days" in p and "<b>12</b>" in p


def test_share_links_are_signed():
    payload = share.solution_payload(1234, "secret")
    assert payload.startswith("s_1234_") and len(payload) <= 64
    assert share.parse_solution(payload, "secret") == 1234
    assert share.parse_solution(payload, "other-secret") is None
    assert share.parse_solution("s_1235_" + payload.split("_")[2], "secret") is None
    assert share.parse_invite("ref_77") == 77 and share.parse_invite("ref_x") is None
    assert share.telegram_share_url("https://t.me/b?start=s_1", "hi there").startswith(
        "https://t.me/share/url?url=https%3A%2F%2Ft.me%2Fb%3Fstart%3Ds_1&text=hi%20there")


async def test_old_database_upgrades_in_place(tmp_path):
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)                              # schema from the first release
    con.execute("CREATE TABLE users (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,"
                " lang TEXT DEFAULT 'en', tutor_mode INTEGER DEFAULT 0, start_source TEXT,"
                " is_banned INTEGER DEFAULT 0, created_at TEXT NOT NULL, last_seen_at TEXT NOT NULL)")
    con.execute("INSERT INTO users(user_id, first_name, created_at, last_seen_at) VALUES (5, 'Old', 'x', 'x')")
    con.commit()
    con.close()
    repo = Repo(path)
    await repo.init()
    u = await repo.get_user(5)
    assert u["first_name"] == "Old" and u["plan"] == "free" and u["total_solves"] == 0 and u["onboarded"] == 0
    await repo.close()


async def test_streaks(repo):
    await repo.upsert_user(1, "a", "A", "en")
    d = date(2026, 10, 1)
    day = lambda n: (d + timedelta(days=n)).isoformat()      # noqa: E731
    r = await repo.record_solve(1, day(0), day(-1))
    assert r["streak"] == 1 and r["first_solve"]
    r = await repo.record_solve(1, day(0), day(-1))          # same day: streak unchanged
    assert r["streak"] == 1 and not r["new_day"] and r["total_solves"] == 2
    r = await repo.record_solve(1, day(1), day(0))           # next day: +1
    assert r["streak"] == 2 and r["new_day"]
    r = await repo.record_solve(1, day(5), day(4))           # gap: back to 1, best kept
    assert r["streak"] == 1 and r["best_streak"] == 2


def test_long_answers_drop_steps_instead_of_breaking_html():
    sol = Solution.model_validate({"steps": [{"say": "word " * 120, "math": "x^{2}+1"} for _ in range(10)],
                                   "final_answer": "x = 1"})
    msg = texts.answer(sol, "q", "verified", from_photo=False, tutor_first=False, other_problems=[])
    assert len(msg) <= 4000 and msg.count("<blockquote") == msg.count("</blockquote>")
    assert "more step(s) in the 🖼 solution image" in msg
