"""Every user-facing message in one place (HTML parse mode)."""
from __future__ import annotations

from html import escape

from ..core.limits import UNLIMITED
from ..mathcheck.text import pretty_math, pretty_text
from ..schemas import Solution

EXAMPLES = ["2x + 5 = 17", "x^2 - 5x + 6 = 0", "15% of 240"]
GRADES = [("6-8", "Class 6–8"), ("9-10", "Class 9–10"), ("11-12", "Class 11–12"),
          ("college", "College"), ("parent", "Parent / Teacher")]
LANGS = [("en", "English"), ("hinglish", "Hinglish")]
GRADE_LABEL = dict(GRADES)
LANG_LABEL = dict(LANGS)
KEYCAPS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
RULE = "━━━━━━━━━━━━━━━"

# ---------------------------------------------------------------- onboarding & profile
ONBOARD_HELLO = (
    "👋 Hi <b>{name}</b>, welcome to <b>MathFix.ai</b>!\n\n"
    "📸 Snap or ✏️ type any maths question and I'll give you:\n"
    "✅ the answer, checked by a maths engine\n"
    "📝 clear step-by-step explanation\n"
    "✍️ a beautiful solution image to save and share\n"
    "🎓 a tutor for hints and \"why?\"\n\n"
    "<b>Quick setup</b> (2 taps) so I explain at your level.\n\n"
    "🎓 <b>Which class are you in?</b>"
)
ONBOARD_LANG = "Nice! 🗣 <b>Which language should I explain in?</b>"
ONBOARD_DONE = (
    "🎉 You're all set, <b>{name}</b>!\n\n"
    "🎓 {grade}  ·  🗣 {lang}\n"
    "🎁 Free every day: <b>{solves} solves</b> + <b>{tutor} tutor messages</b>\n\n"
    "📸 Send a photo of a maths question, or type it.\n"
    "Try one now 👇"
)
WELCOME_BACK = (
    "👋 Welcome back, <b>{name}</b>!{streak}\n"
    "🧮 {quota}\n\n"
    "📸 Send a photo or ✏️ type a question 👇"
)
SAVED = "✅ Saved! I'll explain for <b>{grade}</b> in <b>{lang}</b>."
CHOOSE_GRADE = "🎓 <b>Which class are you in?</b>"
CHOOSE_LANG = "🗣 <b>Which language should I explain in?</b>"

HELP = (
    "💡 <b>How to get the best results</b>\n"
    "• One question per photo, good light, phone held flat\n"
    "• Or type it: <code>3x - 7 = 11</code>, <code>x^2 - 4 = 0</code>, <code>d/dx x^3 sin x</code>\n"
    "• Use ^ for powers and / for fractions\n\n"
    "⚙️ <b>Commands</b>\n"
    "/me: your profile, streak and free solves\n"
    "/invite: invite friends and get extra solves\n"
    "/lang: change class or language\n"
    "/tutor: hints first, answer later\n"
    "/feedback &lt;text&gt;: tell us what to improve\n"
    "/privacy · /deleteme"
)

PRIVACY = (
    "🔒 <b>Privacy in short</b>\n"
    "• Photos are processed and then discarded. We never store them\n"
    "• We keep your Telegram id and first name, your class and language choice, usage counts and "
    "your streak, and the maths problems (not linked to you)\n"
    "• Tutor chats are deleted after 7 days\n"
    "• No ads, no tracking, no selling of data\n"
    "• The maths problem is sent to our AI providers to read and explain it\n"
    "• /deleteme deletes your data\n\n"
    "Full policy: https://mathfix.ai/privacy"
)

# ---------------------------------------------------------------- statuses
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
WRONG_THANKS = "Thanks for telling us! 🙏 We'll review this answer.{refund}"
REFUND_NOTE = " Your free solve was given back."
TUTOR_ON = "🎓 Tutor-first mode is <b>ON</b>: I'll give hints first and the answer only when you ask."
TUTOR_OFF = "Tutor-first mode is <b>OFF</b>: you'll get full solutions straight away."
DELETE_CONFIRM = "This deletes all your MathFix data (profile, usage, tutor chats). Are you sure?"
DELETED = "✅ Your data has been deleted. Send /start any time to come back."
FEEDBACK_THANKS = "Thank you! 💙 Your feedback was sent to the team."
FEEDBACK_HOW = "Write your feedback after the command, e.g. <code>/feedback the photo reading is great</code>"
SHARED_INTRO = "📬 <b>Someone shared this MathFix solution with you!</b>"
SHARED_NOT_FOUND = "This shared solution isn't available any more 🙂 Send me your own question instead!"
SHARE_TEXT = "I solved this maths problem with MathFix ✨ Free step-by-step answers on Telegram:"
INVITE_SHARE_TEXT = "Try MathFix: snap any maths question, get step-by-step answers free 📸✨"

