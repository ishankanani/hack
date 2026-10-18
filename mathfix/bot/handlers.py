"""Telegram handlers for students. Dependencies (repo, limits, pipeline, …) are injected by aiogram
from the Dispatcher's workflow data (see main.py)."""
from __future__ import annotations

import io
import logging
import re
import time
from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from ..ai.router import AllModelsBusy
from ..config import Settings
from ..core import share
from ..core.limits import Limits
from ..core.pipeline import Outcome, Pipeline, cache_key
from ..core.tutor import Tutor
from ..db import Repo
from ..mathcheck.sandbox import Sandbox, SandboxTimeout
from ..render.handwriting import render_solution
from ..schemas import Solution
from . import keyboards as kb
from . import texts

log = logging.getLogger(__name__)
router = Router(name="student")

# short-lived per-user state (fine to lose on restart)
_last: dict[int, tuple[int, float]] = {}            # user -> (solution_id, time)   tutor context
_fix: dict[int, int] = {}                            # user -> solution_id awaiting a corrected question
_others: dict[tuple[int, int], list[str]] = {}       # (user, solution_id) -> other questions in the photo
_step: dict[tuple[int, int], int] = {}               # (user, solution_id) -> next step pointer
CONTEXT_TTL = 30 * 60
_QUESTION_START = re.compile(r"^(why|how|what|can|could|i don'?t|i dont|explain|is it|so|ok|but|wait)\b", re.I)
_MATHY = re.compile(r"[\d=+\-*/^√∫²³π]")


async def _ensure_user(repo: Repo, m: Message | CallbackQuery, source: str | None = None) -> dict:
    u = m.from_user
    await repo.upsert_user(u.id, u.username, u.first_name, u.language_code, source)
    return await repo.get_user(u.id)


def _name(user: dict) -> str:
    return (user.get("first_name") or "friend").strip()[:32]


def _solution_share_url(settings: Settings, sid: int) -> str:
    return share.telegram_share_url(share.solution_link(settings.bot_username, sid, settings.share_secret),
                                    texts.SHARE_TEXT)


def _invite_share_url(settings: Settings, uid: int) -> str:
    return share.telegram_share_url(share.invite_link(settings.bot_username, uid), texts.INVITE_SHARE_TEXT)


# ---------------------------------------------------------------- start, onboarding, profile
@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, **deps):
    repo: Repo = deps["repo"]
    limits: Limits = deps["limits"]
    settings: Settings = deps["settings"]
    uid = message.from_user.id
    payload = (command.args or "").strip()
    is_new = await repo.get_user(uid) is None
    user = await _ensure_user(repo, message, payload[:32] or None)
    await repo.event(uid, "start", source=payload or None, new=is_new)

    inviter = share.parse_invite(payload)
    if inviter and is_new and await repo.set_referrer(uid, inviter):
        await repo.event(uid, "referred", by=inviter)

    shared_sid = share.parse_solution(payload, settings.share_secret)
    if shared_sid:
        await _open_shared(message, deps, shared_sid)

    if not user.get("onboarded"):
        return await message.answer(texts.ONBOARD_HELLO.format(name=texts.escape(_name(user))),
                                    reply_markup=kb.grade_kb("o"))
    if not shared_sid:
        st = await limits.status(uid)
        await message.answer(texts.WELCOME_BACK.format(
            name=texts.escape(_name(user)), streak=texts.streak_line(user.get("streak") or 0),
            quota=texts.quota(st)), reply_markup=kb.examples_kb())


