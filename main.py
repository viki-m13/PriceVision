"""LeakEngine — Revenue leak detection for businesses.

Usage:
    python main.py scan --url https://example-business.com
    python main.py scan --url https://example.com --quick
    python main.py scan --batch prospects.csv
    python main.py pipeline              # Run full pipeline once
    python main.py server                # Start web dashboard
    python main.py scheduler             # Run pipeline on interval
    python main.py scheduler --interval 6  # Every 6 hours
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import datetime, timezone

import click
from rich.console import Console
from rich.table import Table

from models import Severity, SiteAudit
from scanner.crawl import crawl_site, quick_scan
from scorer.engine import score_site
from reporter.html_report import save_report
from prospector.find import load_prospects_from_csv
from storage import save_audit

console = Console()


async def audit_url(
    url: str,
    max_pages: int = 20,
    quick: bool = False,
    screenshots: bool = False,
    output: str | None = None,
) -> SiteAudit:
    """Run a full audit on a URL."""
    console.print(f"\n[bold]Scanning:[/bold] {url}")

    start = time.monotonic()

    if quick:
        console.print("[dim]Quick scan (homepage only)...[/dim]")
        page = await quick_scan(url)
        pages = [page]
    else:
        console.print(f"[dim]Crawling up to {max_pages} pages...[/dim]")
        pages = await crawl_site(url, max_pages=max_pages)

    console.print(f"[dim]Scanned {len(pages)} page(s). Scoring...[/dim]")

    audit = score_site(pages, url)
    audit.scan_duration_seconds = time.monotonic() - start
    audit.scanned_at = datetime.now(timezone.utc).isoformat()

    if screenshots:
        try:
            from scanner.screenshot import capture_screenshots
            console.print("[dim]Capturing screenshots...[/dim]")
            await capture_screenshots(url)
        except ImportError:
            console.print("[yellow]Playwright not installed — skipping screenshots[/yellow]")

    _print_results(audit)

    if output:
        report_path = save_report(audit, output)
        console.print(f"\n[bold green]Report saved:[/bold green] {report_path}")

    # Also save to storage for the web dashboard
    save_audit(audit)

    return audit


def _print_results(audit: SiteAudit) -> None:
    """Print audit results to terminal."""
    score = audit.overall_score
    if score < 40:
        score_style = "bold red"
    elif score < 70:
        score_style = "bold yellow"
    else:
        score_style = "bold green"

    console.print(f"\n[{score_style}]Health Score: {score}/100[/{score_style}]")
    console.print(f"[bold]Estimated waste:[/bold] {audit.estimated_monthly_waste}")
    console.print(f"[dim]Scan took {audit.scan_duration_seconds:.1f}s[/dim]\n")

    if not audit.leaks:
        console.print("[green]No significant leaks detected.[/green]")
        return

    table = Table(title=f"Revenue Leaks ({len(audit.leaks)} found)")
    table.add_column("Severity", style="bold", width=10)
    table.add_column("Type", width=20)
    table.add_column("Description", width=50)

    severity_colors = {
        Severity.CRITICAL: "red",
        Severity.HIGH: "dark_orange",
        Severity.MEDIUM: "yellow",
        Severity.LOW: "blue",
        Severity.INFO: "dim",
    }

    severity_order = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]
    sorted_leaks = sorted(audit.leaks, key=lambda l: severity_order.index(l.severity))

    for leak in sorted_leaks:
        color = severity_colors.get(leak.severity, "white")
        table.add_row(
            f"[{color}]{leak.severity.value.upper()}[/{color}]",
            leak.leak_type.value.replace("_", " ").title(),
            leak.description[:80],
        )

    console.print(table)


# ── CLI ──────────────────────────────────────────────────────

@click.group()
def cli():
    """LeakEngine — Find and exploit revenue leaks in business websites."""
    pass


@cli.command()
@click.option("--url", help="Single URL to audit")
@click.option("--batch", "batch_csv", help="CSV file of prospects to batch audit")
@click.option("--output", "-o", help="Output file path")
@click.option("--output-dir", default="output/reports", help="Output directory (for batch)")
@click.option("--max-pages", default=15, help="Max pages to crawl per site")
@click.option("--quick", is_flag=True, help="Quick scan (homepage only)")
@click.option("--screenshots", is_flag=True, help="Capture screenshots")
def scan(url, batch_csv, output, output_dir, max_pages, quick, screenshots):
    """Scan a URL or batch of URLs for revenue leaks."""
    if not url and not batch_csv:
        console.print("[red]Provide --url or --batch[/red]")
        sys.exit(1)

    if batch_csv:
        prospects = load_prospects_from_csv(batch_csv)
        console.print(f"\n[bold]Batch audit:[/bold] {len(prospects)} prospects")
        os.makedirs(output_dir, exist_ok=True)

        for i, prospect in enumerate(prospects, 1):
            console.print(f"\n[bold]--- [{i}/{len(prospects)}] {prospect.name or prospect.url} ---[/bold]")
            safe = prospect.url.replace("https://", "").replace("http://", "").replace("/", "_").rstrip("_")
            out_path = os.path.join(output_dir, f"{safe}.html")
            try:
                asyncio.run(audit_url(prospect.url, max_pages, quick, screenshots, out_path))
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
    else:
        if not output:
            safe = url.replace("https://", "").replace("http://", "").replace("/", "_").rstrip("_")
            output = f"audit_{safe}.html"
        asyncio.run(audit_url(url, max_pages, quick, screenshots, output))


@cli.command()
def pipeline():
    """Run the full automated pipeline (discover -> scan -> score -> store)."""
    from pipeline import run_full_pipeline
    asyncio.run(run_full_pipeline())


@cli.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=5000, help="Port to bind to")
def server(host, port):
    """Start the web dashboard."""
    from config import generate_default_config
    from pathlib import Path

    if not Path("config.yaml").exists():
        generate_default_config()
        console.print("[yellow]Generated default config.yaml — edit it to configure niches and locations.[/yellow]")

    os.makedirs("output/reports", exist_ok=True)
    os.makedirs("output/data", exist_ok=True)

    console.print(f"\n[bold green]LeakEngine Dashboard[/bold green]")
    console.print(f"http://{host}:{port}\n")

    from app import app
    app.run(debug=True, host=host, port=port)


@cli.command()
@click.option("--interval", default=24.0, help="Hours between pipeline runs")
def scheduler(interval):
    """Run the pipeline on a repeating schedule."""
    from scheduler import run_scheduler
    run_scheduler(interval)


@cli.command()
def init():
    """Initialize config and output directories."""
    from config import generate_default_config
    from pathlib import Path

    if not Path("config.yaml").exists():
        generate_default_config()
        console.print("[green]Created config.yaml[/green]")
    else:
        console.print("[yellow]config.yaml already exists[/yellow]")

    for d in ["output/reports", "output/data", "output/screenshots", "output/logs"]:
        os.makedirs(d, exist_ok=True)
    console.print("[green]Created output directories[/green]")
    console.print("\n[bold]Next steps:[/bold]")
    console.print("  1. Edit config.yaml to set your target niches and locations")
    console.print("  2. Run: python main.py pipeline")
    console.print("  3. Run: python main.py server")
    console.print("  4. Open: http://localhost:5000")


if __name__ == "__main__":
    cli()
