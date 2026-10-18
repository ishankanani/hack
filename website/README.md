# mathfix.ai website

The official website. Plain HTML and CSS with a few lines of JavaScript, so there is no build step.

| File | What it is |
|---|---|
| `index.html` | Home page: hero, the six-step "how it works" walkthrough, solution page, features, topics, pricing, FAQ |
| `assets/logo-full.png` | The full MathFix.ai logo for the header and footer (from `brand/logo-full.png`) |
| `assets/logo-mark.png` | The M mark (from `brand/logo-mark.png`, resized for the web) |
| `assets/solution-sample.jpg` | A real solution page drawn by the bot's renderer (`mathfix/render/handwriting.py`) |
| `assets/question-ml.jpg`, `assets/solution-ml.jpg` | A real machine-learning question photo and the solution page the bot drew for it (hero and solution-page deck) |
| `assets/favicon-32.png`, `assets/apple-touch-icon.png` | Browser and home-screen icons |

Design: white background so the logo sits naturally, navy text and the logo's blues as the only accent colour.
Fonts come from Google Fonts: Plus Jakarta Sans (headings and text), Geist Mono (numbers and maths) and Kalam
(only inside the photo of the handwritten question). The site is light-only on purpose.

## Preview on your computer

```
python -m http.server 8080 -d website
```
Then open http://localhost:8080.

## Put it on mathfix.ai (Cloudflare Pages, free)

1. Cloudflare dashboard → **Workers & Pages** → **Create** → **Pages** → **Connect to Git** → choose this repository.
2. Production branch: `main`. Framework preset: **None**. Build command: leave empty.
   Build output directory: `website`.
3. **Custom domains** → add `mathfix.ai` (and `www.mathfix.ai`, redirected to it).

Every push to `main` then updates the site. To publish without Git:
`npx wrangler pages deploy website --project-name mathfix`.

## Still to build

- `/privacy` and `/terms` pages (the bot's /privacy message links to mathfix.ai/privacy)
- A 1200×630 share image for links posted on WhatsApp, Telegram and X
