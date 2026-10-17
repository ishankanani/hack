# 07 · Deployment & operations

## Hosting

The bot must be **always on**, because cold starts kill the speed. Options:

| Option | Cost | Verdict |
|---|---|---|
| **Oracle Cloud Always Free**, Arm (Ampere) VM, Ubuntu 24.04 | $0 | **Free pick.** Plenty of CPU/RAM for the bot, SymPy and image rendering. Caveats: sign-up can be fussy, and Oracle may **reclaim Always Free instances it considers idle** over a 7-day window (a lightly used bot can look idle). Read Oracle's current idle policy; upgrading the account to Pay-As-You-Go (still $0 within Always Free limits) is the commonly used fix |
| **Small VPS** (2 vCPU / 2–4 GB; Hetzner, DigitalOcean, etc.) | ~$4–6 / month | **Most reliable pick.** Five minutes to set up. The one spend worth making if Oracle sign-up fails |
| Google Cloud Run (free tier: 2M requests/month) | $0 at low traffic | Not for launch: scales to zero, so cold starts with SymPy + matplotlib imports take seconds, and SQLite doesn't persist (needs an external DB) |
| Free hosts that sleep after inactivity | $0 | ❌ The webhook goes cold, and the first message waits 30+ s |

**Region:** Europe (Frankfurt/Amsterdam) is close to Telegram's Bot API servers (Amsterdam). Groq and Cloudflare are
global/US-heavy, so measure the round-trip from your VM to `api.groq.com` and pick the region with the lowest total.

---

## Domain: `mathfix.ai` on Cloudflare (all free)

1. Add `mathfix.ai` to Cloudflare (Free plan) → change nameservers at your registrar → wait for "Active".
2. DNS records:

| Name | Type | Target | Purpose |
|---|---|---|---|
| `mathfix.ai` | (Pages custom domain) | Cloudflare Pages project | Landing page, `/privacy`, `/terms` |
| `www` | CNAME | `mathfix.ai` | redirect to apex |
| `bot` | CNAME (created by `cloudflared`) | `<tunnel-id>.cfargotunnel.com` | Telegram webhook → your VM |
| `api` | – | *(phase 2)* | REST API for web/mobile apps |
| MX/TXT | (Email Routing wizard) | Cloudflare Email Routing | `support@mathfix.ai` → your inbox, free |

3. **Cloudflare Tunnel** on the VM (no open ports, free TLS):
```bash
cloudflared tunnel login
cloudflared tunnel create mathfix
cloudflared tunnel route dns mathfix bot.mathfix.ai

# /etc/cloudflared/config.yml
tunnel: <TUNNEL_ID>
credentials-file: /etc/cloudflared/<TUNNEL_ID>.json
ingress:
  - hostname: bot.mathfix.ai
    service: http://localhost:8080
  - service: http_status:404

sudo cloudflared service install && sudo systemctl enable --now cloudflared
```

4. **Register the webhook** with Telegram (once, and after every token change):
```bash
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
  -d url="https://bot.mathfix.ai/tg/webhook" \
  -d secret_token="$TELEGRAM_WEBHOOK_SECRET" \
  -d max_connections=40 \
  -d allowed_updates='["message","callback_query"]' \
  -d drop_pending_updates=true
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo"   # check: no last_error_message
```

---

## BotFather setup