VERIFY_LINE = {
    "verified": "✔️ <i>Verified by our maths engine</i>",
    "agreed": "✔️ <i>Double-checked by two independent methods</i>",
    "unchecked": "ℹ️ <i>Not auto-checked: our maths engine can't verify this kind of problem yet</i>",
    "failed": "⚠️ <i>This answer did not pass our automatic check. Please double-check it</i>",
}


def fmt_duration(seconds: int) -> str:
    h, m = divmod(max(0, seconds) // 60, 60)
    return f"{h} h {m} m" if h else f"{m} m"


def topic_label(topic: str) -> str:
    t = (topic or "").replace("_", " ").strip()
    return "" if t.lower() in ("", "general", "refused") else t[:1].upper() + t[1:]


def streak_line(streak: int) -> str:
    return f"\n🔥 <b>{streak}-day streak!</b>" if streak >= 2 else ""


def amount(n: int) -> str:
    """Limits for admins are a huge number internally; show them as 'unlimited'."""
    return "unlimited" if n >= UNLIMITED else str(n)


def left_of(left: int, limit: int) -> str:
    return "<b>unlimited</b>" if limit >= UNLIMITED else f"<b>{left}</b> of {limit}"


def quota(st: dict) -> str:
    """'3 of 5 free solves left today', for the welcome message."""
    if st["solves_limit"] >= UNLIMITED:
        return "<b>Unlimited</b> solves (admin)."
    return f"<b>{st['solves_left']}</b> of {st['solves_limit']} free solves left today."


def usage(st: dict) -> str:
    plan = "⭐ Premium" if st.get("plan") == "premium" else "Free plan"
    return (
        f"📊 <b>Today</b> · {plan}\n"
        f"🧮 Solves: {left_of(st['solves_left'], st['solves_limit'])} left\n"
        f"💬 Tutor: {left_of(st['tutor_left'], st['tutor_limit'])} left\n"
        f"⏰ Resets in {fmt_duration(st['reset_in_s'])}\n"
        "💡 Questions solved before are free · /invite friends for extra solves"
    )


def profile(user: dict, st: dict, referrals: int) -> str:
    name = escape(user.get("first_name") or "friend")
    badge = "⭐ Premium" if (user.get("plan") == "premium") else "Free"
    return (
        f"👤 <b>{name}</b> · {badge}\n"
        f"🎓 {GRADE_LABEL.get(user.get('grade') or '', 'Class not set')}  ·  "
        f"🗣 {LANG_LABEL.get(user.get('explain_lang') or 'en', 'English')}\n\n"
        f"🔥 Streak: <b>{user.get('streak') or 0}</b> days (best {user.get('best_streak') or 0})\n"
        f"✅ Problems solved: <b>{user.get('total_solves') or 0}</b>\n"
        f"🤝 Friends invited: <b>{referrals}</b>\n\n" + usage(st)
    )


def invite(link: str, cfg: dict) -> str:
    return (
        "🤝 <b>Invite friends, get more free solves!</b>\n\n"
        "When a friend joins with your link and solves their first problem:\n"
        f"🎁 you get <b>+{cfg.get('inviter_bonus_solves', 3)} solves</b> that day\n"
        f"🎁 they get <b>+{cfg.get('friend_bonus_solves', 2)} solves</b>\n\n"
        f"Your personal link:\n{link}"
    )


def limit_reached(kind: str, st: dict) -> str:
    reset = fmt_duration(st["reset_in_s"])
    if kind == "tutor":
        return f"That's all your tutor messages for today, great effort! 💪\nYour tutor is back in {reset}."
    return (f"🎉 You've used all {st['solves_limit']} free solves today. That's a lot of maths!\n\n"
            f"⏰ More in <b>{reset}</b>\n"
            f"🤝 Want more today? /invite a friend: you both get extra solves\n"
            f"💬 You can still use the tutor on your last answers ({st['tutor_left']} left)")


def footer(st: dict, streak: int) -> str:
    bits = []
    if streak >= 2:
        bits.append(f"🔥 {streak}-day streak")
    if st["solves_limit"] >= UNLIMITED:
        bits.append("♾️ Unlimited solves (admin)")
    else:
        bits.append(f"🧮 {st['solves_left']}/{st['solves_limit']} free solves left today")
    return " · ".join(bits)


def milestone(streak: int, total: int, new_day: bool) -> str:
    if new_day and streak in (3, 7, 14, 30, 50, 100):
        return f"\n\n🏆 <b>{streak}-day streak!</b> You're on fire, keep it going!"
    if total in (10, 25, 50, 100, 250, 500):
        return f"\n\n🏅 <b>{total} problems solved!</b> Amazing work!"
    return ""


def _step_number(i: int) -> str:
    return KEYCAPS[i - 1] if i <= len(KEYCAPS) else f"<b>{i}.</b>"


def answer(sol: Solution, problem: str, verified: str, *, from_photo: bool, tutor_first: bool,
           other_problems: list[str], name: str = "", foot: str = "", extra: str = "") -> str:
    """Telegram allows 4096 characters. Never cut HTML in half: show fewer steps instead."""
    max_steps = len(sol.steps)
    while True:
        text = _answer(sol, problem, verified, from_photo=from_photo, tutor_first=tutor_first,
                       other_problems=other_problems, name=name, foot=foot, extra=extra, max_steps=max_steps)
        if len(text) <= 4000 or max_steps == 0:
            return text if len(text) <= 4000 else escape(pretty_math(problem)[:300]) + "\n\n" + VERIFY_LINE.get(verified, "")
        max_steps -= 1


SHORT_ANSWER = 48      # longer answers get their own block instead of the bold headline
MAX_ANSWER = 600       # the full working is in the steps


def answer_text(sol: Solution) -> str:
    """The final answer as clean Unicode, one statement per line."""
    final = pretty_math(sol.final_answer) or pretty_math(sol.final_answer_latex)
    if len(final) > SHORT_ANSWER:
        final = "\n".join(p.strip() for p in final.replace("; ", "\n").splitlines() if p.strip())
    if len(final) > MAX_ANSWER:
        final = final[:MAX_ANSWER].rsplit(" ", 1)[0] + " … (see the steps)"
    return final


def _answer(sol: Solution, problem: str, verified: str, *, from_photo: bool, tutor_first: bool,
            other_problems: list[str], name: str, foot: str, extra: str, max_steps: int) -> str:
    topic = topic_label(sol.topic)
    head = "✨ <b>MathFix</b>" + (f" · <i>{escape(topic)}</i>" if topic else "")
    question = pretty_math(problem) or problem
    q_tag = "blockquote expandable" if len(question) > 280 else "blockquote"
    parts = [head, "",
             f"{'📸' if from_photo else '✏️'} <b>{'I read' if from_photo else 'Your question'}</b>",
             f"<{q_tag}>{escape(question)}</blockquote>"]
    if tutor_first:
        who = f", {escape(name)}" if name else ""
        parts.append(f"\n🎓 Let's work it out together{who}! Tap <b>💡 Hint</b> to start, or <b>👀 Show answer</b>.")
    else:
        final = answer_text(sol) or "see the steps below"
        if len(final) <= SHORT_ANSWER and "\n" not in final:
            parts += ["", f"✅ <b>ANSWER:  {escape(final)}</b>"]
        else:
            body = "\n".join(f"<b>{escape(ln)}</b>" if len(final) <= 240 else escape(ln) for ln in final.splitlines())
            parts += ["", "✅ <b>ANSWER</b>", f"<blockquote>{body}</blockquote>"]
        if sol.key_idea:
            parts += ["", f"💡 <b>Key idea:</b> {escape(pretty_text(sol.key_idea))}"]
        if sol.steps:
            lines = []
            for i, s in enumerate(sol.steps[:max_steps], 1):
                line = f"{_step_number(i)} {escape(pretty_text(s.say))}"
                if s.math:
                    line += f"\n      <code>{escape(pretty_math(s.math))}</code>"
                lines.append(line)
            if max_steps < len(sol.steps):
                lines.append(f"… {len(sol.steps) - max_steps} more step(s) in the 🖼 solution image")
            tag = "blockquote expandable" if len(sol.steps) > 3 else "blockquote"
            parts += ["", "📝 <b>Step-by-step</b>" + (" <i>(tap to expand)</i>" if len(sol.steps) > 3 else ""),
                      f"<{tag}>" + "\n\n".join(lines) + "</blockquote>"]
        if sol.tip:
            parts += [f"⚠️ <b>Watch out:</b> {escape(pretty_text(sol.tip))}"]
        parts += ["", VERIFY_LINE.get(verified, VERIFY_LINE["unchecked"])]
    if other_problems:
        parts.append(f"\n🧾 I also found {len(other_problems)} more question(s) in your photo. Tap below to solve them.")
    if foot:
        parts += [RULE, foot]
    return "\n".join(parts) + extra


def image_caption(topic: str) -> str:
    t = topic_label(topic)
    return (f"✍️ <b>{escape(t) + ' · ' if t else ''}Solved with MathFix.ai</b>\n"
            "📲 Save it, or tap <b>Share</b> to send it to a friend. Anyone can scan the QR to open it.")
