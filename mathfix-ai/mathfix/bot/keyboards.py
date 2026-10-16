"""Inline keyboards. Callback data format: "<action>:<solution_id>[:<arg>]" (max 64 bytes)."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton as B
from aiogram.types import InlineKeyboardMarkup

from .texts import EXAMPLES


def answer_kb(sid: int, *, from_photo: bool, tutor_first: bool, n_others: int) -> InlineKeyboardMarkup:
    rows = [[B(text="🖼 Handwritten image", callback_data=f"img:{sid}")]]
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
    if from_photo:
        rows.append([B(text="✏️ Fix question", callback_data=f"fix:{sid}")])
    if n_others:
        rows.append([B(text=f"Solve Q{i + 2}", callback_data=f"q:{sid}:{i}") for i in range(min(n_others, 4))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def why_kb(sid: int, n_steps: int) -> InlineKeyboardMarkup:
    nums = [B(text=f"Step {i}", callback_data=f"whyn:{sid}:{i}") for i in range(1, min(n_steps, 12) + 1)]
    return InlineKeyboardMarkup(inline_keyboard=[nums[i:i + 4] for i in range(0, len(nums), 4)])


def examples_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[B(text=e, callback_data=f"ex:0:{i}")] for i, e in enumerate(EXAMPLES)])


def delete_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[B(text="Yes, delete my data", callback_data="del:0:yes"),
                                                  B(text="Cancel", callback_data="del:0:no")]])
