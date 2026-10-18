# 03 · AI models: what runs at every step

## The rule
> **Use AI only for reading, explaining and tutoring. Use code for everything that must be exact.**

Language models are good at reading messy handwriting and explaining things like a teacher. They're unreliable at
arithmetic and they're slow and costly at drawing. So MathFix:
- asks the AI to **read and explain**,
- asks **SymPy** (a computer-algebra library) to **check the answer**,
- uses **plain drawing code** for the handwritten-style image.

That's how the bot can be **more accurate, faster and $0** all at once.

---

## The three plans

The AI provider decision is driven by two facts:
1. **Students are mostly under 18.** Google's Gemini API Additional Terms (effective 18 Dec 2025) forbid using the API
   in apps "directed towards or likely to be accessed by individuals under the age of 18". That covers the free and paid tiers.
2. **The AI bill must be $0 for now.**

| | **Plan A: launch default** | Plan B | Plan C: best product |
|---|---|---|---|
| Photo reading | Cloudflare Workers AI · Llama 4 Scout | Gemini Flash-Lite | Claude Haiku 5.5 |
| Solving | Groq · gpt-oss-120b | Gemini Flash-Lite | Claude Haiku 5.5 |
| Tutor | Groq · gpt-oss-20b | Gemini Flash-Lite | Groq · gpt-oss-20b (free) |
| AI cost | **$0** | **$0** | ≈ **$0.001 per solve** |
| Free capacity (est.) | ~200 solves/day (~1,000 with one-time $10 OpenRouter top-up) | ~1,000 solves/day | unlimited (pay per use) |
| Handwriting reading quality | good (test it!) | very good | very good |
| Under-18 users | No clause against it found in Groq's terms; **verify Groq + Cloudflare terms** | ❌ **not allowed** | ✅ allowed **with safeguards** (Anthropic's guidelines for organisations serving minors) |
| Use it when | Launching now at $0 | Only if MathFix is **adults-only** | Demand outgrows Plan A and ~$1/day is OK |

