# 06 · Weekend launch plan (Fri 16 – Sun 18 Oct 2026)

**Goal:** @mathfixbot live and public on **Sunday ~18:00**, with photo and text solving, steps, handwritten
image, tutor buttons, daily limits and admin alerts.
**Rule:** if something is late, cut from the "nice to have" list. Don't skip testing or the limits.

---

## Friday evening: prep (≈ 3 h)

DNS can take hours, so start with it.

- [ ] **Domain → Cloudflare**: add `mathfix.ai` to Cloudflare (free plan) and change the nameservers at your registrar. *(15 min + waiting)*
- [ ] **BotFather**: confirm the @mathfixbot token works; set name, about, description, commands and picture ([07](07-deployment-and-ops.md#botfather-setup)). *(20 min)*
- [ ] **Decide the plan** ([03](03-ai-models.md#the-three-plans)): A ($0, open models: the default), B (Gemini, adults-only)
      or C (Claude Haiku 5.5, ~$0.001/solve). Read the **terms** of each provider in your plan, especially anything about
      users under 18. *(30 min)*
- [ ] **API keys**: Groq console, Cloudflare (account ID + Workers AI token), OpenRouter (and Anthropic if Plan C). Store them in a password manager. *(20 min)*
- [ ] **Record the real free limits** for each model ([03](03-ai-models.md#verify-on-friday-night)) and fill in the
      [capacity worksheet](04-speed-and-cost.md#capacity-worksheet). Confirm or adjust the 5 / 15 daily limits. *(30 min)*
- [ ] **Quick model smoke test**: send 3 maths photos to each vision model and 3 text problems to each text model
      (a simple script or the AI Studio UI). Drop any model that misreads badly. *(30 min)*
- [ ] **Server**: create the VM ([07](07-deployment-and-ops.md#hosting)); install Python 3.12, git, `cloudflared`; create the
      `mathfix` user. *(45 min)*
- [ ] **Repo skeleton**: folders from [02](02-architecture.md#folder-layout-code-to-be-written-on-saturday), `.gitignore` with `.env`,
      `requirements.txt`. *(20 min)*
- [ ] **Golden test set**: ask 5–10 friends or students to send real homework photos tonight; write 60 text problems
      with answers (copy from textbooks and past papers). *(ongoing through Saturday)*

---

## Saturday: build day

| Time | Build | Done when |
|---|---|---|
| 09:00–10:30 | Bot skeleton: aiogram webhook, `/start` `/help` `/usage`, DB schema, user upsert, `/health` | Bot replies to `/start` through `bot.mathfix.ai` |
| 10:30–12:30 | AI layer: one OpenAI-compatible client for Groq / Cloudflare / OpenRouter, router with fallback chains, rate-limit and token/neuron counters, pydantic `Reading` + `Solution` schemas | `run_step("solve", "2x+3=11")` returns valid JSON; disabling a key makes it fall back |
| 12:30–13:15 | *Lunch* | |
| 13:15–15:00 | Solve pipeline: photo download/resize/pHash, cache, SymPy quick path, solve call, LaTeX → Unicode answer message, inline buttons | Photo in Telegram → correct answer message |
| 15:00–16:30 | SymPy verifier (whitelist, process pool, timeouts) + second-opinion path | Deliberately wrong answer gets caught and re-solved |
| 16:30–18:30 | Handwritten renderer (fonts, paper, jitter, answer box, footer) | Image arrives < 1 s after the text and looks good on a phone |
| 18:30–19:30 | Daily limits (reserve/commit/refund), burst limit, capacity guard, limit messages | 11th solve is blocked; failed solve is refunded |
| 19:30–21:00 | **Run golden set** on every model in the chain, tune prompts, record p50/p95 | Text ≥ 90 %, photo ≥ 85 %; latency table filled in |
| 21:00 | Deploy to the server as a `systemd` service; test from your own phone | Survives `sudo systemctl restart mathfix` |

---

## Sunday: polish + launch

| Time | Task |
|---|---|
| 09:00–11:00 | Tutor: Hint / Next step / Why? / Explain simpler / Show answer, typed follow-ups, `/tutor` mode, tutor limit |
| 11:00–12:00 | Edge cases: unreadable, not-maths, multi-question picker, "✏️ Fix question", "⚠️ Wrong answer?" (refund + flag), `/feedback`, `/privacy` |
| 12:00–13:00 | Admin: `/stats`, `/setlimit`, `/guard`, `/grant`, `/ban`; alerts to admin chat (errors, 70 %/90 % quota, guard mode); nightly DB backup cron |
| 13:00–14:00 | `mathfix.ai` landing page on Cloudflare Pages: hero, "Open in Telegram" button (`https://t.me/mathfixbot?start=web`), example image, **privacy** and **terms** pages |
| 14:00–15:00 | Lunch + mini load test: script 30 fake users sending 3 requests each over 2 minutes; check no crash, queue works, limits hold |
| 15:00–16:00 | **Closed beta** with 20–50 testers (classmates, a teacher, family). Watch logs and `/stats` live |
| 16:00–17:30 | Fix the top 3–5 issues from the beta |
| 17:30 | **Go / no-go** (checklist below) |
| 18:00 | **Public launch** (see below) |
| 18:00–23:00 | Watch `/stats` and the admin alerts; reply to feedback quickly. First impressions matter |

### If you're behind schedule, cut in this order
1. Streaming "I read: …" preview (keep the simple placeholder)
2. Multi-question picker (solve the first question, and say "send one question per photo for the others")
3. "Explain simpler" button
4. Load test (do a smaller manual one instead)
5. **Never cut:** verification, daily limits, capacity guard, privacy page, admin alerts.

---

## Go / no-go checklist (Sunday 17:30)

**Quality**
- [ ] Golden set: ≥ 90 % correct (text), ≥ 85 % (photos)
- [ ] Beta testers' "wrong answer" reports < 5 %
- [ ] Handwritten image readable on a small phone screen

**Speed**
- [ ] p50: text < 5 s, photo < 8 s; p95 < 15 s
- [ ] "typing…"/placeholder appears in < 0.5 s

**Limits & cost**
- [ ] 11th solve blocked; cache hits don't count; failures refunded
- [ ] Capacity guard tested by forcing `/guard soft` and `/guard hard`
- [ ] No card or paid plan on Groq, Cloudflare or OpenRouter (Plan A); quota alerts reach the admin chat

**Reliability & security**
- [ ] Fallback works when the primary key is removed
- [ ] Service restarts automatically (`kill -9` test)
- [ ] Webhook secret checked; `.env` not in git; SymPy sandbox timeout works on `factorial(10**9)`
- [ ] Backup ran once and the file can be opened

**Legal**
- [ ] `mathfix.ai/privacy` and `/terms` live and linked from `/privacy` in the bot ([08](08-privacy-and-safety.md))

---

## Launch (Sunday 18:00)

1. Post with **tracked deep links**, so `/stats` can show which channel brings users:
   - `https://t.me/mathfixbot?start=launch_insta`, `…?start=launch_whatsapp`, `…?start=launch_yt`, `…?start=web`
2. Share a **15-second screen recording**: photo of a handwritten problem → answer → handwritten image.
3. Post in student/maths communities where self-promotion is allowed, and send to classmates and teachers.
4. Say it in the bot's description: *"Free: 5 solves + 15 tutor messages every day."* Call it a **public beta**, which
   makes the small limits feel fair, and raise them as capacity grows.

## Launch week (Mon 19 – Sun 25 Oct)
- Daily 10-minute review of `/stats`: limit hits, capacity-guard minutes, wrong-answer reports, slowest requests.
- Re-run the golden set whenever a prompt or model changes.
- Re-check providers' free limits mid-week (they change without notice).
- Decide on the [paid upgrade path](04-speed-and-cost.md#paid-upgrade-path) if the guard hits "hard" before 20:00 on 3 days.
- Start the app phase plan ([09](09-roadmap-apps.md)) once the bot is stable for 7 days.
