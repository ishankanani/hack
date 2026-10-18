# MathFix AI: Launch Plan & Documentation

> **The Plan A bot is built.** Code is in [`mathfix/`](mathfix/), with 77 tests. To run it, see
> [Run the bot](#run-the-bot). Changes after review are under [Decisions after review](#decisions-after-review).

> Snap or type any maths problem and get the correct answer, step-by-step explanation,
> a handwritten-style solution image, and a patient AI tutor.

| | |
|---|---|
| **Bot** | [@mathfixbot](https://t.me/mathfixbot) (Telegram) |
| **Domain** | `mathfix.ai` (landing page, privacy, terms) · `bot.mathfix.ai` (webhook) |
| **Status** | Planning v0.1, written Fri 16 Oct 2026 |
| **Launch** | Telegram this weekend (Sat 17 – Sun 18 Oct 2026). Web/Android/iOS apps come after |
| **Price to users** | Free, with a daily limit per user |
| **AI API budget** | **$0** (free tiers only; see the decision below) |

---

## ⚠️ Decision needed tonight: who is MathFix for?

The provider with the **biggest free tier (Google Gemini API)** doesn't allow this use. Google's Gemini API
Additional Terms (version effective 18 Dec 2025) say you **may not use the API in an app "directed towards or likely to be
accessed by individuals under the age of 18"**. That applies to the free and paid tiers. A maths homework bot for students
is clearly likely to be used by under-18s.

| Plan | AI stack | AI cost | Free capacity (est.) | Under-18 users? |
|---|---|---|---|---|
| **A: launch default** ✅ | Open models on **Groq** + **Cloudflare Workers AI** (+ OpenRouter overflow) | **$0** | ~200 solves/day (~1,000 with a one-time $10 OpenRouter top-up) | No clause against it found in Groq's terms; **read Groq's and Cloudflare's terms yourself tonight** |
| **B** | Google **Gemini** free tier | $0 | ~1,000 solves/day | ❌ **Only if MathFix is 18+ only** (university students, adult learners, parents) |
| **C: best product** | **Claude Haiku 5.5** for photo reading + solving, plus Groq free for tutor | ~**$0.001 per solve** (≈ $27/month at 1,000 solves/day) | not capped by free quotas | ✅ Anthropic explicitly allows products for minors **with safeguards** |

**Recommendation:** launch on **Plan A** at $0 with conservative limits. Keep **Plan C** wired into the config
(it's just a config change) and switch to it once demand outgrows the free pool. Don't use Plan B unless you
deliberately make MathFix adults-only. Details are in [docs/03-ai-models.md](docs/03-ai-models.md#the-three-plans).

---

## TL;DR: the decisions (Plan A)

### 1. Which AI does what (every step)

Only **3 kinds of step use AI** (reading photos, solving/explaining, tutoring). Everything else is plain code, which is
free, instant and exact.

| # | Step | Who does it | Fallback chain |
|---|------|-------------|----------------|
| 1 | Receive photo/text, shrink image, hash it | Code (Pillow, imagehash) | – |
| 2 | Look up answer cache | Code (SQLite) | – |
| 3 | Instant answer for plain arithmetic / simple equations | Code (**SymPy**) | → step 5 |
| 4 | **Read the photo** (handwriting → maths text) | **Cloudflare Workers AI · Llama 4 Scout** (vision) | OpenRouter `:free` vision model |
| 5 | **Solve step by step** | **Groq · `openai/gpt-oss-120b`** (fast, strong at maths) | Groq's free Qwen model → Cloudflare `gpt-oss-120b` → OpenRouter `:free` |
| 6 | Check the answer is correct | Code (**SymPy** verification) | – |
| 7 | Second opinion, *only* if the check fails or the problem is hard | **Groq · Qwen** (different model family) | Groq `gpt-oss-120b` (high reasoning) |
| 8 | Telegram-friendly text (LaTeX → x², √, π) | Code | – |
| 9 | **Handwritten-style solution image**, only when the student taps 🖼 | Code (**Pillow + matplotlib + free handwriting font**), *not* an image AI | plain-text fallback |
| 10 | **Tutor chat** (hints, "why?", next step) | **Groq · `openai/gpt-oss-20b`** (very fast) | Cloudflare small model → OpenRouter `:free` |

Model IDs, settings, prompts and the JSON format are in [docs/03-ai-models.md](docs/03-ai-models.md).

### 2. How it stays at $0
- **Handwriting images are drawn by code**, so no image-generation AI is needed. That's free, it takes about 0.3 s, and the maths stays exact.
- **SymPy checks answers and solves simple ones itself.** That's free and exact, and it means fewer AI calls.
- **Answer cache**: a repeated question (same photo or same text) costs nothing.
- **Each provider and model has its own free bucket**, and the router spreads work across them.
- A **global capacity guard** means we never get billed and never crash. When the free pool runs out, users get a friendly "back tomorrow" message.

### 3. How it stays fast (targets: text ≈ 2–4 s, photo ≈ 4–7 s, cached < 0.5 s)
Groq (one of the fastest AI APIs) for solving and tutoring · always-on server with a webhook (no cold starts) · instant
"typing…"/draft feedback · images shrunk before upload · cache · SymPy instant path · handwritten image drawn **only
when the student taps 🖼** (and reused after the first time) · per-provider rate limiters so we skip a provider
*before* it returns 429.
See [docs/04-speed-and-cost.md](docs/04-speed-and-cost.md).

### 4. Daily limit per user (launch values for Plan A, changeable live without redeploy)
| Allowance | Per user per day |
|---|---|
| Solves (photo **or** text) | **5** (raise to 10+ when capacity grows: Plan A + $10, or Plan C) |
| Tutor messages | **15** |
| Cached answers, failed attempts, answers reported wrong | **don't count** |
| Burst protection | 1 request at a time, max 5 per minute |
| Reset | 00:00 in one configured timezone |

See [docs/05-daily-limits.md](docs/05-daily-limits.md).

### 5. The weekend
**Fri night**: decide the plan, read the providers' terms, get keys and real quotas, set up the server and DNS.
**Sat**: build the solve pipeline, verification, handwriting renderer and limits.
**Sun**: tutor mode, admin tools, landing page and privacy policy, beta test with 20–50 people, then public launch at about 18:00.
See [docs/06-weekend-launch-plan.md](docs/06-weekend-launch-plan.md).

---

## Read before launch: the honest constraints

1. **Free capacity is small.** Plan A at $0 serves roughly **200 solves/day**, so think of launch weekend as a
   **public beta for ~50–80 daily users**. A one-time $10 OpenRouter credit purchase lifts it to ~1,000/day, and Plan C
   removes the ceiling for about $1/day. Fill in the [capacity worksheet](docs/04-speed-and-cost.md#capacity-worksheet)
   with your own console numbers on Friday night.
2. **Free limits and free model lists change without notice.** Google cut Gemini free quotas in Dec 2025, Groq reportedly
   dropped Llama from new free accounts in 2026, and OpenRouter's free models rotate. That's why every model name lives in a
   config file, and why every step has a fallback chain.
3. **Students are minors.** Beyond provider terms, collect the minimum data, store no photos, show no ads and do no
   tracking. Read [docs/08-privacy-and-safety.md](docs/08-privacy-and-safety.md). This is a plan, not legal advice: get a
   lawyer's eye on the privacy policy before the app-store phase.
4. **Never create extra accounts to multiply free limits.** Limits are per account or organisation, and doing this breaks
   the terms of service. It can get every key banned at once.

---

## Run the bot

```bash
git clone https://github.com/ishankanani/hack.git && cd hack
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env              # fill in TELEGRAM_BOT_TOKEN, GROQ_API_KEY, CF_ACCOUNT_ID, CF_AI_API_TOKEN, ADMIN_USER_IDS
.venv/bin/python -m pytest -q     # 164 tests, no keys needed
.venv/bin/python -m scripts.smoke_test   # checks every free model with YOUR keys (uses a little quota)
.venv/bin/python -m scripts.eval_golden  # accuracy and speed on 40 real problems (school to machine learning)
.venv/bin/python -m mathfix.main  # MODE=polling: talk to @mathfixbot from your phone right away
```
On the server, set `MODE=webhook` and use [`deploy/mathfix.service`](deploy/mathfix.service) plus the Cloudflare Tunnel
from [docs/07](docs/07-deployment-and-ops.md). Before launch, fill in the two `"<...>"` model ids in
[`config/models.yaml`](config/models.yaml) (the Groq Qwen id and, optionally, OpenRouter free models). Until then
they're simply skipped.

| Folder | What's inside |
|---|---|
| `mathfix/ai/` | `router.py` (fallback chains, retries, cooldowns), `budget.py` (RPM/RPD/TPM/TPD + Cloudflare neurons per model), `prompts.py` |
| `mathfix/core/` | `pipeline.py` (cache → read photo → maths engine (instant exact answer) → solve → verify → second opinion), `limits.py`, `tutor.py` |
| `mathfix/mathcheck/` | SymPy verification, quick answers, safe parsing, process sandbox with timeouts, LaTeX → Unicode |
| `mathfix/render/` | handwritten-style image (Kalam font, SIL Open Font License) |
| `mathfix/bot/` | Telegram handlers, buttons, texts, admin commands |
| `config/` | `models.yaml` (which model does what, and free limits), `limits.yaml` (daily limits, capacity guard) |

## Premium experience (built)

| What | How it works |
|---|---|
| **Onboarding** | `/start` asks 2 quick questions: class (6–8, 9–10, 11–12, college, parent/teacher) and language (English or Hinglish). Every explanation, hint and tutor reply is then pitched at that level |
| **Answer layout** | Topic header → question → **bold answer** (long answers get their own block, one statement per line) → 💡 key idea → numbered steps (collapsible) → ⚠️ common mistake → verified badge → 🔥 streak and free solves left. Telegram can't show LaTeX, so every LaTeX bit is turned into readable maths first: `\frac{1}{n}\|W\|_2^2` → `(1/n)‖W‖₂²`, `X^{T}` → `Xᵀ` |
| **Solution image** | Brand header with logo, maths grid paper, faint logo watermark, numbered step badges, key-idea note, green answer box with a ✓ VERIFIED stamp, and a footer with a **QR code** + logo. Symbols like √ π ≤ ≠ ∞ use a fallback font, so no more boxes |
| **QR & sharing** | The QR (and the 📤 Share button) opens that exact solution in the bot for anyone. Links are signed, so people can't browse other students' solutions. New users who arrive this way get onboarded |
| **Invites** | `/invite` gives a personal link. When a friend solves their first problem, the inviter gets +3 and the friend +2 solves that day |
| **Personal touches** | `/me` profile with streak, best streak, problems solved, friends invited and today's usage. Milestone messages at 3/7/14/30-day streaks and 10/25/50/100 solves |
| **Plans** | Free plan with daily limits for everyone now. `premium` is already wired in for later (`/setplan`, `/setlimit premium solves 50`) |

**Logo & brand:** the official MathFix logo is in [`brand/`](brand/): `logo-mark.png`, `logo-full.png` and
`telegram-profile.png` (upload that one in BotFather with `/setuserpic`). The image renderer uses the transparent copies
in `mathfix/render/assets/` (`logo.png` for the mark, `logo_full.png` for the full logo); replace those files to update
the logo everywhere. Brand colours sampled from the logo: cyan `#01E3FD` → blue `#006EFC` → royal `#003DE3`,
navy `#051744`, slate `#525E77`.

**Changing the image design:** Telegram images are cached (one upload per solution, reused for everyone). After
changing anything in `mathfix/render/`, bump `RENDER_VERSION` in `mathfix/render/handwriting.py`; on the next start
the bot forgets the old images and draws the new design when someone taps 🖼.

## Decisions after review

**1. The handwritten image is made only when the student taps 🖼.** The answer arrives faster, and no CPU is spent
on images nobody opens. The first tap renders it in about 0.3 s. Later taps, by anyone, reuse Telegram's stored copy instantly.

**2. No multiple accounts rotated per request.** Groq, OpenRouter and Google set their free limits **per account or
organisation**, and their terms forbid creating extra accounts to get around those limits. If one account is flagged,
providers typically ban all the linked accounts and keys, and the bot goes down for everyone. The same goal (more free
capacity, used efficiently) is met legitimately:
- **every model has its own free bucket**, and the router spreads requests across all of them (Groq gpt-oss-120b, Qwen
  and gpt-oss-20b; Cloudflare Llama 4 Scout and gpt-oss-120b; OpenRouter free models),
- the router **checks each bucket before calling** (no wasted 429s) and moves to the next model when one is full,
- a **cache**, the **SymPy quick path**, and **one-time image rendering** remove AI calls entirely where possible,
- if that isn't enough, the cheapest real boosts are the one-time $10 OpenRouter top-up, or Plan C at about $0.001 per solve.

**3. Gemini is not used for 18+ users either.** Google's clause is about the **app**: an API client "directed towards or
likely to be accessed by" under-18s. MathFix as a whole is a student app, so routing adults to Gemini inside it doesn't
change that. Age would also be self-declared and easy to fake. If you want Gemini's capacity, the legitimate route is a
**separate adults-only product** (e.g. for university students) with its own bot and terms, or ask Google directly.

## Documentation index

| Doc | What's inside |
|---|---|
| [01 – Product spec](docs/01-product-spec.md) | Features, user flows, bot commands, message formats, launch scope |
| [02 – Architecture](docs/02-architecture.md) | System diagram, tech stack, pipeline, database schema, folder layout, API for future apps |
| [03 – AI models](docs/03-ai-models.md) | Plans A/B/C, model per step, routing and fallbacks, prompts, JSON output, SymPy verification, accuracy testing |
| [04 – Speed & cost](docs/04-speed-and-cost.md) | Latency budget, speed techniques, $0 strategy, capacity worksheet, paid upgrade path |
| [05 – Daily limits](docs/05-daily-limits.md) | Limits, what counts, reset, global capacity guard, anti-abuse, algorithm, messages, admin controls |
| [06 – Weekend launch plan](docs/06-weekend-launch-plan.md) | Hour-by-hour Fri/Sat/Sun plan, scope cuts, go/no-go checklist |
| [07 – Deployment & ops](docs/07-deployment-and-ops.md) | Hosting, `mathfix.ai` DNS, BotFather setup, env vars, monitoring, runbooks |
| [08 – Privacy & safety](docs/08-privacy-and-safety.md) | Minors, provider terms, data handling, privacy policy outline, content safety |
| [09 – Roadmap: apps](docs/09-roadmap-apps.md) | Web, Android and iOS on the same backend; monetisation later |
| [Website](website/README.md) | The mathfix.ai home page (static HTML), how to preview it and deploy it on Cloudflare Pages |

---

## Sources (checked 16 Oct 2026)

This sandbox couldn't open the providers' own pages directly. The figures below come from search results, mostly
third-party trackers, so **confirm every limit and term in your own console and on the providers' sites**.

- **Gemini terms (under-18 clause):** [Gemini API Additional Terms](https://ai.google.dev/gemini-api/terms) ·
  [mirror of the 2025 terms](https://open.windriver.com/info/uni-license-list/licenses/gemini-api-additional-tos-2025.html) ·
  [Google AI forum: age restrictions question](https://discuss.ai.google.dev/t/age-restrictions-in-gemini-api-terms-general-audience-app-rated-3-with-an-adult-only-ai-feature/179916) ·
  [forum: "Only Paid Services" for EEA/CH/UK](https://discuss.ai.google.dev/t/clarification-on-only-paid-services-for-eea-ch-uk/107860) ·
  [Simon Willison on free-tier data use](https://simonwillison.net/2024/Oct/17/gemini-terms-of-service)
- **Gemini free tier:** [Gemini 3.1 Flash-Lite model page](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite) ·
  [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) ·
  [aifreeapi: Gemini free tier in 2026 (10 Oct 2026)](https://www.aifreeapi.com/en/posts/google-gemini-api-free-tier) ·
  [memetik: free tier limits (Sep 2026)](https://www.memetik.ai/guides/gemini-api-free-tier-limits) ·
  [aifreeapi: Dec 2025 quota cuts](https://www.aifreeapi.com/en/posts/gemini-api-free-tier-not-working)
- **Groq:** [klymentiev: Groq free tier 2026](https://klymentiev.com/blog/groq-pricing) ·
  [klymentiev: rate limits and 429s](https://klymentiev.com/blog/groq-api-free-tier) ·
  [TokenMix: Groq free limits 2026](https://tokenmix.ai/blog/groq-free-tier-limits-2026) ·
  [ConductAtlas: Groq terms, age](https://conductatlas.com/platform/groq/groq-terms-of-use/age-restriction-18/) ·
  [ConductAtlas: Groq acceptable use](https://conductatlas.com/platform/groq/groq-acceptable-use-policy/prohibited-content-and-use-categories/)
- **Cloudflare Workers AI:** [Llama 4 Scout model page](https://developers.cloudflare.com/workers-ai/models/llama-4-scout-17b-16e-instruct/) ·
  [agentdeals: Workers AI free tier 2026](https://agentdeals.dev/vendor/cloudflare-workers-ai) ·
  [toolfreebie: 10,000 neurons/day](https://toolfreebie.com/cloudflare-workers-ai/)
- **OpenRouter:** [OpenRouter: free LLM APIs compared (2026)](https://openrouter.ai/blog/tutorials/free-llm-apis-compared/) ·
  [TrueFoundry: OpenRouter free limits](https://www.truefoundry.com/es/blog/openrouter-rate-limits-your-free-tier-depends-on-what-youve-already-paid) ·
  [ConductAtlas: terms changed to 18+ (31 Aug 2026)](https://conductatlas.com/change/2026-09-01-openrouter-openrouter-terms-of-service-4768/)
- **Anthropic (Plan C):** [Guidelines for organisations serving minors](https://support.claude.com/en/articles/9307344-responsible-use-of-anthropic-s-models-guidelines-for-organizations-serving-minors) ·
  [Child safety guidance for developers](https://support.claude.com/en/articles/15591275-child-safety-guidance-for-developers) ·
  Claude pricing from Anthropic's model table (cached 6 Oct 2026)
- **Telegram streaming drafts:** [Telegram: AI features for bots](https://core.telegram.org/api/bots/ai) ·
  [aibase: Bot API 9.5 `sendMessageDraft`](https://news.aibase.com/news/25881)
- **Hosting:** [Cloud Run free tier 2026](https://agentdeals.dev/vendor/google-cloud-run)
