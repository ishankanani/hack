# 08 · Privacy & safety

> MathFix's users are mostly **students, and many are under 18**. Design for that from day one: collect as little
> as possible, keep it for as short as possible, and be open about it.
>
> ⚖️ This document is a plan, not legal advice. Before the app-store phase (and ideally before a big launch push),
> have a lawyer review the privacy policy and the provider terms for the countries you serve.

---

## 1. Provider terms and minors (the launch blocker we found)

| Provider | What the terms say (as reported, verify yourself) | Our decision |
|---|---|---|
| **Google Gemini API** | Additional Terms (eff. 18 Dec 2025): users must be 18+, and the API must not be used in apps "directed towards or likely to be accessed by individuals under the age of 18". Free-tier inputs may be used to improve Google products, with human review. Apps offered in the EEA/CH/UK must use paid services | **Not used** (Plan B only for an adults-only product) |
| **Groq** | Account holder must be 18+ (that's you). Privacy policy: services not directed to children under 13. Acceptable-use policy bans harmful content. **No clause against apps used by minors found in summaries** | Used (Plan A). **Read the services agreement before launch** |
| **Cloudflare Workers AI** | Not checked in detail (the sandbox couldn't reach the pages) | Used (Plan A). **Read the terms, and the Llama 4 licence and acceptable-use policy** |
| **OpenRouter** | Terms reportedly changed on 31 Aug 2026 to **18+ users** (previously 13+ with parental permission). Upstream providers of `:free` models may log or train on prompts | **Overflow only**, until you confirm that apps with under-18 end users are allowed |
| **Anthropic (Claude)** | Allows organisations to let minors use API-based products **if they add safeguards** (e.g. age-appropriate design, content moderation, monitoring and reporting, educational resources) | Plan C. Write down our safeguards (section 5) |

**Friday-night task:** read the current terms of every provider in the chosen plan, and keep a dated copy (PDF) in a
private folder.

---

## 2. Data we collect, and data we don't

| Data | Collected? | Why | Kept for |
|---|---|---|---|
| Telegram user id, first name, username, language code | ✅ | Limits, replies, language | Until `/deleteme`, or 12 months inactive |
| Daily usage counters | ✅ | Daily limits | 90 days |
| **Photos** | ❌ **Not stored.** Processed in memory, sent to the vision model, then discarded | – | – |
| Image perceptual hash | ✅ (can't be turned back into the image) | Cache | 12 months |
| Problem text + solution | ✅ (not linked to the user in the `solutions` table) | Cache, quality review | 12 months |
| Tutor messages | ✅ | Tutor context | **7 days**, then deleted |
| Events (solve, limit hit, feedback…) | ✅ (user id + event name + small props) | Stats, abuse prevention | 90 days |
| Phone number, location, contacts, payment data | ❌ never | – | – |

**Never sent to AI providers:** user id, name or username. The AI sees only the maths problem (photo or text) and the
tutor conversation about it.

**`/deleteme`:** deletes the user's rows (users, usage, tutor turns, events) after a confirmation button. Cached
solutions stay, because they aren't linked to the user.

---

## 3. Telling users (in the bot and on the site)

- `/start` (first time only): *"Tip: photograph only the maths question. No names, faces or personal details. We don't
  keep your photos. Privacy: mathfix.ai/privacy"*
- `/privacy`: a 5-line summary + link.
- Every answer is labelled as AI-generated through the bot's name and description. Answers that couldn't be checked
  are labelled ℹ️ (see [03](03-ai-models.md#answer-verification-with-sympy)).

### Privacy policy outline (`mathfix.ai/privacy`)
1. Who we are and how to contact us (`support@mathfix.ai`)
2. What we collect (table above) and what we don't
3. How photos are handled (processed, not stored)
4. Which AI providers process the maths problem, and that they're in other countries
5. How long we keep data
6. Children and students: no ads, no tracking, no selling of data, parents can request deletion
7. Your rights: `/deleteme`, or email us for access or deletion
8. Changes to this policy (date at the top)

### Terms outline (`mathfix.ai/terms`)
Free beta with daily limits; answers may contain mistakes (check important work); use it for learning, and follow your
school's rules on homework and exams; no abuse or attempts to misuse the bot; we may change limits or features.

---

## 4. Content safety

| Risk | Control |
|---|---|
| Non-maths or inappropriate requests | The read prompt returns `is_math: false`, and the solve prompt returns `topic: refused`. Both get a friendly "maths only" reply. Not counted against limits |
| Tutor drifting off-topic | Tutor prompt: maths only, refuse anything else, never ask for or repeat personal information |
| Prompt injection via photo ("ignore your instructions…") | The AI only fills a JSON schema. The bot never takes actions chosen by the AI. The worst case is a wrong explanation, which verification and reports catch |
| Personal info in photos (names on worksheets) | Advise students to crop; photos are never stored; the vision prompt transcribes only the maths |
| Wrong answers | SymPy verification, second opinions, "⚠️ Wrong answer?" button, admin review of flagged solutions |
| Academic honesty | Tutor-first mode (`/tutor`) gives hints before answers; the product messaging is "understand it" |
| Abuse of the bot | Rate limits, bans, global capacity guard ([05](05-daily-limits.md#anti-abuse-launch-level)) |

---

## 5. Safeguards summary (the list to show a provider, school or parent)

1. Maths-only scope, enforced in every prompt and checked in code
2. No ads, no tracking pixels, no selling or sharing of data
3. Photos never stored; minimal data; 7-day tutor history; `/deleteme`
4. Answer verification and clear labelling of unchecked answers
5. Report button on every answer and a human admin reviewing reports daily
6. Rate limits and bans against abuse
7. Clear privacy policy and contact address

---

## 6. Before the apps (phase 2/3) and before targeting younger children
- App stores require a privacy policy and data-safety forms. Apps for children have extra rules (for example Google
  Play's Families policy and Apple's Kids category).
- Children's privacy laws apply by country (for example COPPA in the US for under-13s, GDPR and the UK Children's Code in
  Europe/UK, and India's DPDP Act rules for children's data). Get legal advice for the countries you target before
  marketing to under-13s or to schools.
