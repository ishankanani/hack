"""Admin-only commands (user ids in ADMIN_USER_IDS)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from ..ai.router import Router as AIRouter
from ..core.limits import Limits
from ..db import Repo

router = Router(name="admin")


def setup(admin_ids: set[int]) -> Router:
    router.message.filter(F.from_user.id.in_(admin_ids or {-1}))
    return router


@router.message(Command("stats"))
async def cmd_stats(message: Message, repo: Repo, limits: Limits, ai: AIRouter):
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds")
    st = await repo.stats(since)
    ev = st["events"]
    n = lambda k: ev.get(k, {}).get("n", 0)  # noqa: E731
    solved, cached = n("solve_done"), n("cache_hit")
    lines = [
        "📊 Last 24 h",
        f"users active: {st['active_users']}  new: {n('start')}",
        f"solves: {solved}  cache hits: {cached} ({100 * cached // max(1, solved + cached)}%)",
        f"tutor msgs: {n('tutor_msg')}  images: {n('image_rendered')} (+{n('image_cached')} reused)",
        f"limit hits: {n('limit_hit')}  capacity hits: {n('capacity_hit')}  wrong reports: {n('wrong_report')}",
        f"shared opens: {n('shared_open')}  referrals rewarded: {n('ref_reward')}  invites opened: {n('invite_opened')}",
        "verification: " + ", ".join(f"{k} {v['n']} (avg {v['avg_ms']} ms)" for k, v in st["solutions"].items()),
        f"guard: {await limits.guard_mode()}  solve pool used: {ai.pool_used('solve'):.0%}",
        "",
        "model  req  tokens  neurons  used  cooling",
    ]
    for r in ai.status():
        if r["enabled"]:
            lines.append(f"{r['model']}  {r['requests']}  {r['tokens']}  {r['neurons']}  {r['used']:.0%}  {r['cooling_s']}s")
            if r["last_error"]:
                lines.append(f"   ↳ last error: {r['last_error']}")
        else:
            lines.append(f"{r['model']}  (disabled)")
    await message.answer("\n".join(lines), parse_mode=None)


PROVIDER_NAMES = {"groq": "Groq", "cloudflare": "Cloudflare", "openrouter": "OpenRouter"}


def quota_report(ai: AIRouter, guard: str, free_plan: dict, now: datetime | None = None) -> str:
    """Today's use of every free limit, and about how much is left (shown by /quota)."""
    now = now or datetime.now(timezone.utc)
    reset = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), timezone.utc) - now
    h, m = divmod(int(reset.total_seconds()) // 60, 60)
    lines = [f"💰 Free quota today (resets in {h} h {m} m, at 00:00 UTC)",
             "API cost: $0. Every model runs on a free tier and is skipped before its limit, never billed.", ""]
    budget = ai.budget
    for name, spec in ai.specs.items():
        if not spec.enabled:
            why = "blocked: not a free model, it would be billed" if spec.paid_risk else "off"
            lines.append(f"{name} ({PROVIDER_NAMES.get(spec.provider, spec.provider)}): {why}")
            continue
        t, lim = budget.today[name], spec.limits
        parts = []
        if lim.get("rpd"):
            parts.append(f"requests {t['requests']:,} / {lim['rpd']:,}")
        if lim.get("tpd"):
            parts.append(f"tokens {t['tokens']:,} / {lim['tpd']:,}")
        if lim.get("neurons_per_day"):
            parts.append(f"neurons {t['neurons']:,.0f} / {lim['neurons_per_day']:,}")
        if spec.pool and spec.pool in budget.pools:
            parts.append(f"shared pool {budget._pool_neurons(spec.pool):,.0f} / "
                         f"{budget.pools[spec.pool]['neurons_per_day']:,}")
        cool = budget.cooling(name)
        lines.append(f"{name} ({PROVIDER_NAMES.get(spec.provider, spec.provider)}): "
                     f"{budget.fraction_used(spec):.0%} used" + (f", cooling {cool:.0f}s" if cool else ""))
        lines.append("   " + " · ".join(parts))
    lines += ["", f"Left today, about: {ai.calls_left('solve'):,} solves · {ai.calls_left('read_photo'):,} photo "
                  f"reads · {ai.calls_left('tutor'):,} tutor replies",
              "(Cloudflare models share one pool, so photo reads and Cloudflare solves draw on the same neurons.)",
              f"Per student: {free_plan.get('solves', '?')} solves + {free_plan.get('tutor', '?')} tutor messages a day."
              f" Capacity guard: {guard}.",
              "Cache hits, and engine answers when quota is low, use no quota."]
    return "\n".join(lines)


@router.message(Command("quota"))
async def cmd_quota(message: Message, limits: Limits, ai: AIRouter, settings):
    await ai.resync()
    free = (settings.limits.get("plans") or {}).get("free", {})
    await message.answer(quota_report(ai, await limits.guard_mode(), free), parse_mode=None)


PLANS = ("free", "premium")


@router.message(Command("setlimit"))
async def cmd_setlimit(message: Message, command: CommandObject, repo: Repo):
    parts = (command.args or "").split()
    plan = parts.pop(0) if parts and parts[0] in PLANS else "free"
    if len(parts) != 2 or parts[0] not in ("solves", "tutor") or not parts[1].isdigit():
        return await message.answer("Usage: /setlimit solves 8   ·   /setlimit tutor 15   ·   "
                                    "/setlimit premium solves 50", parse_mode=None)
    await repo.set_setting(f"limit_{parts[0]}" if plan == "free" else f"limit_{plan}_{parts[0]}", parts[1])
    await message.answer(f"✅ Daily {parts[0]} limit for the {plan} plan is now {parts[1]}")


@router.message(Command("setplan"))
async def cmd_setplan(message: Message, command: CommandObject, repo: Repo):
    parts = (command.args or "").split()
    if len(parts) != 2 or not parts[0].isdigit() or parts[1] not in PLANS:
        return await message.answer("Usage: /setplan <user_id> free|premium", parse_mode=None)
    if not await repo.get_user(int(parts[0])):
        return await message.answer("User not found (they need to /start the bot first)", parse_mode=None)
    await repo.set_user_flag(int(parts[0]), "plan", parts[1])
    await message.answer(f"✅ {parts[0]} is now on the {parts[1]} plan")


@router.message(Command("guard"))
async def cmd_guard(message: Message, command: CommandObject, repo: Repo):
    mode = (command.args or "").strip()
    if mode not in ("normal", "soft", "hard", "auto"):
        return await message.answer("Usage: /guard normal|soft|hard|auto", parse_mode=None)
    await repo.set_setting("guard_mode", mode)
    await message.answer(f"✅ Capacity guard: {mode}")


@router.message(Command("grant"))
async def cmd_grant(message: Message, command: CommandObject, repo: Repo, settings):
    parts = (command.args or "").split()
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return await message.answer("Usage: /grant <user_id> <n>", parse_mode=None)
    await repo.grant(int(parts[0]), settings.user_day(), int(parts[1]))
    await message.answer(f"✅ Gave {parts[1]} bonus solves today to {parts[0]}")


@router.message(Command("ban", "unban"))
async def cmd_ban(message: Message, command: CommandObject, repo: Repo):
    arg = (command.args or "").strip()
    if not arg.isdigit():
        return await message.answer("Usage: /ban <user_id>", parse_mode=None)
    banned = message.text.startswith("/ban")
    await repo.set_user_flag(int(arg), "is_banned", 1 if banned else 0)
    await message.answer(f"✅ {'Banned' if banned else 'Unbanned'} {arg}")


@router.message(Command("flag"))
async def cmd_flag(message: Message, command: CommandObject, repo: Repo):
    arg = (command.args or "").strip()
    if not arg.isdigit():
        return await message.answer("Usage: /flag <solution_id>", parse_mode=None)
    ok = await repo.flag_solution(int(arg))
    await message.answer("✅ Removed from cache" if ok else "Not found")


@router.message(Command("user"))
async def cmd_user(message: Message, command: CommandObject, repo: Repo, limits: Limits):
    arg = (command.args or "").strip()
    if not arg.isdigit():
        return await message.answer("Usage: /user <user_id>", parse_mode=None)
    u = await repo.get_user(int(arg))
    if not u:
        return await message.answer("Not found")
    st = await limits.status(int(arg))
    await message.answer(
        f"{u['user_id']} @{u['username']} since {u['created_at'][:10]} source={u['start_source']} "
        f"banned={u['is_banned']} tutor_mode={u['tutor_mode']} plan={u['plan']} class={u['grade']} "
        f"lang={u['explain_lang']} solved={u['total_solves']} streak={u['streak']} ref_by={u['referred_by']}\n"
        f"solves left {st['solves_left']}/{st['solves_limit']}, tutor left {st['tutor_left']}/{st['tutor_limit']}",
        parse_mode=None)
