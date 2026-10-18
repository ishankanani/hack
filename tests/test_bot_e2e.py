"""End-to-end: real aiogram Dispatcher + handlers, fake Telegram API, fake AI providers."""
from datetime import datetime, timezone

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.methods import (AnswerCallbackQuery, EditMessageText, SendChatAction, SendMessage, SendPhoto)
from aiogram.types import CallbackQuery, Chat, Message, PhotoSize, Update, User

from mathfix.ai.router import Router
from mathfix.bot import admin, handlers
from mathfix.core.limits import Limits
from mathfix.core.pipeline import Pipeline
from mathfix.core.tutor import Tutor

from .conftest import FakeAI, InlineSandbox

USER = User(id=1, is_bot=False, first_name="Asha", username="asha", language_code="en")
FRIEND = User(id=2, is_bot=False, first_name="Ravi", username="ravi", language_code="en")
CHAT = Chat(id=1, type="private")
NOW = datetime.now(timezone.utc)


class FakeTelegram(BaseSession):
    def __init__(self):
        super().__init__()
        self.sent: list = []
        self._id = 100

    async def make_request(self, bot, method, timeout=None):
        self.sent.append(method)
        self._id += 1
        if isinstance(method, (SendChatAction, AnswerCallbackQuery)):
            return True
        if isinstance(method, SendPhoto):
            return Message(message_id=self._id, date=NOW, chat=CHAT, caption=method.caption,
                           photo=[PhotoSize(file_id=f"file{self._id}", file_unique_id="u", width=1080, height=1400)]
                           ).as_(bot)
        if isinstance(method, (SendMessage, EditMessageText)):
            return Message(message_id=self._id, date=NOW, chat=CHAT, text=method.text,
                           reply_markup=method.reply_markup).as_(bot)
        raise AssertionError(f"unexpected method {type(method).__name__}")

    async def stream_content(self, *a, **k):
        yield b""

    async def close(self):
        pass

    def texts(self):
        return [m.text for m in self.sent if isinstance(m, (SendMessage, EditMessageText))]


