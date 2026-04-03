# LeakEngine

Automated revenue leak detection engine. Discovers businesses, crawls their sites,
detects broken funnels/forms/CTAs, scores leak severity, and displays everything
in a web dashboard — fully automated.

## How It Works

```
1. DISCOVER  →  Finds businesses via Google CSE, SerpAPI, or directory scraping
2. SCAN      →  Crawls each site, checks forms, CTAs, links, speed, SSL, mobile
3. SCORE     →  Detects leaks, assigns severity, estimates revenue waste
4. DISPLAY   →  Web dashboard with ranked results + downloadable audit reports
5. REPEAT    →  Scheduler runs the pipeline on an interval (default: 24h)
```

## Quickstart

```bash
pip install -r requirements.txt

# Initialize config + directories
python main.py init

# Edit config.yaml to set your target niches and locations
# Then run the full pipeline:
python main.py pipeline

# Start the web dashboard:
python main.py server
# Open http://localhost:5000
```

## Commands

```bash
python main.py init                    # Setup config + directories
python main.py scan --url URL          # Scan a single site
python main.py scan --url URL --quick  # Homepage-only quick scan
python main.py scan --batch FILE.csv   # Batch scan from CSV
python main.py pipeline                # Run full discover → scan → score
python main.py server                  # Start web dashboard
python main.py scheduler               # Run pipeline every 24h
python main.py scheduler --interval 6  # Run pipeline every 6h
```

## Architecture

```
scanner/        → Async site crawler, page analyzer, screenshot capture
scorer/         → Leak detection engine with severity + impact estimation
reporter/       → Standalone HTML audit report generator
prospector/     → Prospect discovery (APIs + directory scraping)
webapp/         → Flask web dashboard
pipeline.py     → Automated orchestrator (discover → scan → score → store)
scheduler.py    → Repeating interval runner
storage.py      → JSON-based persistence
config.py       → YAML config + env var overrides
```

## Configuration

Edit `config.yaml`:

```yaml
prospector:
  niches: ["plumber", "dentist", "hvac", "lawyer"]
  locations: ["Austin TX", "Denver CO", "Phoenix AZ"]
  serpapi_key: ""      # Optional: better discovery
  google_api_key: ""   # Optional: Google Custom Search
  google_cse_id: ""

scan:
  max_pages: 15
  delay_between_scans_seconds: 2.0
```

## What It Detects

- Broken/missing contact forms
- No call-to-action on key pages
- Missing phone numbers
- No email capture
- SSL issues / mixed content
- Slow page load times
- Broken links
- Missing social proof
- No clear pricing/offer
- Weak/missing headlines
- Missing meta descriptions
