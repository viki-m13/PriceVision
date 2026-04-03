"""Automated pipeline: discover -> scan -> score -> store.

Runs the full cycle automatically. Can be triggered manually
or scheduled to run on an interval.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from rich.console import Console

from config import Config, load_config
from models import Prospect, SiteAudit
from prospector.discovery import discover_prospects
from scanner.crawl import crawl_site
from scorer.engine import score_site
from reporter.html_report import save_report
from storage import (
    get_unscanned_prospects,
    load_audits,
    load_prospects,
    log_pipeline_run,
    save_audit,
    save_prospects,
)

console = Console()


async def run_discovery(config: Config) -> list[Prospect]:
    """Phase 1: Discover prospects for all configured niches + locations."""
    all_prospects: list[Prospect] = []

    niches = config.prospector.niches or ["plumber"]
    locations = config.prospector.locations or ["Austin TX"]

    for niche in niches:
        for location in locations:
            console.print(f"[bold blue]Discovering:[/bold blue] {niche} in {location}")
            try:
                prospects = await discover_prospects(
                    niche=niche,
                    location=location,
                    google_api_key=config.prospector.google_api_key,
                    google_cse_id=config.prospector.google_cse_id,
                    serpapi_key=config.prospector.serpapi_key,
                    max_per_source=config.prospector.max_prospects_per_search,
                )
                console.print(f"  Found {len(prospects)} prospects")
                all_prospects.extend(prospects)
            except Exception as e:
                console.print(f"  [red]Error: {e}[/red]")

            await asyncio.sleep(1)  # Be polite between searches

    # Save discovered prospects
    save_prospects(all_prospects)
    console.print(f"\n[bold green]Total prospects saved:[/bold green] {len(all_prospects)}")
    return all_prospects


async def run_scanning(config: Config) -> list[SiteAudit]:
    """Phase 2: Scan unscanned prospects and generate audits."""
    unscanned = get_unscanned_prospects()
    if not unscanned:
        console.print("[yellow]No unscanned prospects. Run discovery first or add prospects.[/yellow]")
        return []

    console.print(f"\n[bold blue]Scanning:[/bold blue] {len(unscanned)} unscanned prospects")

    audits: list[SiteAudit] = []
    errors: list[str] = []

    for i, prospect in enumerate(unscanned, 1):
        console.print(f"\n[bold][{i}/{len(unscanned)}][/bold] {prospect.name or prospect.url}")

        try:
            pages = await crawl_site(
                prospect.url,
                max_pages=config.scan.max_pages,
                check_external_links=config.scan.check_external_links,
            )

            audit = score_site(pages, prospect.url)
            audit.business_name = prospect.name
            audit.scanned_at = datetime.now(timezone.utc).isoformat()

            # Save audit
            save_audit(audit)

            # Generate HTML report
            safe_name = prospect.url.replace("https://", "").replace("http://", "").replace("/", "_").rstrip("_")
            if len(safe_name) > 80:
                safe_name = safe_name[:80]
            report_dir = config.pipeline.reports_dir
            report_path = f"{report_dir}/{safe_name}.html"
            save_report(audit, report_path)

            console.print(f"  Score: {audit.overall_score}/100 | Leaks: {len(audit.leaks)} | Waste: {audit.estimated_monthly_waste}")
            audits.append(audit)

        except Exception as e:
            error_msg = f"Error scanning {prospect.url}: {e}"
            console.print(f"  [red]{error_msg}[/red]")
            errors.append(error_msg)

        # Delay between scans
        await asyncio.sleep(config.scan.delay_between_scans_seconds)

    return audits


async def run_full_pipeline(config: Config | None = None) -> None:
    """Run the complete pipeline: discover -> scan -> score -> store."""
    if config is None:
        config = load_config()

    start = time.monotonic()
    console.print("\n[bold]═══ LeakEngine Pipeline Starting ═══[/bold]")
    console.print(f"[dim]{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}[/dim]\n")

    # Phase 1: Discovery
    console.print("[bold]Phase 1: Discovery[/bold]")
    prospects = await run_discovery(config)

    # Phase 2: Scanning & Scoring
    console.print("\n[bold]Phase 2: Scanning & Scoring[/bold]")
    audits = await run_scanning(config)

    # Summary
    elapsed = time.monotonic() - start
    console.print(f"\n[bold]═══ Pipeline Complete ═══[/bold]")
    console.print(f"Prospects found: {len(prospects)}")
    console.print(f"Audits completed: {len(audits)}")
    console.print(f"Time: {elapsed:.1f}s")

    # Log the run
    log_pipeline_run(
        niches_searched=config.prospector.niches,
        locations_searched=config.prospector.locations,
        prospects_found=len(prospects),
        audits_completed=len(audits),
        errors=[],
    )

    console.print("\n[bold green]Dashboard:[/bold green] python app.py  (then open http://localhost:5000)")


if __name__ == "__main__":
    asyncio.run(run_full_pipeline())