@router.callback_query(F.data.regexp(r"^(grade|lang|prof):"))
async def on_profile_button(call: CallbackQuery, **deps):
    repo: Repo = deps["repo"]
    limits: Limits = deps["limits"]
    uid = call.from_user.id
    user = await _ensure_user(repo, call)
    parts = call.data.split(":")
    await call.answer()
    if parts[0] == "prof":
        if parts[1] == "grade":
            return await call.message.answer(texts.CHOOSE_GRADE, reply_markup=kb.grade_kb("p"))
        return await call.message.answer(texts.CHOOSE_LANG, reply_markup=kb.lang_kb("p"))

    code, mode = parts[1], parts[2] if len(parts) > 2 else "p"
    if parts[0] == "grade" and code in texts.GRADE_LABEL:
        await repo.set_user_flag(uid, "grade", code)
        await repo.event(uid, "set_grade", grade=code)
        if mode == "o":
            return await call.message.edit_text(texts.ONBOARD_LANG, reply_markup=kb.lang_kb("o"))
    elif parts[0] == "lang" and code in texts.LANG_LABEL:
        await repo.set_user_flag(uid, "explain_lang", code)
        await repo.event(uid, "set_lang", lang=code)
        if mode == "o":
            await repo.set_user_flag(uid, "onboarded", 1)
            st = await limits.status(uid)
            return await call.message.edit_text(texts.ONBOARD_DONE.format(
                name=texts.escape(_name(user)), grade=texts.GRADE_LABEL.get(user.get("grade") or "", "Any class"),
                lang=texts.LANG_LABEL[code], solves=texts.amount(st["solves_limit"]),
                tutor=texts.amount(st["tutor_limit"])),
                reply_markup=kb.examples_kb())
    else:
        return
    user = await repo.get_user(uid)
    await call.message.edit_text(texts.SAVED.format(
        grade=texts.GRADE_LABEL.get(user.get("grade") or "", "any class"),
        lang=texts.LANG_LABEL.get(user.get("explain_lang") or "en", "English")))


@router.message(Command("me", "profile"))
async def cmd_me(message: Message, repo: Repo, limits: Limits, settings: Settings):
    user = await _ensure_user(repo, message)
    st = await limits.status(message.from_user.id)
    refs = await repo.referral_count(message.from_user.id)
    await message.answer(texts.profile(user, st, refs),
                         reply_markup=kb.profile_kb(_invite_share_url(settings, message.from_user.id)))


@router.message(Command("invite"))
async def cmd_invite(message: Message, repo: Repo, settings: Settings):
    await _ensure_user(repo, message)
    link = share.invite_link(settings.bot_username, message.from_user.id)
    await repo.event(message.from_user.id, "invite_opened")
    await message.answer(texts.invite(link, settings.limits.get("referral") or {}),
                         reply_markup=kb.invite_kb(_invite_share_url(settings, message.from_user.id)),
                         disable_web_page_preview=True)


@router.message(Command("lang", "class"))
async def cmd_lang(message: Message, command: CommandObject, repo: Repo):
    await _ensure_user(repo, message)
    if command.command == "class":
        return await message.answer(texts.CHOOSE_GRADE, reply_markup=kb.grade_kb("p"))
    await message.answer(texts.CHOOSE_LANG, reply_markup=kb.lang_kb("p"))


# ---------------------------------------------------------------- other commands
@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(texts.HELP)


@router.message(Command("privacy"))
async def cmd_privacy(message: Message):
    await message.answer(texts.PRIVACY, disable_web_page_preview=True)


@router.message(Command("usage"))
async def cmd_usage(message: Message, repo: Repo, limits: Limits):
    await _ensure_user(repo, message)
    await message.answer(texts.usage(await limits.status(message.from_user.id)))


@router.message(Command("tutor"))
async def cmd_tutor(message: Message, repo: Repo):
    user = await _ensure_user(repo, message)
    on = 0 if user["tutor_mode"] else 1
    await repo.set_user_flag(message.from_user.id, "tutor_mode", on)
    await message.answer(texts.TUTOR_ON if on else texts.TUTOR_OFF)


@router.message(Command("deleteme"))
async def cmd_deleteme(message: Message):
    await message.answer(texts.DELETE_CONFIRM, reply_markup=kb.delete_kb())


@router.message(Command("feedback"))
async def cmd_feedback(message: Message, command: CommandObject, repo: Repo, bot: Bot, settings: Settings):
    if not command.args:
        return await message.answer(texts.FEEDBACK_HOW)
    await repo.event(message.from_user.id, "feedback", text=command.args[:1000])
    if settings.admin_chat_id:
        await bot.send_message(settings.admin_chat_id,
                               f"💬 Feedback from {message.from_user.id}:\n{command.args[:1000]}", parse_mode=None)
    await message.answer(texts.FEEDBACK_THANKS)


