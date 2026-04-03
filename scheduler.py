"""Scheduler — runs the pipeline on a configurable interval.

Can run standalone or be started alongside the web app.
"""

from __future__ import annotations

import asyncio
import signal
import sys
import time
from datetime import datetime, timezone

from rich.console import Console

from config import load_config
from pipeline import run_full_pipeline

console = Console()

_shutdown = False


def _handle_signal(sig, frame):
    global _shutdown
    console.print("\n[yellow]Shutting down scheduler...[/yellow]")
    _shutdown = True


def run_scheduler(interval_hours: float | None = None):
    """Run the pipeline on a repeating interval.

    Args:
        interval_hours: Hours between runs. Defaults to config value.
    """
    config = load_config()
    interval = interval_hours or config.pipeline.schedule_interval_hours
    interval_seconds = interval * 3600

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    console.print(f"\n[bold]LeakEngine Scheduler[/bold]")
    console.print(f"Interval: every {interval} hours")
    console.print(f"Niches: {', '.join(config.prospector.niches)}")
    console.print(f"Locations: {', '.join(config.prospector.locations)}")
    console.print(f"Press Ctrl+C to stop.\n")

    run_count = 0

    while not _shutdown:
        run_count += 1
        console.print(f"\n[bold blue]═══ Scheduled Run #{run_count} ═══[/bold blue]")
        console.print(f"[dim]{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}[/dim]")

        try:
            # Reload config each run (allows hot-updating config.yaml)
            config = load_config()
            asyncio.run(run_full_pipeline(config))
        except Exception as e:
            console.print(f"[red]Pipeline error: {e}[/red]")

        if _shutdown:
            break

        next_run = datetime.now(timezone.utc).timestamp() + interval_seconds
        next_run_str = datetime.fromtimestamp(next_run, tz=timezone.utc).strftime("%H:%M UTC")
        console.print(f"\n[dim]Next run at {next_run_str} (in {interval}h). Sleeping...[/dim]")

        # Sleep in small increments so we can catch shutdown signals
        sleep_until = time.monotonic() + interval_seconds
        while time.monotonic() < sleep_until and not _shutdown:
            time.sleep(min(10, sleep_until - time.monotonic()))

    console.print("[bold]Scheduler stopped.[/bold]")


if __name__ == "__main__":
    interval = float(sys.argv[1]) if len(sys.argv) > 1 else None
    run_scheduler(interval)
