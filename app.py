"""LeakEngine Web App.

Flask web application that serves the dashboard, prospect list,
audit results, and pipeline controls.
"""

from __future__ import annotations

import asyncio
import os
import threading
from collections import Counter
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for

from config import Config, generate_default_config, load_config
from models import Prospect, Severity
from storage import (
    get_unscanned_prospects,
    load_audits,
    load_pipeline_log,
    load_prospects,
    save_audit,
    save_prospects,
)

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "webapp", "templates"),
)

# Global state for pipeline status
_pipeline_running = False
_pipeline_lock = threading.Lock()


def _get_config() -> Config:
    if not Path("config.yaml").exists():
        generate_default_config()
    return load_config()


@app.context_processor
def inject_common_context() -> dict:
    """Context variables shared across all pages."""
    prospects = load_prospects()
    audits = load_audits()
    return {
        "total_prospects": len(prospects),
        "total_audits": len(audits),
    }


# ── Dashboard ────────────────────────────────────────────────

@app.route("/")
def dashboard():
    prospects = load_prospects()
    audits = load_audits()
    pipeline_log = load_pipeline_log()

    # Stats
    total_leaks = sum(len(a.leaks) for a in audits)
    critical_leaks = sum(
        1 for a in audits for l in a.leaks if l.severity == Severity.CRITICAL
    )
    avg_score = (
        round(sum(a.overall_score for a in audits) / len(audits))
        if audits else 0
    )
    pending = len(get_unscanned_prospects())

    # Top niche
    niche_counts = Counter(p.niche for p in prospects if p.niche)
    top_niche = niche_counts.most_common(1)[0][0] if niche_counts else None

    # Worst audits (best outreach targets)
    worst = sorted(audits, key=lambda a: a.overall_score)[:10]

    return render_template(
        "dashboard.html",
        active_page="dashboard",
        pending_scan=pending,
        critical_leaks=critical_leaks,
        total_leaks=total_leaks,
        avg_score=avg_score,
        pipeline_runs=len(pipeline_log),
        top_niche=top_niche,
        worst_audits=worst,
    )


# ── Prospects ────────────────────────────────────────────────

@app.route("/prospects")
def prospects_page():
    prospects = load_prospects()
    audits = load_audits()

    audited_urls = set()
    for a in audits:
        audited_urls.add(a.url)

    return render_template(
        "prospects.html",
        active_page="prospects",
        prospects=prospects,
        audited_urls=audited_urls,
    )


@app.route("/add-prospect", methods=["POST"])
def add_prospect():
    url = request.form.get("url", "").strip()
    if not url:
        return redirect(url_for("prospects_page"))

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    prospect = Prospect(
        name=request.form.get("name", "").strip(),
        url=url,
        niche=request.form.get("niche", "").strip(),
        location=request.form.get("location", "").strip(),
        source="manual",
    )
    save_prospects([prospect])

    # Auto-scan
    return redirect(url_for("scan_url", url=url))


# ── Audits ───────────────────────────────────────────────────

@app.route("/audits")
def audits_page():
    audits = load_audits()
    sort = request.args.get("sort", "score_asc")

    # Add severity counts to each audit for the template
    for audit in audits:
        audit.critical = sum(1 for l in audit.leaks if l.severity == Severity.CRITICAL)
        audit.high = sum(1 for l in audit.leaks if l.severity == Severity.HIGH)
        audit.medium = sum(1 for l in audit.leaks if l.severity == Severity.MEDIUM)
        audit.low = sum(1 for l in audit.leaks if l.severity == Severity.LOW)

    if sort == "score_asc":
        audits.sort(key=lambda a: a.overall_score)
    elif sort == "score_desc":
        audits.sort(key=lambda a: a.overall_score, reverse=True)
    elif sort == "leaks_desc":
        audits.sort(key=lambda a: len(a.leaks), reverse=True)
    elif sort == "recent":
        audits.sort(key=lambda a: a.scanned_at or "", reverse=True)

    return render_template(
        "audits.html",
        active_page="audits",
        audits=audits,
        sort=sort,
    )


@app.route("/audit/<path:slug>")
def audit_detail(slug):
    audits = load_audits()
    audit = None
    for a in audits:
        a_slug = a.url.replace("https://", "").replace("http://", "").replace("/", "_")
        if a_slug == slug:
            audit = a
            break

    if not audit:
        return "Audit not found", 404

    return render_template(
        "audit_detail.html",
        active_page="audits",
        audit=audit,
        slug=slug,
    )


@app.route("/report/<path:slug>")
def view_report(slug):
    """Serve the generated HTML report for a specific audit."""
    config = _get_config()
    report_path = Path(config.pipeline.reports_dir) / f"{slug}.html"
    if report_path.exists():
        return report_path.read_text()

    # Generate report on the fly
    audits = load_audits()
    for a in audits:
        a_slug = a.url.replace("https://", "").replace("http://", "").replace("/", "_")
        if a_slug == slug:
            from reporter.html_report import save_report
            save_report(a, str(report_path))
            return report_path.read_text()

    return "Report not found", 404