@router.message(Command("solve"))
async def cmd_solve(message: Message, command: CommandObject, **deps):
    if not command.args:
        return await message.answer("Type the question after /solve, e.g. <code>/solve 2x + 3 = 11</code>")
    await _solve_flow(message, deps, text=command.args)


# ---------------------------------------------------------------- photos & text
def _best_photo(message: Message):
    """Smallest Telegram size that is still >= 1280 px (less to download), else the largest."""
    sizes = sorted(message.photo, key=lambda p: p.width * p.height)
    for p in sizes:
        if max(p.width, p.height) >= 1280:
            return p
    return sizes[-1]


@router.message(F.photo)
async def on_photo(message: Message, **deps):
    buf = io.BytesIO()
    await deps["bot"].download(_best_photo(message), destination=buf)
    await _solve_flow(message, deps, image=buf.getvalue())


@router.message(F.document & F.document.mime_type.startswith("image/"))
async def on_image_document(message: Message, **deps):
    if (message.document.file_size or 0) > 10 * 1024 * 1024:
        return await message.answer("That image is too big (max 10 MB) 🙂")
    buf = io.BytesIO()
    await deps["bot"].download(message.document, destination=buf)
    await _solve_flow(message, deps, image=buf.getvalue())


@router.message(F.text & ~F.text.startswith("/"))
async def on_text(message: Message, **deps):
    uid, text = message.from_user.id, message.text.strip()
    if uid in _fix:                     # corrected question after "✏️ Fix question": free
        _fix.pop(uid)
        return await _solve_flow(message, deps, text=text, free=True)
    ctx = _last.get(uid)
    if ctx and time.time() - ctx[1] < CONTEXT_TTL and (_QUESTION_START.match(text) or not _MATHY.search(text)):
        return await _tutor_flow(message, deps, ctx[0], "ask", text=text)
    if not _MATHY.search(text) and len(text) < 40:
        return await message.answer(texts.NOT_MATH)
    await _solve_flow(message, deps, text=text)


# ---------------------------------------------------------------- the solve flow
async def _solve_flow(message: Message, deps: dict, *, text: str | None = None, image: bytes | None = None,
                      free: bool = False):
    repo: Repo = deps["repo"]
    limits: Limits = deps["limits"]
    pipeline: Pipeline = deps["pipeline"]
    bot: Bot = deps["bot"]
    uid = message.from_user.id
    user = await _ensure_user(repo, message)
    lang = user.get("explain_lang") or "en"
    if user["is_banned"]:
        return await message.answer(texts.BANNED)
    if not limits.begin(uid):
        return await message.answer(texts.ONE_AT_A_TIME)
    reservation = None
    try:
        if text and not free:
            row = await repo.find_solution(cache_key(text, lang))
            if row:                     # already solved before: free, even at the daily limit
                placeholder = await message.answer(texts.SOLVING)
                return await _finish_solve(placeholder, Pipeline._from_row(row), uid, False, deps)
        if not free:
            reservation, why = await limits.reserve(uid, "solves")
            if reservation is None:
                st = await limits.status(uid)
                msg = texts.CAPACITY.format(reset=texts.fmt_duration(st["reset_in_s"])) if why == "capacity" \
                    else texts.BANNED if why == "banned" else texts.limit_reached("solves", st)
                await repo.event(uid, "limit_hit" if why == "limit" else "capacity_hit")
                return await message.answer(msg)

        await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        placeholder = await message.answer(texts.READING if image else texts.SOLVING)
        shown = {"stage": "start"}

        async def progress(stage: str, info: str = "") -> None:
            if stage == shown["stage"]:
                return
            shown["stage"] = stage
            try:
                if stage == "instant":                       # exact answer first, explanation follows
                    await placeholder.edit_text(texts.INSTANT.format(answer=texts.escape(texts.pretty_math(info))))
                    return
                line = {"read": f"📸 I read: {texts.pretty_math(info)}\n\n{texts.SOLVING}", "solve": None,
                        "queue": texts.QUEUE, "double_check": texts.DOUBLE_CHECK}.get(stage)
                if line:
                    await placeholder.edit_text(line, parse_mode=None)
            except TelegramBadRequest:
                pass

        await repo.event(uid, "solve_requested", kind="photo" if image else "text")
        try:
            if image:
                out = await pipeline.solve_photo(image, progress, grade=user.get("grade"), lang=lang)
            else:
                out = await pipeline.solve_text(text, progress, grade=user.get("grade"), lang=lang)
        except Exception:
            log.exception("solve failed")
            await placeholder.edit_text(texts.ERROR)
            return

        counted = out.status == "solved" and not out.from_cache and not free
        if reservation:
            await limits.finish(reservation, counted)
            reservation = None
        await _finish_solve(placeholder, out, uid, bool(image), deps)
    finally:
        if reservation:
            await limits.finish(reservation, False)
        limits.end(uid)


