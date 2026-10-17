# 05 · Daily limits

MathFix is free for everyone, and the AI capacity behind it is free too, which means it's **shared and limited**.
Daily limits keep it fair, so one heavy user can't use up the bot for everyone else.

## Launch limits

| Allowance | Per user per day | Notes |
|---|---|---|
| **Solves** (photo or typed) | **5** at launch (Plan A) → 10+ when capacity grows | One unit per question solved |
| **Tutor messages** (Hint / Next step / Why? / typed follow-ups) | **15** at launch → 20+ later | Short replies, so they cost less capacity |
| Invite bonus | Inviter **+3** and friend **+2** solves that day, when the friend solves their first problem (inviter rewarded max 5 times a day) | `/invite` |
| Plans | Everyone is **free**. `premium` (50 solves / 200 tutor) is ready for later; give it to testers with `/setplan <user_id> premium` | `plans:` in `config/limits.yaml` |

All values live in `config/limits.yaml` and can be changed **live** with an admin command (no redeploy).

```yaml
# config/limits.yaml
reset_timezone: "UTC"            # ONE timezone for everyone: set your main audience's, e.g. "Asia/Kolkata" or "Europe/London"
per_user_daily:
  solves: 5                      # raise to 10 after the $10 OpenRouter top-up or Plan C
  tutor: 15
burst:
  max_in_flight: 1               # one request at a time per user
  max_per_minute: 5
capacity_guard:
  soft_at: 0.85                  # pool 85 % used → shrink limits
  soft_limits: { solves: 3, tutor: 8 }
  hard_at: 0.98                  # pool 98 % used → pause new solves until reset
admins: [123456789]              # your Telegram user id(s), unlimited
```

---

## What counts and what doesn't

