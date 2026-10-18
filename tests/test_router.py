import json
import httpx
import pytest

from mathfix.ai.router import AllModelsBusy, Router, extract_json
from mathfix.schemas import Reading, Solution

from .conftest import FakeAI

GOOD = {"steps": [{"say": "Subtract 3", "math": "2x=8"}], "final_answer": "x = 4",
        "check": {"type": "equation_solutions", "expr": "2*x+3-11", "values": ["4"]}, "confidence": 0.9}


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    async def sleep(self, s):
        self.t += s


def make(models_cfg, fake, repo=None):
    clock = Clock()
    return Router(models_cfg, repo, transport=fake.transport, clock=clock, sleep=clock.sleep), clock


MSG = [{"role": "user", "content": "2x+3=11"}]


async def test_first_model_used_with_effort_and_json_mode(models_cfg):
    fake = FakeAI()
    fake.add("openai/gpt-oss-120b", GOOD)
    r, _ = make(models_cfg, fake)
    res = await r.run("solve", MSG, schema=Solution, effort="low")
    assert res.model == "groq_oss_120b" and res.data.final_answer == "x = 4"
    call = fake.calls[0]
    assert call["reasoning_effort"] == "low" and call["response_format"] == {"type": "json_object"}
    assert call["url"] == "https://api.groq.com/openai/v1/chat/completions"


async def test_placeholder_models_are_disabled(models_cfg):
    r, _ = make(models_cfg, FakeAI())
    names = [s.name for s in r.enabled_models("solve")]
    assert names == ["groq_oss_120b", "cf_oss_120b"]          # groq_qwen / or_free_text still have "<...>" ids


async def test_429_falls_back_to_next_model_and_cools_down(models_cfg):
    fake = FakeAI()
    fake.add("openai/gpt-oss-120b", httpx.Response(429, headers={"retry-after": "40"}))
    fake.add("@cf/openai/gpt-oss-120b", GOOD)
    r, _ = make(models_cfg, fake)
    res = await r.run("solve", MSG, schema=Solution)
    assert res.model == "cf_oss_120b"
    assert fake.calls[1]["url"] == "https://api.cloudflare.com/client/v4/accounts/acct/ai/v1/chat/completions"
    assert r.budget.cooling("groq_oss_120b") > 0


async def test_bad_json_retried_once_on_same_model(models_cfg):
    fake = FakeAI()
    fake.add("openai/gpt-oss-120b", "sorry, here: {not json", "```json\n" + __import__("json").dumps(GOOD) + "\n```")
    r, _ = make(models_cfg, fake)
    res = await r.run("solve", MSG, schema=Solution)
    assert res.model == "groq_oss_120b" and fake.models_called() == ["openai/gpt-oss-120b"] * 2
    assert "not valid JSON" in fake.calls[1]["messages"][-1]["content"]


async def test_bad_json_twice_moves_to_next_model(models_cfg):
    fake = FakeAI()
    fake.add("openai/gpt-oss-120b", "nope", "still nope")
    fake.add("@cf/openai/gpt-oss-120b", GOOD)
    r, _ = make(models_cfg, fake)
    assert (await r.run("solve", MSG, schema=Solution)).model == "cf_oss_120b"


async def test_daily_budget_spent_model_is_skipped_without_calling(models_cfg):
    fake = FakeAI()
    fake.add("@cf/openai/gpt-oss-120b", GOOD)
    r, _ = make(models_cfg, fake)
    r.budget.today["groq_oss_120b"]["tokens"] = 180000
    res = await r.run("solve", MSG, schema=Solution)
    assert res.model == "cf_oss_120b" and fake.models_called() == ["@cf/openai/gpt-oss-120b"]


async def test_all_daily_budgets_spent_raises_daily(models_cfg):
    r, _ = make(models_cfg, FakeAI())
    r.budget.today["groq_oss_120b"]["requests"] = 900
    r.budget.today["cf_oss_120b"]["neurons"] = 9000
    with pytest.raises(AllModelsBusy) as e:
        await r.run("solve", MSG, schema=Solution)
    assert e.value.daily


async def test_per_minute_limit_waits_then_succeeds(models_cfg):
    fake = FakeAI()
    fake.add("openai/gpt-oss-120b", GOOD)
    r, clock = make(models_cfg, fake)
    r.budget.today["cf_oss_120b"]["neurons"] = 9000               # other model out for the day
    for _ in range(27):                                            # groq rpm limit reached this minute
        r.budget.minute["groq_oss_120b"].append((clock() - 40, 10))   # made 40 s ago
    waits = []

    async def on_wait():
        waits.append(1)

    res = await r.run("solve", MSG, schema=Solution, on_wait=on_wait)
    assert res.model == "groq_oss_120b" and waits == [1] and 1020 <= clock.t <= 1030