async def _finish_solve(target: Message, out: Outcome, uid: int, from_photo: bool, deps: dict):
    """Streaks, totals and referral rewards for a solved problem, then show the answer."""
    repo: Repo = deps["repo"]
    settings: Settings = deps["settings"]
    extra = ""
    stats = None
    if out.status == "solved":
        now = datetime.now(timezone.utc)
        stats = await repo.record_solve(uid, settings.user_day(now), settings.user_day(now - timedelta(days=1)))
        extra = texts.milestone(stats["streak"], stats["total_solves"], stats["new_day"])
        if stats["first_solve"]:
            extra += await _reward_referral(uid, deps)
    await _show_outcome(target, out, uid, from_photo, deps, streak=(stats or {}).get("streak", 0), extra=extra)


async def _reward_referral(uid: int, deps: dict) -> str:
    """When an invited friend solves their first problem, both get bonus solves for the day."""
    repo: Repo = deps["repo"]
    settings: Settings = deps["settings"]
    inviter = await repo.claim_referral(uid)
    if not inviter:
        return ""
    cfg = settings.limits.get("referral") or {}
    day = settings.user_day()
    friend_bonus, inviter_bonus = int(cfg.get("friend_bonus_solves", 2)), int(cfg.get("inviter_bonus_solves", 3))
    await repo.grant(uid, day, friend_bonus)
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds")
    if await repo.count_events(inviter, "ref_reward", since) < int(cfg.get("max_rewards_per_day", 5)):
        await repo.grant(inviter, day, inviter_bonus)
        await repo.event(inviter, "ref_reward", friend=uid)
        try:
            await deps["bot"].send_message(
                inviter, f"🎉 A friend you invited just solved their first problem!\n"
                         f"🎁 You got <b>+{inviter_bonus} free solves</b> today. Thanks for sharing MathFix 💙")
        except TelegramAPIError:
            pass                        # inviter blocked the bot; the bonus still applies
    return f"\n\n🎁 <b>Welcome gift:</b> +{friend_bonus} extra solves today, because a friend invited you!"


async def _show_outcome(target: Message, out: Outcome, uid: int, from_photo: bool, deps: dict, *,
                        streak: int = 0, extra: str = ""):
    repo: Repo = deps["repo"]
    limits: Limits = deps["limits"]
    settings: Settings = deps["settings"]
    simple = {"unreadable": texts.UNREADABLE, "not_math": texts.NOT_MATH, "refused": texts.REFUSED,
              "busy": texts.BUSY}
    if out.status in simple:
        await repo.event(uid, out.status)
        return await target.edit_text(simple[out.status])
    if out.status == "capacity":
        await repo.event(uid, "capacity_hit")
        return await target.edit_text(texts.CAPACITY.format(reset="a few hours"))
    user = await repo.get_user(uid) or {}
    sid = out.solution_id
    _last[uid] = (sid, time.time())
    _step[(uid, sid)] = 1
    if out.other_problems:
        _others[(uid, sid)] = out.other_problems
    tutor_first = bool(user.get("tutor_mode"))
    st = await limits.status(uid)
    await target.edit_text(
        texts.answer(out.solution, out.problem_text, out.verified, from_photo=from_photo, tutor_first=tutor_first,
                     other_problems=out.other_problems, name=_name(user),
                     foot=texts.footer(st, streak or user.get("streak") or 0), extra=extra),
        reply_markup=kb.answer_kb(sid, from_photo=from_photo, tutor_first=tutor_first,
                                  n_others=len(out.other_problems), share_url=_solution_share_url(settings, sid)))
    await repo.event(uid, "cache_hit" if out.from_cache else "solve_done", model=out.model, verified=out.verified,
                     ms=out.latency_ms)


