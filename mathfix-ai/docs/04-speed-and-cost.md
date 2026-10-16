# 04 · Speed & cost

## Part 1: Speed

### Targets (measure them, don't assume them)
| Request | First feedback | Full answer p50 | p95 |
|---|---|---|---|
| Cached (seen before) | < 0.3 s | **< 0.5 s** | < 1 s |
| Typed, simple (SymPy quick path) | < 0.3 s | **< 2 s** | < 4 s |
| Typed, general | < 0.3 s | **2–4 s** | < 10 s |
| Photo | < 0.3 s ("🔍 Reading…"), "I read: …" at ~2 s | **4–7 s** | < 15 s |
| Tutor reply | < 0.3 s | **1–2 s** | < 4 s |

### Where the time goes (photo, Plan A, estimated budget)
| Stage | Estimate | How we keep it small |
|---|---|---|
| Telegram → our webhook | 50–150 ms | Server in Europe (Telegram's Bot API servers are in Amsterdam) or US-East near Groq; measure both |
| Instant feedback (`typing…` + draft) | < 300 ms | Sent *before* any other work |
| Download photo from Telegram | 100–300 ms | Pick the photo size closest to 1280 px, not the original |
| Resize + JPEG + hash | 30–80 ms | Pillow, in memory |
| Cache lookup | < 5 ms | SQLite index |
| **Read photo** (Cloudflare Llama 4 Scout) | **1–2.5 s** | Short output (transcription only, ≤ 300 tokens), small image |
| Show "📸 I read: …" | 100 ms | The student sees progress, and can spot a misread before the answer arrives |
| **Solve** (Groq gpt-oss-120b) | **1–3 s** | Groq is extremely fast at generating tokens; low reasoning for easy problems; ≤ 12 steps |
| SymPy verification | 10–300 ms | Process pool, 2 s hard timeout |
| Send answer text | 100–200 ms | Sent as soon as verified, without waiting for the image |
| Render + send image | 0 ms (not on the answer path) | Only when the student taps 🖼; ~0.3 s render, then Telegram's file id is reused |
| Second opinion (only 10–20 % of solves) | +1–3 s | User sees "🔁 Double-checking…" |

### Speed techniques, ranked by impact
1. **Always-on process with a webhook.** No polling, and no free host that "sleeps" (a 30-second cold start ruins the experience).
2. **Instant feedback.** `sendChatAction("typing")` immediately, then a placeholder or draft that changes
   "🔍 Reading…" → "📸 I read: …" → "🧮 Solving…" → answer. Bot API 9.5 (March 2026) reportedly made
   `sendMessageDraft` available to all bots. Use it in private chats if your aiogram version supports it, otherwise send
   one placeholder and `editMessageText` it (max ~1 edit/second). The perceived wait drops a lot even when the real time doesn't.
3. **Groq for every text step.** Solving and tutoring run on one of the fastest inference APIs available.
4. **Answer cache.** Photos are matched by perceptual hash and text by normalised problem text (the transcription from
   step 4 counts too). Textbook questions repeat a lot across students, so a hit is < 0.5 s and uses no quota.
5. **SymPy quick path** for arithmetic and simple equations, which finds the answer in milliseconds.
6. **Right-sized reasoning.** `reasoning_effort: low` for easy problems and `medium` only for calculus, trigonometry, proofs
   or long problems. High is only for second opinions.
7. **Small images.** ≤ 1280 px, JPEG quality 85, which means fewer image tokens and a faster upload.
8. **Handwritten image on demand.** It's drawn only when the student taps 🖼, and the Telegram file id is stored so
   later taps (by anyone) are instant.
9. **Persistent HTTP connections** to each provider (one shared client, keep-alive), saving 100–300 ms per call.
10. **Skip a busy provider *before* calling it.** Our own rate-limit counters know when a quota is nearly gone, so we
    never wait on a 429 and retry.
11. **Timeouts + fast fallback.** Read 12 s · solve 15 s · tutor 8 s; then move to the next model. Don't send the same
    request to two providers at once ("hedging"), because that burns free quota.
12. **Warm start.** Import SymPy and matplotlib and load the fonts at boot, and pre-start the process pool, so the first
    user of the day isn't slow.

### Queue at peak times
Groq's free tier is reportedly **8K tokens/minute per model**, which is only ~5 full solves per minute per model. With two
solve models plus fallbacks that's **~10–15 solves per minute at peak**. When every solve model is out of per-minute
budget, the request waits in an in-memory queue for up to **30 s** with "⏳ Busy right now, you're #3 in line…". After
30 s the student gets the capacity message and the reservation is refunded.

---

## Part 2: Cost, keeping the AI API bill at $0

### What costs what
| Item | Cost |
|---|---|
| AI calls (Groq, Cloudflare Workers AI, OpenRouter free tiers) | **$0** within free limits |
| SymPy verification, handwriting images, cache, limits | **$0** (our own code) |
| Telegram Bot API | **$0** |
| Cloudflare DNS, Tunnel, Pages (landing site), Email Routing | **$0** |
| Server | **$0** on Oracle Cloud Always Free, or ~$4–6/month for a small VPS (the only optional spend, see [07](07-deployment-and-ops.md#hosting)) |
| Domain `mathfix.ai` | already bought (renewal yearly) |

### Rules that keep it at $0
1. **No card / no paid plan** on Groq, Cloudflare (Workers Free plan) or OpenRouter while in "free mode". On the free
   plans over-limit requests fail instead of being billed, so nothing can be charged by accident.
2. **Global budget counters** per model (requests and tokens per day; neurons for Cloudflare) with a 10 % safety margin.
3. **Capacity guard** ([05](05-daily-limits.md#global-capacity-guard)): when the pool is nearly used up, per-user limits
   shrink. When it's empty, users get a friendly "back at 00:00" message. We never "just keep calling".
4. **Count every call** in `provider_usage`, and alert the admin at 70 % and 90 % of any model's daily quota.
5. Note that **Cloudflare's free allowance resets at 00:00 UTC** and Groq's daily windows are rolling, while our
   user limits reset at local midnight. The capacity guard works from our own counters, so it handles the mismatch.

---

## Capacity worksheet

Fill in **your** console numbers on Friday night. The example numbers below are **illustrative only** (from October 2026
reports).

| Model | Role | Free limit | × 0.9 | Cost per use (est.) | Daily uses |
|---|---|---|---|---|---|
| Cloudflare Llama 4 Scout | read photos | 10,000 neurons | 9,000 | ~35–55 neurons (≈1–1.7K image tokens + 150 output tokens) | **≈ 200 reads** |
| OpenRouter `:free` vision | read overflow | 50 req (1,000 with $10) | 45 | 1 req | 45 reads |
| Groq `gpt-oss-120b` | solve | 200K tokens/day | 180K | ~1,500 tokens | ≈ 120 solves |
| Groq Qwen (free) | solve overflow + 2nd opinions | 200K tokens/day | 180K | ~1,500 tokens | ≈ 120 |
| Groq `gpt-oss-20b` | tutor | 200K tokens/day | 180K | ~700 tokens | **≈ 255 tutor replies** |
| **Solve capacity** | | | | minus ~15 % second opinions | **≈ 200 solves/day** |

**How many users can that serve?**
```
daily_users ≈ solve_capacity × (1 + cache_hit_rate) ÷ avg_solves_per_user
            ≈ 200 × 1.15 ÷ 3      ≈ 75 daily active users     (example numbers)
worst case  (everyone uses all 5)  ≈ 200 ÷ 5  ≈ 40 users
```

**With a one-time $10 OpenRouter purchase** (free models: 50 → 1,000 req/day, reported), photo reads plus solves through
OpenRouter add roughly **+500–900 solves/day**, so **~1,000 solves/day ≈ 300+ daily users**.

> **The takeaway:** Plan A at $0 is a **public beta** for the first ~50–80 daily users. That's the right size to learn
> from, and the upgrade path below costs very little when you need more.

---

## Paid upgrade path

Move up a step when the capacity guard hits "hard stop" before 20:00 on 3 or more days in a week, or before any big
marketing push.

| Step | What | Cost | Effect |
|---|---|---|---|
| 1 | **OpenRouter one-time ≥ $10 credit purchase** | $10 once | `:free` models go from 50 → 1,000 requests/day, permanently (reported). Cheapest capacity boost. *Check OpenRouter's terms on minors first* |
| 2 | **Plan C: Claude Haiku 5.5** (`claude-haiku-5-5`) reads and solves photos in one call | **$0.10 / M input, $0.50 / M output** tokens (prompts ≤ 100K) | ≈ 1.5K in + 1.5K out = **≈ $0.0009 per solve**, so **1,000 solves/day ≈ $27/month**. Accepts images; Anthropic allows products for minors with safeguards. Set a monthly spend limit in the Console |
| 3 | **Groq Developer tier** (card) | pay per token | Reported ~10× the free limits; open models are cheap per token. Keeps text solving and tutor on the fastest API |
| 4 | **Cloudflare Workers Paid** | ~$5/month base + $0.011 per 1,000 neurons beyond the free 10,000/day | More photo reads on Llama 4 Scout |
| 5 | **Claude Sonnet 5.5** (`claude-sonnet-5-5`) for the hardest second opinions | $2 / M input, $10 / M output | ≈ $0.02 per hard problem; only a few % of solves |

**Per-solve cost formula** (any provider):
`cost ≈ input_tokens × input_price + output_tokens × output_price`. Start from ~1,500 input tokens (prompt + 1280 px
image) and ~1,500 output tokens (steps + reasoning), and **replace these with your measured averages** from
`provider_usage` before deciding.

**Funding it later (not now):** a "MathFix Pro" plan (more solves, PDF export, history), payable inside Telegram with
**Telegram Stars**, and through app stores in phase 3 ([09](09-roadmap-apps.md)).