**Recommendation:** launch on **Plan A**. Pre-wire **Plan C** in `models.yaml` (with no key, so it's disabled) so the
switch is a 5-minute config change. Plan B is documented only so you know why it isn't the default.

> ⚖️ This is a planning document, not legal advice. Read each provider's current terms yourself (links in the
> [README sources](../README.md#sources-checked-16-oct-2026)) before launch.

---

## Plan A: model per step

| # | Step | Model / tool | Settings | Why | Fallback chain |
|---|------|--------------|----------|-----|----------------|
| 1 | Intake: download, resize, hash | **Code** (Pillow, imagehash) | longest side ≤ 1280 px, JPEG q85 | Smaller upload means faster, cheaper vision | – |
| 2 | Cache lookup | **Code** (SQLite) | image pHash distance ≤ 4, or same normalised text | Repeats cost no quota and come back in < 0.5 s | – |
| 3 | Quick maths (typed only) | **Code** (SymPy) | arithmetic, %, fractions, 1-variable linear/quadratic, 2×2 systems | Exact answer in ms. The AI then only writes the steps for a *known* answer | → step 5 |
| 4 | **Read photo** → maths text | **Cloudflare Workers AI** `@cf/meta/llama-4-scout-17b-16e-instruct` (vision) | JSON output, ≤ 300 output tokens, temperature 0 | Vision model on a free daily allowance (10,000 neurons/day); transcription is short, so it's cheap | OpenRouter `:free` vision model → (Plan C) Claude Haiku 5.5 |
| 5 | **Solve** (typed, or the text read in step 4) | **Groq** `openai/gpt-oss-120b` | `reasoning_effort`: **low** for easy, **medium** otherwise; JSON output | Strong maths reasoning, open-weight (Apache-2.0), and Groq is among the fastest APIs | Groq's free **Qwen** model (current ID in console) → Cloudflare `@cf/openai/gpt-oss-120b` (if in the free allowance) → OpenRouter `:free` reasoning model |
| 6 | Verify answer | **Code** (SymPy, sandboxed) | ≤ 2 s timeout | Catches most arithmetic/algebra slips, and costs nothing | – |
| 7 | **Second opinion** (only when needed) | **Groq Qwen** (free) | thinking on | A *different model family* catches different mistakes | Groq `gpt-oss-120b`, `reasoning_effort: high` |
| 8 | Telegram text | **Code** (LaTeX → Unicode) | | Telegram can't render LaTeX | – |
| 9 | **Handwritten-style image** | **Code** (Pillow + matplotlib + handwriting font) | see [spec below](#the-handwritten-style-image-no-ai) | $0, ~0.3 s, maths always exact. Image-generation AIs are slow, paid and garble equations | plain text only |
| 10 | **Tutor chat** | **Groq** `openai/gpt-oss-20b` | `reasoning_effort: low`, ≤ 200 output tokens | Hints are short and must feel *instant* | Cloudflare small text model → OpenRouter `:free` |
| 11 | Practice similar *(after launch)* | Groq `gpt-oss-20b` | answers verified with SymPy before showing | Cheap generation; verified answers | – |

**Easy vs hard (no AI needed):** a tiny code heuristic sets the reasoning level. Calculus (`∫ d/dx lim`), trigonometry,
proofs, more than 2 equations, or more than 200 characters means **medium**. Everything else is **low**. Low reasoning
roughly halves the tokens and the time.

**When does step 7 (second opinion) run?** Only if one of these is true, so it should be about 10–20 % of solves:
- SymPy verification **failed**,
- the model's own `confidence` < 0.7,
- the problem is "hard" **and** the answer can't be machine-checked (proofs, word problems, geometry reasoning). In that
  case both answers are compared. If they agree, show "✔️ Two independent methods agree". If they disagree, show the
  verified one, or the better-scored one with "ℹ️ Double-check this one".

**Why two calls for a photo (read, then solve)?** The free vision models are good readers but weaker reasoners than
`gpt-oss-120b`. Splitting also means:
- we can show **"I read: …" early** so the student spots a misread,
- the transcription feeds the **text cache**, so the same textbook question photographed by a different student is a cache hit,
- a multi-question photo needs only **one** read, and each chosen question is a cheap text solve.

---

## Plan B: Gemini (adults-only product)

Only if you decide MathFix is for 18+ users. Then **one call reads and solves**: Gemini Flash-Lite (current stable ID, e.g.
`gemini-3.1-flash-lite`, GA since May 2026) with a JSON schema; fallback to a second Flash-Lite version (each model ID
has its own quota bucket), then Gemini Flash. Groq stays for second opinions and tutor.
Extra caveats: free-tier prompts may be used by Google to improve its products, with human review; the terms
reportedly require **paid** services for apps offered in the EEA, Switzerland or the UK; and Pro models reportedly
left the free tier on 1 Apr 2026.

## Plan C: Claude Haiku 5.5 (paid, minors allowed with safeguards)

- **Read + solve in one call:** `claude-haiku-5-5` with the image, structured JSON output (`output_config.format`),
  and **effort `low`** for easy problems or `medium` (its default) for hard ones. Price: **$0.10 / M input, $0.50 / M output
  tokens** (prompts ≤ 100K), which works out to **≈ $0.0009 per solve** (≈1.5K in + 1.5K out).
- **Second opinion:** keep Groq Qwen (free), or `claude-sonnet-5-5` ($2 / $10 per M) for the hardest ~5 %.
- **Tutor:** keep Groq `gpt-oss-20b` (free and fastest).
- **Safeguards Anthropic asks of products serving minors** (see the guidelines linked in the README): content moderation
  and filtering, monitoring and reporting, age-appropriate design, and being open that users are talking to an AI.
  MathFix's design (maths-only prompt, refusal of off-topic requests, feedback/report button, admin review) covers most
  of this. Write it down in the privacy page.
- **Set a hard monthly spend limit** in the Anthropic Console before switching on.

---

## Free-tier landscape (as reported mid-October 2026, confirm in your own console)

| Provider | Free models we use | Reported free limits | Terms notes |
|---|---|---|---|
| **Groq** | `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, free Qwen model (reported: Qwen 3.6 / 3.8 27B) | per model: **30 req/min, 1,000 req/day, 8K tokens/min, 200K tokens/day**; per organisation (extra keys don't add capacity) | Account holder must be 18+ (that's you). No clause against apps used by minors found in summaries; acceptable-use policy bans harmful content. **Read the services agreement** |
| **Cloudflare Workers AI** | `@cf/meta/llama-4-scout-17b-16e-instruct` (vision; listed at $0.27 / $0.85 per M tokens), `@cf/openai/gpt-oss-120b` | **10,000 neurons/day free** (resets 00:00 UTC; over-limit requests fail on the free plan). Some newer models are paid-plan only | Llama 4 licence: check its acceptable-use policy (and EU restrictions if *you* are EU-based). **Read the Workers AI terms** |
| **OpenRouter** | one `:free` vision + one `:free` reasoning model (they rotate, so pick on Friday) | 20 req/min; **50 req/day**, or **1,000 req/day** after a one-time lifetime purchase of ≥ $10 | Terms changed on 31 Aug 2026 to **18+ users** (reported). Unclear for apps whose end-users are minors, so treat it as **overflow only** until clarified. Each free model's upstream provider may log or train on inputs |
| Google Gemini | (Plan B only) Flash-Lite, Flash | set per project in AI Studio; reports range ~20 to ~1,500 req/day per model | ❌ under-18 clause; free-tier data used for product improvement |

### Verify on Friday night
1. **Groq console** → Settings → Limits. Note RPM / RPD / TPM / TPD for `gpt-oss-120b`, `gpt-oss-20b` and the Qwen
   model. Read Groq's **services agreement / terms** for anything about end users or minors.
2. **Cloudflare dashboard** → Workers AI. Check the free neuron allowance and that Llama 4 Scout (and `gpt-oss-120b`)
   run on the free plan. Create an API token with *Workers AI: Read/Edit*. Read the terms.
3. **OpenRouter** → models, filtered by "free" + "image input". Pick one vision model and one reasoning model and test them
   with maths photos. Re-read the current terms on minors.
4. **Smoke test the readers:** 10 real homework photos through each vision model. Count exact transcriptions and keep
   the best as first choice.
5. Put the numbers × 0.9 into `config/models.yaml` and into the
   [capacity worksheet](04-speed-and-cost.md#capacity-worksheet).

---

## The router (how a model is chosen)

```python
async def run_step(step: str, request) -> Result:
    for model in config.steps[step]:                       # ordered list from models.yaml
        if not model.enabled:                              # e.g. Plan C models with no key yet
            continue
        if not budget.has_room(model, est_tokens(request)):    # RPD/TPD used < 90 %, RPM/TPM bucket has room
            continue
        if cooldown.active(model):                         # got a 429/5xx in the last 60 s
            continue
        try:
            raw = await asyncio.wait_for(call(model, request), timeout=config.timeouts[step])
            result = SCHEMAS[step].model_validate_json(raw.text)   # pydantic, so bad JSON raises
            budget.record(model, usage=raw.usage)
            return result
        except RateLimited as e:  cooldown.start(model, seconds=e.retry_after or 60)
        except (Timeout, ServerError, ValidationError):   cooldown.start(model, seconds=20)
    raise AllProvidersBusy        # → user gets the "capacity" message, reservation refunded
```

- **Skip before failing.** Our own counters know when a quota is nearly used up, so we don't waste seconds on 429s.
- **One retry on bad JSON** with the same model (the error is appended to the prompt), then fall through.
- Every call logs `model, latency_ms, tokens_in, tokens_out, ok/error` to `provider_usage`, which drives the admin
  stats and the capacity guard.
- Groq, Cloudflare and OpenRouter all speak the **OpenAI-compatible chat API**, so one client class with three base URLs
  covers Plan A. Plan C adds the Anthropic SDK.

### Big problems (machine learning, long derivations)

gpt-oss is a reasoning model: its hidden reasoning counts against `max_tokens`. With the normal budget (2,500), a
long university problem used most of it thinking, the JSON answer was cut off, and the solve failed. What the
pipeline does now:

- `is_big()` (long text, or words like gradient, regression, softmax, eigen, norm, ∇) marks a problem as big.
- Big problems get `max_tokens_big` (5,500 on Groq, which keeps prompt + output under the free 8,000 tokens per
  minute; 6,000 on Cloudflare), `timeouts_big` (100 s) and `est_tokens_big` for the budget check.
- An answer cut off at `max_tokens` (`finish_reason: length`) is retried once with the big budget.
- Groq's JSON mode rejects a reply with invalid JSON as HTTP 400 `json_validate_failed`. That used to bench the
  model for 10 minutes; now the reply in `failed_generation` is repaired and used.
- LaTeX inside JSON (`\lambda`, `\|W\|`, `\frac`) is repaired before parsing. Unrepaired, it either fails to parse
  or silently becomes control characters (`\f` in `\frac` is a form feed).
- Big problems skip the automatic second full solve when the answer can't be machine-checked (derivations usually
  can't), because it doubled the wait and used the whole per-minute token budget. They still get one when the check
  fails or the model reports low confidence.
- Photo reading has 1,200 output tokens, since a long question appears up to three times in the reply.

On the free Groq tier one big problem uses most of a minute's tokens, so a burst of big problems falls back to the
slower Cloudflare model. A paid Groq tier removes that limit.

---

## Structured outputs

### Step 4: photo reading
```json
{
  "is_math": true,
  "readable": true,
  "problems": ["Solve 2x^2 - 8x + 6 = 0", "Find the value of 3/4 + 5/6"],
  "problem_text": "Solve 2x² − 8x + 6 = 0",
  "problem_latex": "2x^{2}-8x+6=0",
  "confidence": 0.9
}
```

### Step 5: solving (also the format Plan B/C return in their single call, with the step-4 fields included)
```json
{
  "topic": "quadratic_equations",
  "grade_level": "9-10",
  "difficulty": 2,
  "steps": [
    {"say": "Divide everything by 2", "math": "x^{2}-4x+3=0"},
    {"say": "Find two numbers that multiply to 3 and add to −4: −1 and −3", "math": ""},
    {"say": "Factorise", "math": "(x-1)(x-3)=0"},
    {"say": "Set each bracket to zero", "math": "x=1 \\text{ or } x=3"}
  ],
  "final_answer": "x = 1 or x = 3",
  "final_answer_latex": "x=1 \\text{ or } x=3",
  "check": {
    "type": "equation_solutions",
    "expr": "2*x**2 - 8*x + 6",
    "variable": "x",
    "values": ["1", "3"]
  },
  "confidence": 0.95
}
```
`check.type` is one of: `equation_solutions` · `expression_value` · `simplify_equal` · `derivative` ·
`antiderivative` · `definite_integral` · `limit` · `numeric` · `none`.

---

## Prompts (drafts, tune them on Saturday against the golden set)

### Read (vision)
```text
You transcribe maths questions from photos. Reply ONLY with JSON matching the schema.
- Copy every separate maths question you see into "problems", exactly as written (plain text, use ^ for powers).
- Put the first one in "problem_text" (with Unicode maths: x², √, π) and "problem_latex".
- Do NOT solve anything. Do NOT fix the question, even if it looks wrong.
- If the image is too blurry or cut off, set "readable": false. If it is not maths, set "is_math": false.
- "confidence": how sure you are the transcription is exactly right (0 to 1).
```

### Solve
```text
You are MathFix, a careful and friendly maths teacher. Reply ONLY with JSON matching the schema.
Problem: {problem_text}
1. Solve step by step at the student's level ("grade_level"). Each step = one short sentence
   in "say" + at most one line of LaTeX in "math". Maximum 12 steps. No skipped algebra.
2. Before finishing, check your answer yourself (substitute back, or estimate).
3. Fill "check" using SymPy syntax (use ** for powers, * for multiplication, sqrt(), pi, E,
   log(), sin()) so the server can verify the answer. Use "none" only if it truly cannot be checked.
4. Write "say" text in {language}. Be encouraging, never condescending.
5. If the problem is not maths or is not appropriate for a school maths helper, return no steps
   and set "topic": "refused".
```
If the quick-maths path already found the answer, add:
`The verified correct answer is: {sympy_answer}. Explain how to reach it. Do not change it.`

### Second opinion
```text
Solve this problem independently from scratch, carefully, step by step. Reply ONLY with JSON (same schema).
Problem: {problem_text}
Note: an earlier attempt answered "{previous_answer}" but it failed an automatic check ({reason}).
Do not assume that earlier answer is right or wrong. Work it out yourself.
```

### Tutor
```text
You are MathFix Tutor, a patient maths tutor for a school student.
Context: the problem, the verified solution steps and final answer are below.
- Prefer the Socratic method: give ONE hint or ask ONE guiding question at a time.
- Give the full answer only when the student presses "Show answer" or asks twice.
- Keep replies under 80 words. Plain text with Unicode maths (x², √, π, ≤). No LaTeX, no markdown tables.
- Only discuss this maths problem or maths learning. Politely refuse anything else, and never
  ask for or repeat personal information.
- Never contradict the verified final answer.
Action requested: {hint | next_step | why:{step_number} | simpler | free_text}
```

---

## Answer verification with SymPy

| `check.type` | How it's verified |
|---|---|
| `equation_solutions` | Substitute each value into `expr`; `simplify(result) == 0`, plus numeric check at 30-digit precision. Also solve with SymPy and compare the solution *sets* (catches missing roots) |
| `expression_value` | Evaluate the problem expression exactly and compare with the answer |
| `simplify_equal` | `original − answer` is 0 at 5 random points (numeric) |
| `derivative` | `diff(f) − answer` is 0 at 5 random points |
| `antiderivative` | `diff(answer) − integrand` is 0 at 5 random points (any +C is fine) |
| `definite_integral` | `mpmath.quad` numeric value vs answer, relative error < 1e-8 |
| `limit` | `sympy.limit` vs answer |
| `numeric` | Recompute the given formula and compare within 1e-6 (geometry, statistics, % problems) |
| `none` | Mark as "not machine-checked"; escalation rules decide whether to get a second opinion |

**Labels shown to users:** ✔️ *Checked*, ℹ️ *Couldn't check this one automatically*, or (after a failed check and a
failed second opinion) the best answer with a clear warning, logged for review.

**Safety (important):** SymPy's `parse_expr` uses Python `eval`, so model output must never be eval'd directly.
1. Whitelist: characters `0-9 a-z A-Z + - * / ^ ( ) = . ,` and space; a fixed list of names (`sin cos tan asin acos atan
   log ln exp sqrt pi E I Abs factorial binomial`); reject `_`, `__`, `lambda`, `import`, and anything longer than 300 characters.
2. Run in a **separate process pool** (`concurrent.futures.ProcessPoolExecutor`) with a **2 s timeout**. That also
   protects against SymPy hanging on a hard `simplify` or a huge `factorial`.
3. A verifier crash or timeout counts as `none` (not checkable), never as "verified".

---

## The handwritten-style image (no AI)

| Property | Spec |
|---|---|
| Size | 1080 px wide; height grows with steps; split into a 2-image album above ~2,400 px |
| Paper | off-white `#FDFBF5`, light-blue rules every 64 px, red margin line at x = 90 |
| Ink | dark blue `#1A3A8F`; final answer in red `#C62828` inside a slightly wobbly hand-drawn box |
| Fonts | **Kalam**, **Caveat** or **Patrick Hand** (Google Fonts, SIL Open Font License, so free for commercial use) |
| Maths | matplotlib `mathtext` with `mathtext.fontset = "custom"` using the handwriting font for `rm`/`it`, and `mathtext.fallback = "stix"` for symbols the font lacks (∫, √, Σ) |
| Hand feel | each line rotated ±1.5°, baseline jitter ±3 px, random seed = hash of the problem, so the same problem gives an identical image |
| Layout | "Question" → problem → numbered steps → boxed answer → small footer `mathfix.ai · @mathfixbot` |
| Speed | target < 400 ms; runs in the process pool so it never blocks the bot |
| Fallback | if a LaTeX line fails in mathtext (e.g. matrices, `align`), render that line as plain Unicode text |

---

## Accuracy testing (before launch and after every prompt/model change)

**Golden set** in `tests/` (build it Friday night / Saturday):

| Topic | Text problems | Photos (real handwriting + textbook prints) |
|---|---|---|
| Arithmetic, fractions, % | 10 | 5 |
| Linear & quadratic equations, inequalities | 12 | 6 |
| Algebra simplification, factorising | 8 | 4 |
| Geometry & mensuration | 8 | 4 |
| Trigonometry | 7 | 4 |
| Calculus (derivatives, integrals, limits) | 10 | 5 |
| Statistics & probability, word problems | 5 | 2 |
| **Total** | **60** | **30** |

Run `python -m tests.run_golden --step solve --model groq_oss_120b` (and `--step read --model cf_llama4_scout`) to
print accuracy, verification rate, p50/p95 latency and tokens used. Do this for **every model in each chain**, so you
know what quality each fallback gives.

**Launch bar:** ≥ 90 % correct on text, ≥ 85 % on photos (transcription *and* answer), 0 crashes.

---

## What we deliberately don't use (yet)

| Not used | Why |
|---|---|
| Google Gemini API (as default) | Its terms forbid apps likely to be used by under-18s (Plan B only for an adults-only product) |
| Image-generation models for the handwritten image | Slow (5–20 s), usually paid, and they frequently misdraw equations |
| Preview / experimental model IDs | Can disappear or change without notice; production needs stable IDs |
| Separate OCR service (e.g. Mathpix) | Paid. Vision LLMs read maths photos well enough |
| Running open models on our own server | A free VM has no GPU, so it would be far slower than free APIs |
| Multiple accounts to multiply free quota | Breaks providers' terms and risks a ban on everything |
