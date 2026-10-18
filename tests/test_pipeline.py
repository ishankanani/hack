import io
import json

from PIL import Image, ImageDraw

from mathfix.ai.router import Router
from mathfix.core.pipeline import Pipeline
from mathfix.core.tutor import Tutor

from .conftest import FakeAI, InlineSandbox

SOLVER = "openai/gpt-oss-120b"
VISION = "@cf/meta/llama-4-scout-17b-16e-instruct"


def sol(answer, check, steps=1, confidence=0.9, topic="algebra"):
    return {"topic": topic, "steps": [{"say": f"step {i}", "math": "x"} for i in range(steps)],
            "final_answer": answer, "final_answer_latex": answer, "check": check, "confidence": confidence}


def make(settings, repo, fake):
    ai = Router(settings.models, repo, transport=fake.transport)
    return Pipeline(ai, repo, InlineSandbox()), ai


async def test_quick_path_answer_wins_and_is_verified(settings, repo):
    fake = FakeAI()
    fake.add(SOLVER, sol("x = 5 (model typo)", {"type": "none"}))
    p, _ = make(settings, repo, fake)
    out = await p.solve_text("2x + 3 = 11")
    assert out.status == "solved" and out.solution.final_answer == "x = 4" and out.verified == "verified"
    assert "verified correct answer is: x = 4" in fake.calls[0]["messages"][1]["content"]
    assert fake.calls[0]["reasoning_effort"] == "low"


async def test_second_solve_is_a_free_cache_hit(settings, repo):
    fake = FakeAI()
    fake.add(SOLVER, sol("x = 4", {"type": "none"}))
    p, _ = make(settings, repo, fake)
    await p.solve_text("2x+3=11")
    out = await p.solve_text("Solve 2x + 3 = 11?")
    assert out.from_cache and len(fake.calls) == 1


async def test_failed_check_gets_second_opinion_from_other_model(settings, repo, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    settings.models["models"]["groq_qwen"]["id"] = "qwen/qwen-test"
    fake = FakeAI()
    fake.add(SOLVER, sol("x = 2", {"type": "equation_solutions", "expr": "x**3 - 8 - x + 2", "values": ["3"]}))
    fake.add("qwen/qwen-test", sol("x = 2", {"type": "equation_solutions", "expr": "x**3 - x - 6", "values": ["2"]}))
    p, _ = make(settings, repo, fake)
    out = await p.solve_text("x^3 - x = 6")             # cubic: not on the SymPy quick path
    assert out.verified == "verified" and out.model == "groq_qwen"
    assert fake.models_called() == [SOLVER, "qwen/qwen-test"]


async def test_hard_unchecked_answers_that_agree_are_marked_agreed(settings, repo):
    settings.models["models"]["groq_qwen"]["id"] = "qwen/qwen-test"
    fake = FakeAI()
    fake.add(SOLVER, sol("It is irrational", {"type": "none"}, topic="proof"))
    fake.add("qwen/qwen-test", sol("it is irrational", {"type": "none"}, topic="proof"))
    p, _ = make(settings, repo, fake)
    out = await p.solve_text("prove that sqrt(2) is irrational")
    assert out.verified == "agreed"
    assert fake.calls[0]["reasoning_effort"] == "medium"


async def test_refused_and_ai_down_with_quick_answer(settings, repo):
    fake = FakeAI()
    fake.add(SOLVER, sol("", {"type": "none"}, steps=0, topic="refused"))
    p, _ = make(settings, repo, fake)
    assert (await p.solve_text("write my essay about 2 dogs")).status == "refused"
    # every model down: SymPy still answers simple questions
    out = await p.solve_text("15% of 240")
    assert out.status == "solved" and out.solution.final_answer == "36" and out.model == "sympy"


async def test_everything_busy_without_quick_answer(settings, repo):
    p, ai = make(settings, repo, FakeAI())
    for s in ai.enabled_models("solve"):
        ai.budget.today[s.name].update(requests=10**6, tokens=10**9, neurons=10**9)
    assert (await p.solve_text("x^3 - x = 6")).status == "capacity"


def photo_bytes():
    img = Image.new("RGB", (2000, 1500), "white")
    ImageDraw.Draw(img).text((100, 100), "2x + 3 = 11   and   x^2 = 9", fill="black")
    b = io.BytesIO()
    img.save(b, format="PNG")
    return b.getvalue()


async def test_photo_flow_reads_then_solves_and_caches_image(settings, repo):
    fake = FakeAI()
    fake.add(VISION, json.dumps({"problems": ["2x + 3 = 11", "x^2 = 9"], "problem_text": "2x + 3 = 11",
                                 "problem_latex": "2x+3=11", "confidence": 0.95}))
    fake.add(SOLVER, sol("x = 4", {"type": "none"}))
    p, _ = make(settings, repo, fake)
    stages = []

    async def progress(stage, info=""):
        stages.append((stage, info))

    out = await p.solve_photo(photo_bytes(), progress=progress)
    assert out.status == "solved" and out.solution.final_answer == "x = 4" and out.other_problems == ["x^2 = 9"]
    assert ("read", "2x + 3 = 11") in stages
    image_part = fake.calls[0]["messages"][1]["content"][1]["image_url"]["url"]
    assert image_part.startswith("data:image/jpeg;base64,")
    again = await p.solve_photo(photo_bytes())            # same photo: no AI calls at all
    assert again.from_cache and again.other_problems == ["x^2 = 9"] and len(fake.calls) == 2


async def test_unreadable_and_not_math_photos(settings, repo):
    fake = FakeAI()
    fake.add(VISION, {"readable": False}, {"is_math": False})
    p, _ = make(settings, repo, fake)
    assert (await p.solve_photo(photo_bytes())).status == "unreadable"
    img = Image.new("RGB", (300, 300), "blue")
    b = io.BytesIO()
    img.save(b, format="JPEG")
    assert (await p.solve_photo(b.getvalue())).status == "not_math"


async def test_tutor_uses_fast_model_and_keeps_history(settings, repo):
    fake = FakeAI()
    fake.add(SOLVER, sol("x = 4", {"type": "none"}))
    fake.add("openai/gpt-oss-20b", "Try subtracting 3 from both sides first.", "Because we want x alone.")
    p, ai = make(settings, repo, fake)
    out = await p.solve_text("2x+3=11")
    row = await repo.get_solution(out.solution_id)
    t = Tutor(ai, repo)
    assert "subtracting 3" in await t.reply(1, row, "hint")
    await t.reply(1, row, "ask", text="why subtract?")
    last = fake.calls[-1]["messages"]
    assert last[0]["role"] == "system" and "x = 4" in last[0]["content"]
    assert [m["role"] for m in last[1:]] == ["user", "assistant", "user"]


async def test_machine_learning_problem_gets_room_and_no_second_full_solve(settings, repo):
    fake = FakeAI()
    fake.add(SOLVER, sol("θ_new ≈ [0.262, −0.427]", {"type": "none"}, steps=7, topic="Logistic regression"))
    p, _ = make(settings, repo, fake)
    q = ("For a single training example in logistic regression with L2 regularization: h(x) = sigmoid(theta^T x). "
         "Given x = [2, -1], y = 1, theta = [0.2, -0.4], lambda = 0.1, alpha = 0.1. Compute theta after one step "
         "of gradient descent.")
    out = await p.solve_text(q)
    assert out.status == "solved" and out.verified == "unchecked" and len(fake.calls) == 1
    assert fake.calls[0]["max_tokens"] == 5500 and fake.calls[0]["reasoning_effort"] == "medium"
