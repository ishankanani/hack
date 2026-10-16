# 01 · Product spec

## What MathFix AI is
A maths helper for students. Send a **photo** or **type** a maths question and get back:
1. **The correct answer**, verified by a maths engine (SymPy) whenever possible
2. **Step-by-step explanation** in simple language
3. **Handwritten-style solution image** that looks like a neat notebook page and is easy to copy or share
4. **Interactive tutoring**: ask "why?", get hints, go step by step, try a similar problem

**Who it's for:** school and early-college students (arithmetic → algebra → geometry → trigonometry → calculus →
statistics), plus parents helping with homework.

**Positioning:** "Understand it, don't just copy it." The tutor mode and the explanations are the product, and the
answer is the hook.

---

## Launch scope (this weekend, Telegram)

| Must have (launch blocker) | Nice to have (only if time allows Sunday) | Later (after launch) |
|---|---|---|
| Photo → answer + steps | Streaming "I read: …" preview while solving | Practice similar problems |
| Typed question → answer + steps | Multi-problem photo picker (buttons) | Referral bonus solves |
| Handwritten-style image | "Explain simpler" button | Group chat support |
| SymPy answer verification | Multiple explanation languages via `/lang` | Inline mode (`@mathfixbot 2x+3=7`) |
| Tutor mode (Hint / Next step / Why?) | | Graph plotting |
| Daily limits + `/usage` | | PDF export, history |
| Global capacity guard | | Web app, Android, iOS ([09](09-roadmap-apps.md)) |
| Admin stats + alerts | | Pro plan |
| Privacy policy on `mathfix.ai` | | |

---

## User flows

### A. Photo solve (main flow)
```
Student sends photo
  → bot instantly shows "typing…" and a draft/placeholder: "🔍 Reading your question…"
  → (2–6 s) placeholder becomes: "🧮 Solving…"
  → Answer message (text):   I read · Answer · Steps · buttons
  → Student taps [🖼 Handwritten image] → image arrives in ~0.5 s (drawn once, then reused for everyone)
```

### B. Typed question
Same as A, but without the reading step. Plain arithmetic or a simple equation (e.g. `2x+5=17`, `15% of 240`) is
answered by SymPy first, so the answer is almost instant and the AI only writes the explanation.

### C. Tutor mode
- Every answer has buttons: **💡 Hint**, **➡️ Next step**, **❓ Why?**, **🧒 Explain simpler**, **⚠️ Wrong answer?**
- `/tutor` turns on **tutor-first mode**. The bot gives *hints and guiding questions first*, and the full solution only on
  request. This is good for learning and good for capacity, because hints are short.
- The student can type follow-ups ("why did you divide by 2?") and the tutor answers with that problem as context.

### D. Edge cases (each needs a clear, friendly message)
| Situation | Bot response |
|---|---|
| Blurry / dark / cut-off photo | "I couldn't read that clearly 😅 Try: good light, hold the phone flat, one question per photo." Doesn't count toward the limit. |
| Not maths (selfie, essay, meme) | "I only do maths 🙂 Send me a maths question as a photo or text." Doesn't count. |
| Several questions in one photo | "I found 3 questions. Which one?" with buttons [Q1] [Q2] [Q3]. Solving the chosen one uses the text already read, so no new photo read is needed. |
| Answer couldn't be machine-checked | Answer shown with "ℹ️ Double-check this one, I couldn't verify it automatically." |
| Daily limit reached | See [05-daily-limits.md](05-daily-limits.md#user-facing-messages) |
| Free capacity exhausted for the day | "MathFix is at full capacity today 🙏 Free solves come back at 00:00 (in 5h 12m)." |
| AI providers all down | "Our maths brain is taking a short break. Try again in a minute." Request refunded. |

---

## Bot commands

| Command | What it does |
|---|---|
| `/start` | Welcome, how to use, 3 example problems as buttons (deep-link payload tracked for marketing) |
| `/solve <question>` | Solve typed question (plain text without the command also works) |
| `/tutor` | Toggle tutor-first mode on/off |
| `/usage` | "Today: 3/5 solves, 12/15 tutor messages left · resets in 5h 12m" |
| `/lang` | Explanation language (launch: English; add more as tested) |
| `/help` | Tips for good photos, what topics work, examples |
| `/feedback <text>` | Sends feedback to the admin chat |
| `/privacy` | Short privacy summary + link to `mathfix.ai/privacy` |
| `/deleteme` | Deletes all of the user's data (asks for confirmation first) |

Admin-only commands are listed in [05-daily-limits.md](05-daily-limits.md#admin-controls) and
[07-deployment-and-ops.md](07-deployment-and-ops.md#monitoring--alerts).

---

## Message format

Telegram **cannot render LaTeX**, so the text message uses Unicode maths (x², √, ÷, π, ≤). The handwritten image
shows proper typeset maths.

```
📸 I read: Solve 2x² − 8x + 6 = 0                  [✏️ Fix question]

✅ Answer: x = 1 or x = 3

📝 Steps
1. Divide everything by 2  →  x² − 4x + 3 = 0
2. Find two numbers that multiply to 3 and add to −4: −1 and −3
3. Factorise  →  (x − 1)(x − 3) = 0
4. Set each bracket to 0  →  x = 1 or x = 3

✔️ Checked: both answers make the equation true.

[🖼 Handwritten image]
[💡 Hint] [➡️ Next step] [❓ Why?]
[🧒 Explain simpler] [⚠️ Wrong answer?]
```
Tapping 🖼 sends the **handwritten-style image** of the same solution, with a small `mathfix.ai` footer. Every shared image
is free marketing.

**Rules**
- Max 12 steps. Longer solutions are grouped into stages.
- One idea per step: a short sentence plus one line of maths.
- Always show what was read ("I read: …") so the student can spot a misread immediately. **✏️ Fix question**
  lets them type the corrected version, and it doesn't count as a new solve.

---

## Languages
Launch in English. Explanations are generated by the model, so other languages are a prompt setting. The
`language_code` that Telegram sends is used as a *suggestion* in `/lang`. Add each language only after testing ~20
problems in it.

---

## Launch-week success metrics
| Metric | Target |
|---|---|
| Correct final answers (golden test set) | ≥ 90 % text, ≥ 85 % photos |
| "⚠️ Wrong answer" reports | < 5 % of solves |
| p50 response time | text < 5 s, photo < 8 s |
| Day-1 retention (comes back next day) | > 25 % |
| Users hitting the daily limit | 5–15 % (lower means limits are too generous for capacity, higher means users are frustrated) |
| Capacity-exhausted minutes per day | 0 before 20:00 local time |
