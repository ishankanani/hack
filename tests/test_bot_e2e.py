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


async def send(dp, bot, text):
    msg = Message(message_id=next(_uid), date=NOW, chat=CHAT, from_user=USER, text=text)
    await dp.feed_update(bot, Update(update_id=next(_uid), message=msg))


async def tap(dp, bot, data, message_text="answer"):
    msg = Message(message_id=next(_uid), date=NOW, chat=CHAT, text=message_text)
    call = CallbackQuery(id=str(next(_uid)), from_user=USER, chat_instance="c", message=msg, data=data)
    await dp.feed_update(bot, Update(update_id=next(_uid), callback_query=call))


SOL = {"topic": "algebra", "steps": [{"say": "Subtract 3 from both sides", "math": "2x=8"},
                                     {"say": "Divide by 2", "math": "x=4"}],
       "final_answer": "x = 4", "final_answer_latex": "x=4", "check": {"type": "none"}, "confidence": 0.9}


async def test_start_solve_image_button_tutor_and_usage(env):
    dp, bot, tg, ai, repo = env
    await send(dp, bot, "/start")
    assert "Welcome to MathFix AI" in tg.texts()[-1] and "5 solves + 15 tutor" in tg.texts()[-1]

    ai.add("openai/gpt-oss-120b", SOL)
    await send(dp, bot, "2x + 3 = 11")
    answer = [m for m in tg.sent if isinstance(m, EditMessageText)][-1]
    assert "✅ <b>Answer:</b> x = 4" in answer.text and "Checked by our maths engine" in answer.text
    buttons = [b.callback_data for row in answer.reply_markup.inline_keyboard for b in row]
    assert buttons[0].startswith("img:")
    assert not any(isinstance(m, SendPhoto) for m in tg.sent)          # image NOT rendered by default
    sid = buttons[0].split(":")[1]

    await tap(dp, bot, f"img:{sid}")                                     # rendered on demand
    photos = [m for m in tg.sent if isinstance(m, SendPhoto)]
    assert len(photos) == 1 and photos[0].photo.data[:4] == b"\x89PNG"
    await tap(dp, bot, f"img:{sid}")                                     # second tap reuses file_id
    photos = [m for m in tg.sent if isinstance(m, SendPhoto)]
    assert len(photos) == 2 and isinstance(photos[1].photo, str)

    ai.add("openai/gpt-oss-20b", "Think: what undoes +3?")
    await tap(dp, bot, f"hint:{sid}")
    assert tg.texts()[-1] == "🎓 Think: what undoes +3?"
    ai.add("openai/gpt-oss-20b", "Because division undoes the 2 times x.")
    await send(dp, bot, "why divide by 2?")                              # free-text follow-up -> tutor
    assert "division" in tg.texts()[-1]

    await send(dp, bot, "/usage")
    assert "4 of 5 left" in tg.texts()[-1] and "13 of 15 left" in tg.texts()[-1]


async def test_daily_limit_message_and_cache_hits_are_free(env, settings):
    dp, bot, tg, ai, repo = env
    settings.limits["burst"]["max_per_minute"] = 100
    ai.add("openai/gpt-oss-120b", *[SOL] * 6)
    for i in range(5):
        await send(dp, bot, f"x + {i} = 10")
    await send(dp, bot, "x + 0 = 10")             # solved before: served from cache even at the limit
    assert "✅ <b>Answer:</b>" in tg.texts()[-1]
    await send(dp, bot, "x + 99 = 1")
    assert "used all 5 free solves" in tg.texts()[-1]


async def test_burst_limit(env):
    dp, bot, tg, ai, repo = env
    ai.add("openai/gpt-oss-120b", *[SOL] * 6)
    for i in range(6):
        await send(dp, bot, f"x + {i} = 20")
    assert "One at a time" in tg.texts()[-1]      # 6th request inside one minute


async def test_wrong_report_refunds_and_fix_question_is_free(env):
    dp, bot, tg, ai, repo = env
    ai.add("openai/gpt-oss-120b", SOL, SOL)
    await send(dp, bot, "2x+3=11")
    sid = (await repo.find_solution(__import__("mathfix.mathcheck.text", fromlist=["x"]).problem_key("2x+3=11")))["id"]
    await tap(dp, bot, f"wrong:{sid}")
    assert "free solve was given back" in tg.texts()[-1]
    await tap(dp, bot, f"fix:{sid}")
    await send(dp, bot, "2x+3=13")
    await send(dp, bot, "/usage")
    assert "5 of 5 left" in tg.texts()[-1]


async def test_admin_commands_only_for_admins(env, settings):
    dp, bot, tg, ai, repo = env
    await send(dp, bot, "/setlimit solves 9")                             # user 1 is not an admin
    assert await repo.get_setting("limit_solves") is None
    admin_user = User(id=999, is_bot=False, first_name="Admin")
    msg = Message(message_id=next(_uid), date=NOW, chat=Chat(id=999, type="private"), from_user=admin_user,
                  text="/setlimit solves 9")
    await dp.feed_update(bot, Update(update_id=next(_uid), message=msg))
    assert await repo.get_setting("limit_solves") == "9"
    msg = msg.model_copy(update={"text": "/stats", "message_id": next(_uid)})
    await dp.feed_update(bot, Update(update_id=next(_uid), message=msg))
    assert "solve pool used" in tg.texts()[-1]


async def test_burst_and_non_maths_text(env):
    dp, bot, tg, ai, repo = env
    await send(dp, bot, "hello there")
    assert "I only do maths" in tg.texts()[-1]