| Event | Counts? |
|---|---|
| Successful new solve (photo or text) | ✅ 1 solve |
| Second opinion / re-check inside the same solve | ❌ (our cost, not the student's) |
| **Cache hit** (same question solved before) | ❌ free, because it costs us nothing |
| Unreadable photo, not-maths photo | ❌ |
| AI error, timeout, capacity message | ❌ refunded |
| "✏️ Fix question" (corrects what we read) | ❌ for the first correction |
| Picking another question from a multi-question photo | ✅ 1 solve (but no new photo read) |
| Answer reported **⚠️ Wrong** | 🔁 refunded (max 3 refunds/day, to prevent abuse) |
| Tutor button or typed follow-up | ✅ 1 tutor message |
| `/usage`, `/help`, `/start`, `/privacy` | ❌ |

---

## Reset
- Every day at **00:00 in `reset_timezone`**, the same moment for everyone. Simple to explain and to build.
- `/usage` always shows the countdown: *"Resets in 5 h 12 m"*.
- Implementation: the `day` key is `today()` in that timezone, so nothing needs to "run" at midnight. A new day simply
  means a new row.

---

## Global capacity guard

Per-user limits protect fairness. The **global guard** protects the free quota. It looks at all solve-capable models
together:

```
pool_used = Σ requests_today(model) / Σ (rpd(model) × 0.9)      over the solve chain
```

| Pool used | Mode | What users see |
|---|---|---|
| < 85 % | **Normal** | Normal limits (5 / 15 at launch) |
| 85–98 % | **Soft** | Limits drop to 3 solves / 8 tutor *for the rest of the day*. Users already above 3 get: *"MathFix is very busy today. You've had your share for now, back at 00:00 🙏"* |
| ≥ 98 % | **Hard** | New solves paused; cache hits and tutor (on its own Groq pool) still work. *"MathFix is at full capacity today 🙏 Free solves come back at 00:00 (in 3 h 40 m)."* |

The admin chat gets an alert on entering Soft and Hard mode, which is the signal to consider the
[paid upgrade path](04-speed-and-cost.md#paid-upgrade-path).

---

## Anti-abuse (launch level)

| Risk | Protection |
|---|---|
| Spamming requests | 1 in-flight request per user + max 5/minute. Extra messages get: *"One at a time please 🙂"* |
| Huge inputs | Text ≤ 2,000 chars, image ≤ 10 MB, no PDFs/videos at launch |
| Using the bot as a free general chatbot | Solve prompt rejects non-maths (`is_math: false`, free). Tutor refuses off-topic |
| Many Telegram accounts | Accept at launch, because the global guard caps the damage. Watch `events` for many new users from one `start_source` with max usage, and ban if needed |
| Abuse of "wrong answer" refunds | Max 3 refunds/day; solutions reported wrong ≥ 2 times are removed from cache and flagged for review |
| Group chats | Bot disabled in groups at launch (`/setjoingroups` → Disable) |

---

## Algorithm: reserve → commit / refund

Reserving *before* calling the AI means two quick messages can't both slip past the limit.

```python
async def handle_solve(user_id, request):
    day = today_in(cfg.reset_timezone)
    limit = effective_limit(user_id, "solves")          # applies capacity-guard mode, bonuses, admins
    ok = await db.execute("""
        INSERT INTO usage_daily(user_id, day, solves_reserved) VALUES (?, ?, 1)
        ON CONFLICT(user_id, day) DO UPDATE
          SET solves_reserved = solves_reserved + 1
          WHERE usage_daily.solves_used + usage_daily.solves_reserved < ?
        RETURNING 1""", (user_id, day, limit))
    if not ok:
        return reply_limit_reached(user_id)

    try:
        result = await pipeline.solve(request)
        counts = result.status == "solved" and not result.from_cache
    except Exception:
        counts = False
        raise
    finally:
        await db.execute("""
            UPDATE usage_daily
               SET solves_reserved = solves_reserved - 1,
                   solves_used     = solves_used + ?
             WHERE user_id = ? AND day = ?""", (1 if counts else 0, user_id, day))
```
- SQLite runs writes one at a time, so the conditional `UPSERT … WHERE … RETURNING` is atomic. The very first
  insert of the day always succeeds, so check `limit == 0` (banned user, or capacity guard in **Hard** mode) *before*
  running the query.
- On startup, reset any leftover `solves_reserved` to 0, which cleans up after a crash.
- The same pattern is used for `tutor_used`.

---

## User-facing messages

**`/usage`**
```
📊 Today's free MathFix
🧮 Solves: 2 of 5 left
💬 Tutor: 9 of 15 left
⏰ Resets in 5 h 12 m
Tip: answers you've already solved before are free!
```

**Solve limit reached**
```
You've used all 5 free solves for today 🎉 That's a lot of maths!
⏰ More in 5 h 12 m.
💬 You can still use the tutor on your last answers (9 messages left).
```

**Tutor limit reached**
```
That's 15 tutor messages today, great effort! 💪
Your tutor is back in 5 h 12 m.
```

**Burst**
```
One at a time please 🙂 I'm still working on your last question.
```

**Every message shows when the limit resets.** Students accept limits much better when they know exactly when they end.

---

## Admin controls

Admin commands work only for the user ids in `admins`:

| Command | Does |
|---|---|
| `/stats` | Today: users, solves, cache-hit %, verification %, p50/p95 latency, per-model quota used, guard mode |
| `/setlimit solves 8` · `/setlimit tutor 15` | Change the daily limits live |
| `/guard normal\|soft\|hard\|auto` | Force capacity-guard mode (e.g. `hard` if a provider is misbehaving) |
| `/grant <user_id> 5` | Give someone bonus solves for today (testers, support cases) |
| `/ban <user_id>` · `/unban <user_id>` | Block abusers |
| `/user <user_id>` | Usage history and recent events for one user |
| `/flag <solution_id>` | Remove a bad solution from the cache and mark it for review |
| `/broadcast <text>` | Message all users, sent at ≤ 25 messages/second to respect Telegram's limits (use sparingly) |
