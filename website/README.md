# mathfix.ai website

The official website. Plain HTML and CSS with a few lines of JavaScript, so there is no build step.

| File | What it is |
|---|---|
| `index.html` | Home page: hero, the six-step "how it works" walkthrough, solution page, features, topics, free plan, FAQ |
| `assets/logo-mark.png` | The M mark (from `brand/logo-mark.png`, resized for the web) |
| `assets/solution-sample.jpg` | A real solution page drawn by the bot's renderer (`mathfix/render/handwriting.py`) |
| `assets/favicon-32.png`, `assets/apple-touch-icon.png` | Browser and home-screen icons |

Fonts come from Google Fonts: Baloo 2 (headings), Lexend (text) and Kalam (the handwritten notes, the same font
as the solution images). Colours are the brand colours from the logo, with a dark version for phones in dark mode.

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
