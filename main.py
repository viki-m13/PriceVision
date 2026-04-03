"""LeakEngine — Revenue leak detection for businesses.

Usage:
    python main.py --url https://example-business.com
    python main.py --url https://example.com --output report.html
    python main.py --batch prospects.csv --output-dir audits/
    python main.py --url https://example.com --quick
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
from scorer.engine import score_page, score_site
from reporter.html_report import save_report
from prospector.find import load_prospects_from_csv

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

    # Score
    audit = score_site(pages, url)
    audit.scan_duration_seconds = time.monotonic() - start
    audit.scanned_at = datetime.now(timezone.utc).isoformat()

    # Screenshots
    if screenshots:
        try:
            from scanner.screenshot import capture_screenshots
            console.print("[dim]Capturing screenshots...[/dim]")
            shots = await capture_screenshots(url)
            for name, path in shots.items():
                console.print(f"  [dim]Screenshot: {path}[/dim]")
        except ImportError:
            console.print("[yellow]Playwright not installed — skipping screenshots[/yellow]")

    # Display results
    _print_results(audit)

    # Save report
    if output:
        report_path = save_report(audit, output)
        console.print(f"\n[bold green]Report saved:[/bold green] {report_path}")

    return audit


def _print_results(audit: SiteAudit) -> None:
    """Print audit results to terminal."""
    # Score
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

    # Leaks table
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

    # Sort by severity
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


async def batch_audit(
    csv_path: str,
    output_dir: str = "audits",
    max_pages: int = 10,
    quick: bool = False,
) -> list[SiteAudit]:
    """Run audits on all prospects in a CSV."""
    prospects = load_prospects_from_csv(csv_path)
    console.print(f"\n[bold]Batch audit:[/bold] {len(prospects)} prospects from {csv_path}")

    os.makedirs(output_dir, exist_ok=True)
    audits = []

    for i, prospect in enumerate(prospects, 1):
        console.print(f"\n[bold]--- [{i}/{len(prospects)}] {prospect.name or prospect.url} ---[/bold]")

        safe_name = prospect.url.replace("https://", "").replace("http://", "").replace("/", "_").rstrip("_")
        output_path = os.path.join(output_dir, f"{safe_name}.html")

        try:
            audit = await audit_url(
                prospect.url,
                max_pages=max_pages,
                quick=quick,
                output=output_path,
            )
            audit.business_name = prospect.name
            audits.append(audit)
        except Exception as e:
            console.print(f"[red]Error scanning {prospect.url}: {e}[/red]")

    # Summary
    console.print(f"\n\n[bold]{'='*60}[/bold]")
    console.print(f"[bold]Batch complete:[/bold] {len(audits)}/{len(prospects)} scanned")
    console.print(f"[bold]Reports saved to:[/bold] {output_dir}/")

    # Summary table
    table = Table(title="Batch Results Summary")
    table.add_column("Business", width=30)
    table.add_column("Score", width=8, justify="center")
    table.add_column("Leaks", width=8, justify="center")
    table.add_column("Est. Waste", width=25)

    for audit in sorted(audits, key=lambda a: a.overall_score):
        score = audit.overall_score
        if score < 40:
            style = "red"
        elif score < 70:
            style = "yellow"
        else:
            style = "green"

        table.add_row(
            audit.business_name or audit.url,
            f"[{style}]{score}[/{style}]",
            str(len(audit.leaks)),
            audit.estimated_monthly_waste,
        )

    console.print(table)

    return audits


@click.command()
@click.option("--url", help="Single URL to audit")
@click.option("--batch", "batch_csv", help="CSV file of prospects to batch audit")
@click.option("--output", "-o", help="Output file path (for single URL)")
@click.option("--output-dir", default="audits", help="Output directory (for batch)")
@click.option("--max-pages", default=15, help="Max pages to crawl per site")
@click.option("--quick", is_flag=True, help="Quick scan (homepage only)")
@click.option("--screenshots", is_flag=True, help="Capture screenshots (requires playwright)")
def main(
    url: str | None,
    batch_csv: str | None,
    output: str | None,
    output_dir: str,
    max_pages: int,
    quick: bool,
    screenshots: bool,
) -> None:
    """LeakEngine — Find revenue leaks in business websites."""
    if not url and not batch_csv:
        console.print("[red]Provide --url or --batch[/red]")
        console.print("Example: python main.py --url https://example.com")
        sys.exit(1)

    if batch_csv:
        asyncio.run(batch_audit(batch_csv, output_dir, max_pages, quick))
    else:
        if not output:
            safe = url.replace("https://", "").replace("http://", "").replace("/", "_").rstrip("_")
            output = f"audit_{safe}.html"
        asyncio.run(audit_url(url, max_pages, quick, screenshots, output))


if __name__ == "__main__":
    main()