| BotFather command | Value |
|---|---|
| `/setname` | `MathFix AI` |
| `/setabouttext` (≤ 120 chars) | `Snap or type a maths problem → answer, steps, handwritten notes & an AI tutor. Free daily. mathfix.ai` |
| `/setdescription` (≤ 512 chars, shown before Start) | see below |
| `/setuserpic` | upload [`brand/telegram-profile.png`](../brand/telegram-profile.png) (the MathFix "M" on white, made for Telegram's round avatar) |
| `/setcommands` | see below |
| `/setjoingroups` | **Disable** (private chats only at launch) |
| `/setprivacy` | Enable (default) |
| `/setinline` | off (later) |

**Description**
```
📸 Send a photo of any maths question, or type it.
✅ Get the correct answer, checked by a maths engine
📝 Clear step-by-step explanation
✍️ A neat handwritten-style solution image
💬 A patient tutor for hints and "why?"

Public beta: free 5 solves + 15 tutor messages every day.
Privacy: mathfix.ai/privacy
```

**Commands** (paste into `/setcommands`)
```
start - Start MathFix AI
solve - Solve a typed problem (or just send a photo)
me - Your profile, streak and free solves
invite - Invite friends, get extra solves
tutor - Turn tutor mode on or off
usage - Free solves left today
lang - Change explanation language
class - Change your class
help - Tips for the best results
feedback - Tell us what to improve
privacy - How we handle your data
deleteme - Delete all your data
```

---

## Environment variables (`/opt/mathfix/.env`, never in git)

```bash
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=          # random, 32+ chars of A-Z a-z 0-9 _ -
WEBHOOK_BASE_URL=https://bot.mathfix.ai
GROQ_API_KEY=
CF_ACCOUNT_ID=
CF_AI_API_TOKEN=                  # Cloudflare API token with Workers AI permission
OPENROUTER_API_KEY=
ANTHROPIC_API_KEY=                # leave empty unless Plan C is switched on
ADMIN_CHAT_ID=                    # private admin group/channel for alerts
ADMIN_USER_IDS=                   # comma-separated Telegram user ids
DATABASE_PATH=/opt/mathfix/data/mathfix.db
LOG_LEVEL=INFO
```

---

## Running it

**systemd unit** `/etc/systemd/system/mathfix.service`
```ini
[Unit]
Description=MathFix AI Telegram bot
After=network-online.target
Wants=network-online.target

[Service]
User=mathfix
WorkingDirectory=/opt/mathfix
EnvironmentFile=/opt/mathfix/.env
ExecStart=/opt/mathfix/.venv/bin/python -m mathfix.main
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
```

**Deploy a new version**
```bash
cd /opt/mathfix && git pull && .venv/bin/pip install -r requirements.txt \
  && .venv/bin/python -m pytest -q tests/fast && sudo systemctl restart mathfix
```
Telegram keeps undelivered updates (for up to 24 h) and retries the webhook, so a few seconds of restart loses no messages.

---

## Monitoring & alerts

| What | How | Alert when |
|---|---|---|
| Is it alive? | `GET https://bot.mathfix.ai/health` (checks DB + process pool) pinged every 5 min by a free uptime monitor | 2 failures in a row |
| Is Telegram reaching us? | In-process check of `getWebhookInfo` every minute | `pending_update_count > 50` or a new `last_error_message` |
| Errors | Count per 10 min from logs | error rate > 5 % |
| Provider health | `provider_usage` table | 429 storm (> 20 in 5 min) or a model returning 404 (model removed) |
| Free quota | `provider_usage` vs limits | any model at **70 %** and **90 %** of its daily quota |
| Capacity guard | guard mode change | entering **Soft** or **Hard** |
| Daily summary | 23:55 report to admin chat | always: users, solves, cache-hit %, verified %, p50/p95, wrong reports, limit hits |

Logs are JSON lines in journald (`journalctl -u mathfix -f`). **Never log photos, tokens or API keys.** Log user
ids, not names.

---

## Runbooks

| Problem | Do this |
|---|---|
| **Bot not replying** | `systemctl status mathfix cloudflared` → `getWebhookInfo` (`last_error_message`) → `sudo systemctl restart mathfix` |
| **Provider 429 / 5xx storm** | The router cools the model down automatically. If it persists, remove it from the chain in `models.yaml` and reload (`systemctl reload` or restart) |
| **Free model removed or renamed** (404 "model not found") | Put the new ID in `models.yaml`, run the golden set for that step (`--limit 20` is enough for a quick check), restart |
| **Free quota gone early in the day** | Guard switches to Soft/Hard automatically. Consider [upgrade step 1 or 2](04-speed-and-cost.md#paid-upgrade-path) |
| **Wrong answer spreading** (several reports) | `/flag <solution_id>` removes it from cache; check the prompt/model; add the problem to the golden set |
| **Bot token leaked** | BotFather `/revoke` → new token in `.env` → restart → run `setWebhook` again |
| **API key leaked** | Revoke in that provider's console → new key in `.env` → restart. Check usage for abuse |
| **Server lost** | New VM → `git clone` → restore latest DB backup → `.env` from password manager → tunnel → `setWebhook`. Target: < 1 hour |

---

## Backups

Nightly cron at 03:00:
```bash
sqlite3 /opt/mathfix/data/mathfix.db ".backup '/opt/mathfix/backups/mathfix-$(date +%F).db'"
find /opt/mathfix/backups -name 'mathfix-*.db' -mtime +7 -delete
```
Copy it **off the server** too: send the file to the private admin channel with the bot (`sendDocument`, fine while the DB
is small), or upload it to Cloudflare R2 (free tier). Test a restore once before launch.