async def test_vision_step_only_uses_vision_models(models_cfg):
    fake = FakeAI()
    fake.add("@cf/meta/llama-4-scout-17b-16e-instruct",
             {"problems": ["2x+3=11"], "problem_text": "2x+3=11", "problem_latex": "2x+3=11"})
    r, _ = make(models_cfg, fake)
    res = await r.run("read_photo", MSG, schema=Reading, need_vision=True)
    assert res.model == "cf_llama4_scout" and res.data.problem_text == "2x+3=11"


async def test_cloudflare_models_share_one_neuron_pool(models_cfg):
    r, _ = make(models_cfg, FakeAI())
    scout, oss = r.specs["cf_llama4_scout"], r.specs["cf_oss_120b"]
    assert r.budget.has_room(oss, 1500)[0]
    r.budget.record(scout, 250000, 40000)                          # ~9,200 neurons spent by the vision model
    assert r.budget.today["cf_oss_120b"]["neurons"] == 0
    assert r.budget.has_room(oss, 1500) == (False, "day")          # ...so the other Cloudflare model is out too


async def test_usage_is_recorded_and_pool_used_grows(models_cfg, repo):
    fake = FakeAI()
    fake.add("openai/gpt-oss-120b", GOOD)
    r, _ = make(models_cfg, fake, repo)
    before = r.pool_used("solve")
    await r.run("solve", MSG, schema=Solution)
    rows = await repo.provider_day(r.budget.day)
    assert rows["groq_oss_120b"]["requests"] == 1 and rows["groq_oss_120b"]["tokens_in"] == 100
    assert r.pool_used("solve") > before


def test_extract_json():
    assert extract_json('Sure! {"a": 1} hope it helps') == {"a": 1}


def cut_off(content="{\"steps\": [{\"say\": \"Compute z"):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}, "finish_reason": "length"}],
                                     "usage": {"prompt_tokens": 900, "completion_tokens": 2500}})


def test_latex_inside_json_is_repaired_not_rejected_or_corrupted():
    raw = (r'{"final_answer": "W = (X^T X + \lambda I)^{-1} X^T y", "math": "\frac{1}{n}\|XW - y\|_2^2 + \nabla \beta",'
           r' "say": "line one\nNext \"quoted\" \\alpha é"}')
    data = extract_json(raw)
    assert data["final_answer"] == r"W = (X^T X + \lambda I)^{-1} X^T y"
    assert data["math"] == r"\frac{1}{n}\|XW - y\|_2^2 + \nabla \beta"      # not form-feed / backspace
    assert data["say"] == 'line one\nNext "quoted" \\alpha é'                 # real escapes still work


async def test_answer_cut_off_by_max_tokens_is_retried_with_more_room(models_cfg):
    fake = FakeAI()
    fake.add("openai/gpt-oss-120b", cut_off(), GOOD)
    r, _ = make(models_cfg, fake)
    res = await r.run("solve", MSG, schema=Solution, effort="medium")
    assert res.model == "groq_oss_120b" and res.data.final_answer == "x = 4"
    assert [c["max_tokens"] for c in fake.calls] == [2500, 5500]


async def test_big_problems_start_with_the_big_budget_and_give_up_cleanly_when_still_cut(models_cfg):
    fake = FakeAI()
    fake.add("openai/gpt-oss-120b", cut_off(), cut_off())
    fake.add("@cf/openai/gpt-oss-120b", GOOD)
    r, _ = make(models_cfg, fake)
    res = await r.run("solve", MSG, schema=Solution, effort="medium", big=True)
    assert fake.calls[0]["max_tokens"] == 5500 and res.model == "cf_oss_120b"
    assert fake.calls[-1]["max_tokens"] == 6000
    assert "cut off" in r.last_error["groq_oss_120b"] and r.budget.cooling("groq_oss_120b") <= 20


async def test_groq_json_validate_failed_is_repaired_instead_of_benching_the_model(models_cfg):
    bad = json.dumps({**GOOD, "final_answer": "x = 4"}).replace('"x = 4"', '"x = 4, so \\\\lambda"')
    bad = bad.replace("\\\\lambda", "\\lambda")                          # a raw \lambda: invalid JSON
    fake = FakeAI()
    fake.add("openai/gpt-oss-120b", httpx.Response(400, json={"error": {
        "message": "Failed to generate JSON.", "type": "invalid_request_error",
        "code": "json_validate_failed", "failed_generation": bad}}))
    r, _ = make(models_cfg, fake)
    res = await r.run("solve", MSG, schema=Solution)
    assert res.model == "groq_oss_120b" and res.data.final_answer == r"x = 4, so \lambda"
    assert r.budget.cooling("groq_oss_120b") == 0


async def test_request_too_large_only_cools_briefly(models_cfg):
    fake = FakeAI()
    fake.add("openai/gpt-oss-120b", httpx.Response(413, json={"error": {"message": "Request too large"}}))
    fake.add("@cf/openai/gpt-oss-120b", GOOD)
    r, _ = make(models_cfg, fake)
    res = await r.run("solve", MSG, schema=Solution, big=True)
    assert res.model == "cf_oss_120b" and 0 < r.budget.cooling("groq_oss_120b") <= 20