async def _open_shared(message: Message, deps: dict, sid: int):
    """Someone scanned a QR code or tapped a shared link: show that solution (free) and its image."""
    repo: Repo = deps["repo"]
    settings: Settings = deps["settings"]
    uid = message.from_user.id
    row = await repo.get_solution(sid)
    if not row or row["flagged"]:
        return await message.answer(texts.SHARED_NOT_FOUND)
    out = Pipeline._from_row(row)
    _last[uid] = (sid, time.time())
    _step[(uid, sid)] = 1
    await repo.event(uid, "shared_open", solution_id=sid)
    await message.answer(texts.SHARED_INTRO)
    await message.answer(
        texts.answer(out.solution, out.problem_text, out.verified, from_photo=False, tutor_first=False,
                     other_problems=[]),
        reply_markup=kb.answer_kb(sid, from_photo=False, tutor_first=False, n_others=0,
                                  share_url=_solution_share_url(settings, sid)))
    await _deliver_image(message.chat.id, uid, row, deps)


# ---------------------------------------------------------------- tutor
async def _tutor_flow(message: Message, deps: dict, sid: int, action: str, *, text: str = "", step: int = 1):
    repo: Repo = deps["repo"]
    limits: Limits = deps["limits"]
    tutor: Tutor = deps["tutor"]
    uid = message.from_user.id
    row = await repo.get_solution(sid)
    if not row:
        return await message.answer(texts.NO_CONTEXT)
    user = await repo.get_user(uid) or {}
    if not limits.begin(uid):
        return await message.answer(texts.ONE_AT_A_TIME)
    try:
        reservation, why = await limits.reserve(uid, "tutor")
        if reservation is None:
            st = await limits.status(uid)
            return await message.answer(texts.BANNED if why == "banned" else texts.limit_reached("tutor", st))
        await deps["bot"].send_chat_action(message.chat.id, ChatAction.TYPING)
        try:
            reply = await tutor.reply(uid, row, action, text=text, step=step, grade=user.get("grade"),
                                      lang=user.get("explain_lang") or "en")
            await limits.finish(reservation, True)
        except AllModelsBusy:
            await limits.finish(reservation, False)
            return await message.answer(texts.BUSY)
        except Exception:
            log.exception("tutor failed")
            await limits.finish(reservation, False)
            return await message.answer(texts.ERROR)
        _last[uid] = (sid, time.time())
        await repo.event(uid, "tutor_msg", action=action)
        await message.answer(f"🎓 <b>Tutor</b>\n{texts.escape(reply)}")
    finally:
        limits.end(uid)


# ---------------------------------------------------------------- answer buttons
@router.callback_query(F.data.regexp(r"^(img|hint|next|why|whyn|simpler|show|wrong|fix|q|ex|del):"))
async def on_button(call: CallbackQuery, **deps):
    repo: Repo = deps["repo"]
    bot: Bot = deps["bot"]
    action, sid_s, *rest = call.data.split(":")
    sid, arg = int(sid_s), (rest[0] if rest else "")
    uid = call.from_user.id
    msg = call.message

    if action == "img":
        return await _send_image(call, sid, deps)
    if action == "ex":
        await call.answer()
        return await _solve_flow_from_call(call, deps, texts.EXAMPLES[int(arg)])
    if action == "del":
        await call.answer()
        if arg == "yes":
            await repo.delete_user(uid)
            return await msg.edit_text(texts.DELETED)
        return await msg.edit_text("Cancelled 🙂")
    if action == "fix":
        _fix[uid] = sid
        await call.answer()
        return await msg.answer(texts.FIX_PROMPT)
    if action == "wrong":
        await repo.report_wrong(sid)
        refunded = await deps["limits"].refund_wrong(uid)
        await repo.event(uid, "wrong_report", solution_id=sid)
        if deps["settings"].admin_chat_id:
            await bot.send_message(deps["settings"].admin_chat_id, f"⚠️ Wrong-answer report on solution {sid}",
                                   parse_mode=None)
        await call.answer()
        return await msg.answer(texts.WRONG_THANKS.format(refund=texts.REFUND_NOTE if refunded else ""))
    if action == "q":
        others = _others.get((uid, sid)) or []
        await call.answer()
        if int(arg) >= len(others):
            return await msg.answer("Please send the photo again 🙂")
        return await _solve_flow_from_call(call, deps, others[int(arg)])
    if action == "why":
        row = await repo.get_solution(sid)
        n = len(Solution.model_validate_json(row["solution_json"]).steps) if row else 0
        await call.answer()
        if n <= 1:
            return await _tutor_flow_user(call, deps, sid, "why", step=1)
        return await msg.answer("Which step should I explain?", reply_markup=kb.why_kb(sid, n))

    await call.answer()
    key = (uid, sid)
    if action == "whyn":
        return await _tutor_flow_user(call, deps, sid, "why", step=int(arg))
    if action == "next":
        step = _step.get(key, 1)
        _step[key] = step + 1
        return await _tutor_flow_user(call, deps, sid, "next", step=step)
    return await _tutor_flow_user(call, deps, sid, action)   # hint | simpler | show


