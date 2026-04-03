# LeakEngine

Machine-assisted revenue leak detection for businesses burning money on broken funnels.

## What It Does

Crawls business websites, detects broken lead capture, dead forms, bad landing pages,
missing CTAs, and wasted ad spend — then generates visual audit reports you can send
as cold outreach.

## Architecture

```
prospector/     → Find target businesses (Google Ads, directories, niches)
scanner/        → Crawl sites, screenshot pages, test forms, check links
scorer/         → Score severity of leaks, estimate revenue waste
reporter/       → Generate visual audit reports (HTML/PDF)
```

## Quickstart

```bash
pip install -r requirements.txt
playwright install chromium

# Scan a single business
python -m scanner.crawl https://example-business.com

# Generate a full audit
python main.py --url https://example-business.com --output audit.html

# Find prospects in a niche + location
python -m prospector.find --niche "plumber" --location "Austin TX" --limit 20

# Batch audit prospects
python main.py --batch prospects.csv --output-dir audits/
```

## Scoring

Each site gets scored on:
- **Broken forms** — contact/lead forms that don't submit or error out
- **Dead links** — 404s on key pages, especially ad landing pages
- **Missing CTAs** — high-traffic pages with no conversion action
- **No lead capture** — no email capture, no chat widget, no phone number prominent
- **SSL issues** — mixed content, expired certs
- **Mobile broken** — key flows broken on mobile viewport
- **Speed** — pages too slow to convert
- **Ad waste signals** — evidence of paid traffic hitting broken pages
