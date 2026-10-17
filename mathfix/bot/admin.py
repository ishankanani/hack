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
        "verification: " + ", ".join(f"{k} {v['n']} (avg {v['avg_ms']} ms)" for k, v in st["solutions"].items()),
        f"guard: {await limits.guard_mode()}  solve pool used: {ai.pool_used('solve'):.0%}",
        "",
        "model  req  tokens  neurons  used  cooling",
    ]
    for r in ai.status():
        if r["enabled"]:
            lines.append(f"{r['model']}  {r['requests']}  {r['tokens']}  {r['neurons']}  {r['used']:.0%}  {r['cooling_s']}s")
        else:
            lines.append(f"{r['model']}  (disabled)")
    await message.answer("\n".join(lines), parse_mode=None)


@router.message(Command("setlimit"))
async def cmd_setlimit(message: Message, command: CommandObject, repo: Repo):
    parts = (command.args or "").split()
    if len(parts) != 2 or parts[0] not in ("solves", "tutor") or not parts[1].isdigit():
        return await message.answer("Usage: /setlimit solves 8   or   /setlimit tutor 15", parse_mode=None)
    await repo.set_setting(f"limit_{parts[0]}", parts[1])
    await message.answer(f"✅ Daily {parts[0]} limit is now {parts[1]}")


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
        f"banned={u['is_banned']} tutor_mode={u['tutor_mode']}\n"
        f"solves left {st['solves_left']}/{st['solves_limit']}, tutor left {st['tutor_left']}/{st['tutor_limit']}",
        parse_mode=None)