async def _tutor_flow_user(call: CallbackQuery, deps: dict, sid: int, action: str, step: int = 1):
    # callback messages belong to the bot; build the flow around the user who tapped
    fake = call.message.model_copy(update={"from_user": call.from_user})
    await _tutor_flow(fake, deps, sid, action, step=step)


async def _solve_flow_from_call(call: CallbackQuery, deps: dict, text: str):
    fake = call.message.model_copy(update={"from_user": call.from_user, "text": text})
    await _solve_flow(fake, deps, text=text)


# ---------------------------------------------------------------- solution image
async def _send_image(call: CallbackQuery, sid: int, deps: dict):
    repo: Repo = deps["repo"]
    limits: Limits = deps["limits"]
    row = await repo.get_solution(sid)
    if not row:
        return await call.answer("Please solve the question again 🙂", show_alert=True)
    if row["image_file_id"]:
        await call.answer()
        return await _deliver_image(call.message.chat.id, call.from_user.id, row, deps)
    if not limits.begin(call.from_user.id):
        return await call.answer(texts.ONE_AT_A_TIME, show_alert=True)
    try:
        await call.answer(texts.DRAWING)
        await _deliver_image(call.message.chat.id, call.from_user.id, row, deps)
    finally:
        limits.end(call.from_user.id)


async def _deliver_image(chat_id: int, uid: int, row: dict, deps: dict):
    """Rendered once per solution (only when asked for), then Telegram's file_id is reused for everyone."""
    repo: Repo = deps["repo"]
    sandbox: Sandbox = deps["sandbox"]
    settings: Settings = deps["settings"]
    bot: Bot = deps["bot"]
    sid = row["id"]
    sol = Solution.model_validate_json(row["solution_json"])
    caption = texts.image_caption(sol.topic)
    markup = kb.image_kb(_solution_share_url(settings, sid), _invite_share_url(settings, uid))
    if row["image_file_id"]:
        await bot.send_photo(chat_id, row["image_file_id"], caption=caption, reply_markup=markup)
        return await repo.event(uid, "image_cached", solution_id=sid)
    await bot.send_chat_action(chat_id, ChatAction.UPLOAD_PHOTO)
    data = {"problem_text": row["problem_text"], "problem_latex": row["problem_latex"] or "",
            "steps": [s.model_dump() for s in sol.steps], "final_answer": sol.final_answer,
            "final_answer_latex": sol.final_answer_latex, "seed": sid, "topic": sol.topic,
            "difficulty": sol.difficulty, "key_idea": sol.key_idea, "tip": sol.tip, "verified": row["verified"],
            "qr_url": share.solution_link(settings.bot_username, sid, settings.share_secret)}
    try:
        png = await sandbox.run(render_solution, data, timeout=30)
    except SandboxTimeout:
        return await bot.send_message(chat_id, texts.ERROR)
    sent = await bot.send_photo(chat_id, BufferedInputFile(png, f"mathfix-{sid}.png"), caption=caption,
                                reply_markup=markup)
    await repo.set_image_file_id(sid, sent.photo[-1].file_id)
    await repo.event(uid, "image_rendered", solution_id=sid)
