"""Inline keyboards. Callback data format: "<action>:<id>[:<arg>]" (max 64 bytes)."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton as B
from aiogram.types import InlineKeyboardMarkup

from .texts import EXAMPLES, GRADES, LANGS


def answer_kb(sid: int, *, from_photo: bool, tutor_first: bool, n_others: int,
              share_url: str = "") -> InlineKeyboardMarkup:
    rows = [[B(text="🖼 Get solution image", callback_data=f"img:{sid}")]]
    if tutor_first:
        rows.append([B(text="💡 Hint", callback_data=f"hint:{sid}"),
                     B(text="➡️ Next step", callback_data=f"next:{sid}"),
                     B(text="👀 Show answer", callback_data=f"show:{sid}")])
    else:
        rows.append([B(text="💡 Hint", callback_data=f"hint:{sid}"),
                     B(text="➡️ Next step", callback_data=f"next:{sid}"),
                     B(text="❓ Why?", callback_data=f"why:{sid}")])
        rows.append([B(text="🧒 Explain simpler", callback_data=f"simpler:{sid}"),
                     B(text="⚠️ Wrong answer?", callback_data=f"wrong:{sid}")])
    if share_url:
        rows.append([B(text="📤 Share with a friend", url=share_url)])
    if from_photo:
        rows.append([B(text="✏️ Fix question", callback_data=f"fix:{sid}")])
    if n_others:
        rows.append([B(text=f"Solve Q{i + 2}", callback_data=f"q:{sid}:{i}") for i in range(min(n_others, 4))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def image_kb(share_url: str, invite_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [B(text="📤 Share this solution", url=share_url)],
        [B(text="🤝 Invite friends · get free solves", url=invite_url)],
    ])


def why_kb(sid: int, n_steps: int) -> InlineKeyboardMarkup:
    nums = [B(text=f"Step {i}", callback_data=f"whyn:{sid}:{i}") for i in range(1, min(n_steps, 12) + 1)]
    return InlineKeyboardMarkup(inline_keyboard=[nums[i:i + 4] for i in range(0, len(nums), 4)])


def examples_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[B(text=f"✏️ {e}", callback_data=f"ex:0:{i}")]
                                                 for i, e in enumerate(EXAMPLES)])


def grade_kb(mode: str) -> InlineKeyboardMarkup:
    """mode: 'o' = onboarding (then ask language), 'p' = changing from profile."""
    btns = [B(text=label, callback_data=f"grade:{code}:{mode}") for code, label in GRADES]
    return InlineKeyboardMarkup(inline_keyboard=[btns[0:2], btns[2:4], btns[4:]])


def lang_kb(mode: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[B(text=f"🗣 {label}", callback_data=f"lang:{code}:{mode}")
                                                  for code, label in LANGS]])


def profile_kb(invite_share_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [B(text="🎓 Change class", callback_data="prof:grade"), B(text="🗣 Change language", callback_data="prof:lang")],
        [B(text="🤝 Invite friends", url=invite_share_url)],
    ])


def invite_kb(invite_share_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[B(text="📤 Send my invite link", url=invite_share_url)]])


def delete_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[B(text="Yes, delete my data", callback_data="del:0:yes"),
                                                  B(text="Cancel", callback_data="del:0:no")]])
