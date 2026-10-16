"""Every user-facing message in one place (HTML parse mode)."""
from __future__ import annotations

from html import escape

from ..mathcheck.text import latex_to_text
from ..schemas import Solution

WELCOME = (
    "👋 <b>Welcome to MathFix AI!</b>\n\n"
    "📸 Send me a <b>photo</b> of a maths question, or just <b>type</b> it.\n"
    "✅ I'll give you the answer, checked by a maths engine\n"
    "📝 step-by-step explanation\n"
    "✍️ a handwritten-style image (tap 🖼 under the answer)\n"
    "💬 and a tutor for hints and \"why?\"\n\n"
    "Free beta: <b>{solves} solves + {tutor} tutor messages every day</b>.\n\n"
    "Tip: photograph only the question, with no names or faces. We don't keep your photos. /privacy\n\n"
    "Try one 👇"
)
EXAMPLES = ["2x + 5 = 17", "x^2 - 5x + 6 = 0", "15% of 240"]

HELP = (
    "<b>How to get the best results</b>\n"
    "• One question per photo, in good light, phone held flat\n"
    "• Or type it: <code>3x - 7 = 11</code>, <code>x^2 - 4 = 0</code>, <code>d/dx x^3 sin x</code>\n"
    "• Use ^ for powers and / for fractions when typing\n\n"
    "<b>Commands</b>\n"
    "/usage: free solves left today\n"
    "/tutor: tutor-first mode (hints before answers)\n"
    "/feedback &lt;text&gt;: tell us what to improve\n"
    "/privacy · /deleteme"
)

PRIVACY = (
    "🔒 <b>Privacy in short</b>\n"
    "• Photos are processed and then discarded. We never store them\n"
    "• We keep your Telegram id/name, daily usage counts, and the maths problems (not linked to you)\n"
    "• Tutor chats are deleted after 7 days\n"
    "• No ads, no tracking, no selling of data\n"
    "• The maths problem is sent to our AI providers to read and explain it\n"
    "• /deleteme deletes your data\n\n"
    "Full policy: https://mathfix.ai/privacy"
)

READING = "🔍 Reading your question…"
SOLVING = "🧮 Solving…"
QUEUE = "⏳ Busy right now, you're in line. One moment…"
DOUBLE_CHECK = "🔁 Double-checking the answer…"
UNREADABLE = ("I couldn't read that clearly 😅\nTry: good light, phone held flat, one question per photo.\n"
              "<i>(This didn't use a free solve.)</i>")
NOT_MATH = "I only do maths 🙂 Send me a maths question as a photo or text.\n<i>(This didn't use a free solve.)</i>"
REFUSED = "I can only help with maths problems 🙂"
BUSY = "MathFix is very busy right now 🙏 Please try again in a minute.\n<i>(This didn't use a free solve.)</i>"
CAPACITY = "MathFix is at full capacity today 🙏 Free solves come back in <b>{reset}</b>."
ERROR = "Something went wrong on our side 😓 Please try again.\n<i>(This didn't use a free solve.)</i>"
ONE_AT_A_TIME = "One at a time please 🙂 I'm still working on your last question."
BANNED = "Your access to MathFix has been paused. Contact support@mathfix.ai if you think this is a mistake."
FIX_PROMPT = "✏️ Type the question exactly as it should be, and I'll solve that instead (free)."
NO_CONTEXT = "Send me a maths question first, then I can help with hints 🙂"
DRAWING = "✍️ Drawing your solution…"
IMAGE_CAPTION = "✍️ Your solution, handwritten style. Share it with friends! @mathfixbot"
WRONG_THANKS = "Thanks for telling us! 🙏 We'll review this answer.{refund}"
REFUND_NOTE = " Your free solve was given back."
TUTOR_ON = "🎓 Tutor-first mode is <b>ON</b>: I'll give hints first and the answer only when you ask."
TUTOR_OFF = "Tutor-first mode is <b>OFF</b>: you'll get full solutions straight away."
DELETE_CONFIRM = "This deletes all your MathFix data (usage, tutor chats, history). Are you sure?"
DELETED = "✅ Your data has been deleted. Send /start any time to come back."
FEEDBACK_THANKS = "Thank you! 💙 Your feedback was sent to the team."
FEEDBACK_HOW = "Write your feedback after the command, e.g. <code>/feedback the photo reading is great</code>"
LANG = "English only during the beta. More languages are coming soon!"


def fmt_duration(seconds: int) -> str:
    h, m = divmod(max(0, seconds) // 60, 60)
    return f"{h} h {m} m" if h else f"{m} m"


def usage(st: dict) -> str:
    return (
        "📊 <b>Today's free MathFix</b>\n"
        f"🧮 Solves: {st['solves_left']} of {st['solves_limit']} left\n"
        f"💬 Tutor: {st['tutor_left']} of {st['tutor_limit']} left\n"
        f"⏰ Resets in {fmt_duration(st['reset_in_s'])}\n"
        "Tip: questions solved before are free!"
    )


def limit_reached(kind: str, st: dict) -> str:
    reset = fmt_duration(st["reset_in_s"])
    if kind == "tutor":
        return f"That's all your tutor messages for today, great effort! 💪\nYour tutor is back in {reset}."
    return (f"You've used all {st['solves_limit']} free solves for today 🎉 That's a lot of maths!\n"
            f"⏰ More in {reset}.\n💬 You can still use the tutor on your last answers "
            f"({st['tutor_left']} messages left).")


VERIFY_LINE = {
    "verified": "✔️ <i>Checked by our maths engine.</i>",
    "agreed": "✔️ <i>Two independent methods agree.</i>",
    "unchecked": "ℹ️ <i>I couldn't check this one automatically, so double-check it.</i>",
    "failed": "⚠️ <i>This answer did not pass our automatic check. Please double-check it.</i>",
}


def answer(sol: Solution, problem: str, verified: str, *, from_photo: bool, tutor_first: bool,
           other_problems: list[str]) -> str:
    parts = []
    if from_photo:
        parts.append(f"📸 <b>I read:</b> {escape(problem)}")
    else:
        parts.append(f"❓ {escape(problem)}")
    if tutor_first:
        parts.append("\n🎓 Let's work it out together! Tap <b>💡 Hint</b> to start, or <b>👀 Show answer</b>.")
    else:
        parts.append(f"\n✅ <b>Answer:</b> {escape(sol.final_answer or latex_to_text(sol.final_answer_latex))}")
        if sol.steps:
            parts.append("\n📝 <b>Steps</b>")
            for i, s in enumerate(sol.steps, 1):
                line = f"{i}. {escape(s.say)}"
                if s.math:
                    line += f"\n    <code>{escape(latex_to_text(s.math))}</code>"
                parts.append(line)
        parts.append("\n" + VERIFY_LINE.get(verified, VERIFY_LINE["unchecked"]))
    if other_problems:
        parts.append(f"\n🧾 I also found {len(other_problems)} more question(s) in your photo; tap below to solve them.")
    text = "\n".join(parts)
    return text if len(text) < 4000 else text[:3990] + "…"