# ── Pipeline ─────────────────────────────────────────────────

@app.route("/pipeline")
def pipeline_page():
    config = _get_config()
    pipeline_log = load_pipeline_log()
    unscanned = get_unscanned_prospects()

    return render_template(
        "pipeline.html",
        active_page="pipeline",
        config=config,
        pipeline_log=pipeline_log,
        is_running=_pipeline_running,
        unscanned_count=len(unscanned),
    )


@app.route("/update-config", methods=["POST"])
def update_config():
    """Update config from the pipeline page form."""
    config = _get_config()

    niches = [n.strip() for n in request.form.get("niches", "").split(",") if n.strip()]
    locations = [l.strip() for l in request.form.get("locations", "").split(",") if l.strip()]

    config.prospector.niches = niches
    config.prospector.locations = locations
    config.scan.max_pages = int(request.form.get("max_pages", 15))
    config.scan.delay_between_scans_seconds = float(request.form.get("delay", 2.0))
    config.prospector.serpapi_key = request.form.get("serpapi_key", "")
    config.prospector.google_cse_id = request.form.get("google_cse_id", "")

    # Save to config.yaml
    import yaml
    data = {
        "smtp": {},
        "scan": {
            "max_pages": config.scan.max_pages,
            "timeout_seconds": config.scan.timeout_seconds,
            "check_external_links": config.scan.check_external_links,
            "capture_screenshots": config.scan.capture_screenshots,
            "concurrent_scans": config.scan.concurrent_scans,
            "delay_between_scans_seconds": config.scan.delay_between_scans_seconds,
        },
        "prospector": {
            "niches": config.prospector.niches,
            "locations": config.prospector.locations,
            "max_prospects_per_search": config.prospector.max_prospects_per_search,
            "google_api_key": config.prospector.google_api_key,
            "google_cse_id": config.prospector.google_cse_id,
            "serpapi_key": config.prospector.serpapi_key,
        },
        "pipeline": {
            "output_dir": config.pipeline.output_dir,
            "reports_dir": config.pipeline.reports_dir,
            "data_dir": config.pipeline.data_dir,
            "screenshots_dir": config.pipeline.screenshots_dir,
            "log_dir": config.pipeline.log_dir,
            "schedule_interval_hours": config.pipeline.schedule_interval_hours,
        },
    }
    with open("config.yaml", "w") as f:
        yaml.dump(data, f, default_flow_style=False)

    return redirect(url_for("pipeline_page"))


# ── Actions ──────────────────────────────────────────────────

def _run_async_in_thread(coro):
    """Run an async coroutine in a background thread."""
    global _pipeline_running
    with _pipeline_lock:
        if _pipeline_running:
            return
        _pipeline_running = True

    def _target():
        global _pipeline_running
        try:
            asyncio.run(coro)
        finally:
            _pipeline_running = False

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()


@app.route("/run-pipeline")
def run_pipeline():
    """Run the full pipeline in background."""
    from pipeline import run_full_pipeline
    config = _get_config()
    _run_async_in_thread(run_full_pipeline(config))
    return redirect(url_for("pipeline_page"))


@app.route("/discover")
def run_discovery():
    """Run discovery only in background."""
    from pipeline import run_discovery as _run_discovery
    config = _get_config()
    _run_async_in_thread(_run_discovery(config))
    return redirect(url_for("prospects_page"))


@app.route("/scan-all")
def scan_all():
    """Scan all unscanned prospects in background."""
    from pipeline import run_scanning
    config = _get_config()
    _run_async_in_thread(run_scanning(config))
    return redirect(url_for("audits_page"))


@app.route("/scan")
def scan_url():
    """Scan a single URL."""
    url = request.args.get("url", "").strip()
    if not url:
        return redirect(url_for("prospects_page"))

    from scanner.crawl import crawl_site
    from scorer.engine import score_site
    from reporter.html_report import save_report
    from datetime import datetime, timezone

    config = _get_config()

    async def _scan():
        pages = await crawl_site(url, max_pages=config.scan.max_pages)
        audit = score_site(pages, url)
        audit.scanned_at = datetime.now(timezone.utc).isoformat()

        # Find business name from prospects
        for p in load_prospects():
            if p.url == url:
                audit.business_name = p.name
                break

        save_audit(audit)

        safe = url.replace("https://", "").replace("http://", "").replace("/", "_").rstrip("_")
        save_report(audit, f"{config.pipeline.reports_dir}/{safe}.html")

    asyncio.run(_scan())

    slug = url.replace("https://", "").replace("http://", "").replace("/", "_")
    return redirect(url_for("audit_detail", slug=slug))


# ── Main ─────────────────────────────────────────────────────

if __name__ == "__main__":
    if not Path("config.yaml").exists():
        generate_default_config()
        print("Generated default config.yaml — edit it to set your niches and locations.")

    os.makedirs("output/reports", exist_ok=True)
    os.makedirs("output/data", exist_ok=True)

    print("\n  LeakEngine Dashboard")
    print("  http://localhost:5000\n")
    app.run(debug=True, host="0.0.0.0", port=5000)