@pytest.fixture
async def env(settings, repo):
    fake_ai = FakeAI()
    ai = Router(settings.models, repo, transport=fake_ai.transport)
    limits = Limits(settings, repo, ai)
    sandbox = InlineSandbox()
    deps = dict(settings=settings, repo=repo, sandbox=sandbox, ai=ai, limits=limits,
                pipeline=Pipeline(ai, repo, sandbox), tutor=Tutor(ai, repo))
    tg = FakeTelegram()
    bot = Bot("42:TEST", session=tg, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(**deps)
    dp.include_router(admin.setup(settings.admin_user_ids))
    dp.include_router(handlers.router)
    yield dp, bot, tg, fake_ai, repo
    handlers._last.clear(); handlers._fix.clear(); handlers._others.clear(); handlers._step.clear()
    for r in (handlers.router, admin.router):     # module-level routers: detach for the next test
        r._parent_router = None


_uid = iter(range(1, 10**6))


async def send(dp, bot, text, user=USER):
    msg = Message(message_id=next(_uid), date=NOW, chat=Chat(id=user.id, type="private"), from_user=user, text=text)
    await dp.feed_update(bot, Update(update_id=next(_uid), message=msg))


async def tap(dp, bot, data, user=USER, message_text="answer"):
    msg = Message(message_id=next(_uid), date=NOW, chat=Chat(id=user.id, type="private"), text=message_text)
    call = CallbackQuery(id=str(next(_uid)), from_user=user, chat_instance="c", message=msg, data=data)
    await dp.feed_update(bot, Update(update_id=next(_uid), callback_query=call))


def buttons(method):
    rows = method.reply_markup.inline_keyboard if method.reply_markup else []
    return [b for row in rows for b in row]


def last_answer(tg):
    return [m for m in tg.sent if isinstance(m, EditMessageText)][-1]


SOL = {"topic": "Linear equations",
       "steps": [{"say": "Subtract 3 from both sides", "math": "2x=8"},
                 {"say": "Divide both sides by 2", "math": "x=4"}],
       "final_answer": "x = 4", "final_answer_latex": "x=4", "check": {"type": "none"}, "confidence": 0.9,
       "key_idea": "Undo operations in reverse order.", "tip": "Do the same thing to both sides."}


async def onboard(dp, bot, user=USER, grade="9-10", lang="en"):
    await send(dp, bot, "/start", user)
    await tap(dp, bot, f"grade:{grade}:o", user)
    await tap(dp, bot, f"lang:{lang}:o", user)


async def test_onboarding_asks_class_and_language(env):
    dp, bot, tg, ai, repo = env
    await send(dp, bot, "/start")
    assert "welcome to <b>MathFix.ai</b>" in tg.texts()[-1] and "Which class" in tg.texts()[-1]
    assert [b.callback_data for b in buttons(tg.sent[-1])][1] == "grade:9-10:o"
    await tap(dp, bot, "grade:9-10:o")
    assert "Which language" in tg.texts()[-1]
    await tap(dp, bot, "lang:hinglish:o")
    done = tg.texts()[-1]
    assert "You're all set" in done and "Class 9–10" in done and "Hinglish" in done and "5 solves" in done
    u = await repo.get_user(1)
    assert u["grade"] == "9-10" and u["explain_lang"] == "hinglish" and u["onboarded"] == 1
    await send(dp, bot, "/start")
    assert "Welcome back" in tg.texts()[-1]


async def test_personalised_solve_answer_layout_image_and_tutor(env):
    dp, bot, tg, ai, repo = env
    await onboard(dp, bot, lang="hinglish")
    ai.add("openai/gpt-oss-120b", SOL)
    await send(dp, bot, "2x + 3 = 11")
    system = ai.calls[0]["messages"][0]["content"]
    assert "Class 9–10" in system and "Hinglish" in system          # explanation tuned to the student
    ans = last_answer(tg)
    assert "✅ <b>ANSWER:  x = 4</b>" in ans.text and "💡 <b>Key idea:</b>" in ans.text
    assert "1️⃣ Subtract 3" in ans.text and "⚠️ <b>Watch out:</b>" in ans.text
    assert "Verified by our maths engine" in ans.text and "4/5 free solves left today" in ans.text
    btns = buttons(ans)
    assert btns[0].callback_data.startswith("img:")
    share_btn = [b for b in btns if b.url][0]
    assert share_btn.url.startswith("https://t.me/share/url?url=https%3A%2F%2Ft.me%2Fmathfixbot%3Fstart%3Ds_")
    sid = btns[0].callback_data.split(":")[1]
    assert not any(isinstance(m, SendPhoto) for m in tg.sent)          # image only on request

    await tap(dp, bot, f"img:{sid}")
    photos = [m for m in tg.sent if isinstance(m, SendPhoto)]
    assert len(photos) == 1 and photos[0].photo.data[:4] == b"\x89PNG"
    assert "Solved with MathFix.ai" in photos[0].caption and any(b.url for b in buttons(photos[0]))
    await tap(dp, bot, f"img:{sid}")                                     # reused file_id, no re-render
    photos = [m for m in tg.sent if isinstance(m, SendPhoto)]
    assert len(photos) == 2 and isinstance(photos[1].photo, str)

    ai.add("openai/gpt-oss-20b", "Socho: +3 ko kaise hatayenge?")
    await tap(dp, bot, f"hint:{sid}")
    assert "Socho" in tg.texts()[-1]
    assert "Hinglish" in ai.calls[-1]["messages"][0]["content"]

    await send(dp, bot, "/me")
    me = tg.texts()[-1]
    assert "Asha" in me and "Class 9–10" in me and "Problems solved: <b>1</b>" in me and "4</b> of 5" in me


async def test_shared_link_opens_solution_for_anyone_and_rejects_forgery(env, settings):
    from mathfix.core import share
    dp, bot, tg, ai, repo = env
    await onboard(dp, bot)
    ai.add("openai/gpt-oss-120b", SOL)
    await send(dp, bot, "2x + 3 = 11")
    sid = int(buttons(last_answer(tg))[0].callback_data.split(":")[1])
    payload = share.solution_payload(sid, settings.share_secret)
    await send(dp, bot, f"/start {payload}", FRIEND)                    # friend scans the QR code
    texts_sent = tg.texts()
    assert any("shared this MathFix solution" in t for t in texts_sent)
    assert any("ANSWER:  x = 4" in t for t in texts_sent[-3:])
    assert isinstance(tg.sent[-2], SendPhoto) or any(isinstance(m, SendPhoto) for m in tg.sent[-3:])
    assert "Which class" in tg.texts()[-1]                              # new user then gets onboarding
    n = len(tg.sent)
    await send(dp, bot, f"/start s_{sid}_0000000000", FRIEND)           # forged signature: ignored
    assert not any("shared this MathFix solution" in (getattr(m, "text", "") or "") for m in tg.sent[n:])


async def test_invite_rewards_both_after_first_solve(env):
    dp, bot, tg, ai, repo = env
    await onboard(dp, bot)
    await send(dp, bot, "/invite")
    assert "ref_1" in tg.texts()[-1]
    await send(dp, bot, "/start ref_1", FRIEND)
    assert (await repo.get_user(2))["referred_by"] == 1
    await tap(dp, bot, "grade:6-8:o", FRIEND)
    await tap(dp, bot, "lang:en:o", FRIEND)
    ai.add("openai/gpt-oss-120b", SOL)
    await send(dp, bot, "2x + 3 = 11", FRIEND)
    assert "Welcome gift" in last_answer(tg).text
    to_inviter = [m for m in tg.sent if isinstance(m, SendMessage) and m.chat_id == 1 and "friend you invited" in m.text]
    assert to_inviter
    await send(dp, bot, "/usage")
    assert "8</b> of 8 left" in tg.texts()[-1]                          # 5 free + 3 inviter bonus
    await send(dp, bot, "/usage", FRIEND)
    assert "6</b> of 7 left" in tg.texts()[-1]                          # 5 + 2 friend bonus, 1 used
    ai.add("openai/gpt-oss-120b", SOL)
    await send(dp, bot, "3x + 3 = 12", FRIEND)                           # second solve: no second reward
    assert "Welcome gift" not in last_answer(tg).text


async def test_daily_limit_message_and_cache_hits_are_free(env, settings):
    dp, bot, tg, ai, repo = env
    settings.limits["burst"]["max_per_minute"] = 100
    ai.add("openai/gpt-oss-120b", *[SOL] * 6)
    for i in range(5):
        await send(dp, bot, f"x + {i} = 10")
    await send(dp, bot, "x + 0 = 10")             # solved before: served from cache even at the limit
    assert "ANSWER:" in tg.texts()[-1]
    await send(dp, bot, "x + 99 = 1")
    assert "used all 5 free solves" in tg.texts()[-1] and "/invite" in tg.texts()[-1]


async def test_burst_limit(env):
    dp, bot, tg, ai, repo = env
    ai.add("openai/gpt-oss-120b", *[SOL] * 6)
    for i in range(6):
        await send(dp, bot, f"x + {i} = 20")
    assert "One at a time" in tg.texts()[-1]      # 6th request inside one minute


async def test_wrong_report_refunds_and_fix_question_is_free(env):
    from mathfix.core.pipeline import cache_key
    dp, bot, tg, ai, repo = env
    ai.add("openai/gpt-oss-120b", SOL, SOL)
    await send(dp, bot, "2x+3=11")
    sid = (await repo.find_solution(cache_key("2x+3=11")))["id"]
    await tap(dp, bot, f"wrong:{sid}")
    assert "free solve was given back" in tg.texts()[-1]
    await tap(dp, bot, f"fix:{sid}")
    await send(dp, bot, "2x+3=13")
    await send(dp, bot, "/usage")
    assert "5</b> of 5 left" in tg.texts()[-1]


async def test_admin_commands_only_for_admins(env, settings):
    dp, bot, tg, ai, repo = env
    await send(dp, bot, "/start")
    await send(dp, bot, "/setlimit solves 9")                             # user 1 is not an admin
    assert await repo.get_setting("limit_solves") is None
    admin_user = User(id=999, is_bot=False, first_name="Admin")
    await send(dp, bot, "/setlimit solves 9", admin_user)
    assert await repo.get_setting("limit_solves") == "9"
    await send(dp, bot, "/setplan 1 premium", admin_user)
    assert (await repo.get_user(1))["plan"] == "premium"
    await send(dp, bot, "/usage")
    assert "Premium" in tg.texts()[-1] and "of 50 left" in tg.texts()[-1]
    await send(dp, bot, "/stats", admin_user)
    assert "solve pool used" in tg.texts()[-1] and "shared opens" in tg.texts()[-1]
    await send(dp, bot, "/quota", admin_user)
    q = tg.texts()[-1]
    assert "API cost: $0" in q and "groq_oss_120b (Groq)" in q and "Left today, about:" in q
    seen = len(tg.texts())
    await send(dp, bot, "/quota")                                         # not for normal users
    assert not any("API cost" in t for t in tg.texts()[seen:])


async def test_non_maths_text(env):
    dp, bot, tg, ai, repo = env
    await send(dp, bot, "hello there")
    assert "I only do maths" in tg.texts()[-1]
