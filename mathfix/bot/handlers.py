"""Telegram handlers for students. Dependencies (repo, limits, pipeline, …) are injected by aiogram
from the Dispatcher's workflow data (see main.py)."""
from __future__ import annotations

import io
import logging
import re
import time

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from ..ai.router import AllModelsBusy
from ..core.limits import Limits
from ..core.pipeline import Outcome, Pipeline
from ..core.tutor import Tutor
from ..db import Repo
from ..mathcheck.sandbox import Sandbox, SandboxTimeout
from ..mathcheck.text import problem_key
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


# ---------------------------------------------------------------- commands
@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, repo: Repo, limits: Limits):
    await _ensure_user(repo, message, (command.args or "")[:32] or None)
    await repo.event(message.from_user.id, "start", source=command.args)
    st = await limits.status(message.from_user.id)
    await message.answer(texts.WELCOME.format(solves=st["solves_limit"], tutor=st["tutor_limit"]),
                         reply_markup=kb.examples_kb())


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(texts.HELP)


@router.message(Command("privacy"))
async def cmd_privacy(message: Message):
    await message.answer(texts.PRIVACY, disable_web_page_preview=True)


@router.message(Command("lang"))
async def cmd_lang(message: Message):
    await message.answer(texts.LANG)


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
async def cmd_feedback(message: Message, command: CommandObject, repo: Repo, bot: Bot, settings):
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
    if user["is_banned"]:
        return await message.answer(texts.BANNED)
    if not limits.begin(uid):
        return await message.answer(texts.ONE_AT_A_TIME)
    reservation = None
    try:
        if text and not free:
            row = await repo.find_solution(problem_key(text))
            if row:                     # already solved before: free, even at the daily limit
                placeholder = await message.answer(texts.SOLVING)
                return await _show_outcome(placeholder, Pipeline._from_row(row), uid, False, user, repo)
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
            line = {"read": f"📸 I read: {info}\n\n{texts.SOLVING}", "solve": None, "queue": texts.QUEUE,
                    "double_check": texts.DOUBLE_CHECK}.get(stage)
            if line:
                try:
                    await placeholder.edit_text(line, parse_mode=None)
                except TelegramBadRequest:
                    pass

        await repo.event(uid, "solve_requested", kind="photo" if image else "text")
        try:
            if image:
                out = await pipeline.solve_photo(image, progress=progress)
            else:
                out = await pipeline.solve_text(text, progress=progress)
        except Exception:
            log.exception("solve failed")
            await placeholder.edit_text(texts.ERROR)
            return

        counted = out.status == "solved" and not out.from_cache and not free
        if reservation:
            await limits.finish(reservation, counted)
            reservation = None
        await _show_outcome(placeholder, out, uid, bool(image), user, repo)
    finally:
        if reservation:
            await limits.finish(reservation, False)
        limits.end(uid)


async def _show_outcome(target: Message, out: Outcome, uid: int, from_photo: bool, user: dict, repo: Repo):
    simple = {"unreadable": texts.UNREADABLE, "not_math": texts.NOT_MATH, "refused": texts.REFUSED,
              "busy": texts.BUSY}
    if out.status in simple:
        await repo.event(uid, out.status)
        return await target.edit_text(simple[out.status])
    if out.status == "capacity":
        await repo.event(uid, "capacity_hit")
        return await target.edit_text(texts.CAPACITY.format(reset="a few hours"))
    sid = out.solution_id
    _last[uid] = (sid, time.time())
    _step[(uid, sid)] = 1
    if out.other_problems:
        _others[(uid, sid)] = out.other_problems
    tutor_first = bool(user.get("tutor_mode"))
    await target.edit_text(
        texts.answer(out.solution, out.problem_text, out.verified, from_photo=from_photo, tutor_first=tutor_first,
                     other_problems=out.other_problems),
        reply_markup=kb.answer_kb(sid, from_photo=from_photo, tutor_first=tutor_first,
                                  n_others=len(out.other_problems)))
    await repo.event(uid, "cache_hit" if out.from_cache else "solve_done", model=out.model, verified=out.verified,
                     ms=out.latency_ms)


# ---------------------------------------------------------------- tutor
async def _tutor_flow(message: Message, deps: dict, sid: int, action: str, *, text: str = "", step: int = 1):
    repo: Repo = deps["repo"]
    limits: Limits = deps["limits"]
    tutor: Tutor = deps["tutor"]
    uid = message.from_user.id
    row = await repo.get_solution(sid)
    if not row:
        return await message.answer(texts.NO_CONTEXT)
    if not limits.begin(uid):
        return await message.answer(texts.ONE_AT_A_TIME)
    try:
        reservation, why = await limits.reserve(uid, "tutor")
        if reservation is None:
            st = await limits.status(uid)
            return await message.answer(texts.BANNED if why == "banned" else texts.limit_reached("tutor", st))
        await deps["bot"].send_chat_action(message.chat.id, ChatAction.TYPING)
        try:
            reply = await tutor.reply(uid, row, action, text=text, step=step)
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
        await message.answer(f"🎓 {reply}", parse_mode=None)
    finally:
        limits.end(uid)


# ---------------------------------------------------------------- buttons
@router.callback_query(F.data.regexp(r"^(img|hint|next|why|whyn|simpler|show|wrong|fix|q|ex|del):"))
async def on_button(call: CallbackQuery, **deps):
    repo: Repo = deps["repo"]
    bot: Bot = deps["bot"]
    action, sid_s, *rest = call.data.split(":")
    sid, arg = int(sid_s), (rest[0] if rest else "")
    uid = call.from_user.id
    msg = call.message

    if action == "img":
        return await _send_image(call, sid, bot, deps)
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


async def _send_image(call: CallbackQuery, sid: int, bot: Bot, deps: dict):
    """Rendered only on request (keeps answers fast); the Telegram file_id is reused afterwards."""
    repo: Repo = deps["repo"]
    sandbox: Sandbox = deps["sandbox"]
    limits: Limits = deps["limits"]
    row = await repo.get_solution(sid)
    if not row:
        return await call.answer("Please solve the question again 🙂", show_alert=True)
    if row["image_file_id"]:
        await call.answer()
        await bot.send_photo(call.message.chat.id, row["image_file_id"], caption=texts.IMAGE_CAPTION)
        return await repo.event(call.from_user.id, "image_cached", solution_id=sid)
    if not limits.begin(call.from_user.id):
        return await call.answer(texts.ONE_AT_A_TIME, show_alert=True)
    try:
        await call.answer(texts.DRAWING)
        await bot.send_chat_action(call.message.chat.id, ChatAction.UPLOAD_PHOTO)
        sol = Solution.model_validate_json(row["solution_json"])
        data = {"problem_text": row["problem_text"], "problem_latex": row["problem_latex"] or "",
                "steps": [s.model_dump() for s in sol.steps], "final_answer": sol.final_answer,
                "final_answer_latex": sol.final_answer_latex, "seed": sid}
        try:
            png = await sandbox.run(render_solution, data, timeout=10)
        except SandboxTimeout:
            return await call.message.answer(texts.ERROR)
        sent = await bot.send_photo(call.message.chat.id, BufferedInputFile(png, f"mathfix-{sid}.png"),
                                    caption=texts.IMAGE_CAPTION)
        await repo.set_image_file_id(sid, sent.photo[-1].file_id)
        await repo.event(call.from_user.id, "image_rendered", solution_id=sid)
    finally:
        limits.end(call.from_user.id)
