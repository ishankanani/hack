from mathfix.ai.router import Router
from mathfix.core.limits import Limits

from .conftest import FakeAI


async def make(settings, repo):
    ai = Router(settings.models, repo, transport=FakeAI().transport)
    await repo.upsert_user(1, "u", "U", "en")
    return Limits(settings, repo, ai, clock=lambda: 0), ai


async def test_reserve_commit_refund_and_limit(settings, repo):
    limits, _ = await make(settings, repo)
    for _ in range(5):                                   # limits.yaml: 5 solves/day
        r, why = await limits.reserve(1, "solves")
        assert why is None
        await limits.finish(r, counted=True)
    r, why = await limits.reserve(1, "solves")
    assert r is None and why == "limit"
    st = await limits.status(1)
    assert st["solves_left"] == 0 and st["tutor_left"] == 15


async def test_failed_solve_is_not_counted(settings, repo):
    limits, _ = await make(settings, repo)
    r, _ = await limits.reserve(1, "solves")
    await limits.finish(r, counted=False)
    assert (await limits.status(1))["solves_left"] == 5


async def test_reservations_block_parallel_overuse(settings, repo):
    limits, _ = await make(settings, repo)
    held = [(await limits.reserve(1, "solves"))[0] for _ in range(5)]
    assert all(held)
    assert (await limits.reserve(1, "solves"))[0] is None     # 5 in flight already


async def test_wrong_answer_refund_and_bonus(settings, repo):
    limits, _ = await make(settings, repo)
    r, _ = await limits.reserve(1, "solves")
    await limits.finish(r, True)
    assert await limits.refund_wrong(1)
    await repo.grant(1, settings.user_day(), 3)
    assert (await limits.status(1))["solves_left"] == 8


async def test_capacity_guard_modes(settings, repo):
    limits, ai = await make(settings, repo)
    assert await limits.guard_mode() == "normal"
    await repo.set_setting("guard_mode", "soft")
    assert await limits.effective_limit(1, "solves") == 3 and await limits.effective_limit(1, "tutor") == 8
    await repo.set_setting("guard_mode", "hard")
    r, why = await limits.reserve(1, "solves")
    assert r is None and why == "capacity"
    assert (await limits.reserve(1, "tutor"))[0] is not None   # tutor still works in hard mode
    await repo.set_setting("guard_mode", "auto")
    for spec in ai.enabled_models("solve"):                     # spend the whole free pool
        ai.budget.today[spec.name].update(requests=10**6, tokens=10**9, neurons=10**9)
    assert await limits.guard_mode() == "hard"


async def test_admin_and_ban(settings, repo):
    limits, _ = await make(settings, repo)
    assert await limits.effective_limit(999, "solves") > 1000
    await repo.set_user_flag(1, "is_banned", 1)
    assert await limits.reserve(1, "solves") == (None, "banned")


async def test_setlimit_override(settings, repo):
    limits, _ = await make(settings, repo)
    await repo.set_setting("limit_solves", "10")
    assert await limits.effective_limit(1, "solves") == 10


async def test_burst(settings, repo):
    limits, _ = await make(settings, repo)
    assert limits.begin(1) and not limits.begin(1)             # one at a time
    limits.end(1)
    for _ in range(4):
        assert limits.begin(1)
        limits.end(1)
    assert not limits.begin(1)                                  # 6th in the same minute
