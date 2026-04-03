"""Configuration management for LeakEngine.

Loads settings from config.yaml or environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


CONFIG_PATH = Path("config.yaml")


@dataclass
class SmtpConfig:
    host: str = ""
    port: int = 587
    username: str = ""
    password: str = ""
    from_email: str = ""
    from_name: str = "LeakEngine"
    use_tls: bool = True


@dataclass
class ScanConfig:
    max_pages: int = 15
    timeout_seconds: int = 15
    check_external_links: bool = True
    capture_screenshots: bool = False
    concurrent_scans: int = 3
    delay_between_scans_seconds: float = 2.0


@dataclass
class ProspectorConfig:
    niches: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    max_prospects_per_search: int = 20
    google_api_key: str = ""
    google_cse_id: str = ""
    serpapi_key: str = ""


@dataclass
class OutreachConfig:
    enabled: bool = False
    dry_run: bool = True  # Print emails instead of sending
    delay_between_emails_seconds: float = 30.0
    max_emails_per_run: int = 10
    subject_template: str = "I found {leak_count} issues costing your business money"
    follow_up_days: int = 3


@dataclass
class PipelineConfig:
    output_dir: str = "output"
    reports_dir: str = "output/reports"
    data_dir: str = "output/data"
    screenshots_dir: str = "output/screenshots"
    log_dir: str = "output/logs"
    schedule_interval_hours: float = 24.0


@dataclass
class Config:
    smtp: SmtpConfig = field(default_factory=SmtpConfig)
    scan: ScanConfig = field(default_factory=ScanConfig)
    prospector: ProspectorConfig = field(default_factory=ProspectorConfig)
    outreach: OutreachConfig = field(default_factory=OutreachConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)


def load_config(path: str | Path = CONFIG_PATH) -> Config:
    """Load config from YAML file, with env var overrides."""
    config = Config()
    path = Path(path)

    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}

        # SMTP
        smtp = data.get("smtp", {})
        config.smtp = SmtpConfig(
            host=smtp.get("host", ""),
            port=smtp.get("port", 587),
            username=smtp.get("username", ""),
            password=smtp.get("password", ""),
            from_email=smtp.get("from_email", ""),
            from_name=smtp.get("from_name", "LeakEngine"),
            use_tls=smtp.get("use_tls", True),
        )

        # Scan
        scan = data.get("scan", {})
        config.scan = ScanConfig(
            max_pages=scan.get("max_pages", 15),
            timeout_seconds=scan.get("timeout_seconds", 15),
            check_external_links=scan.get("check_external_links", True),
            capture_screenshots=scan.get("capture_screenshots", False),
            concurrent_scans=scan.get("concurrent_scans", 3),
            delay_between_scans_seconds=scan.get("delay_between_scans_seconds", 2.0),
        )

        # Prospector
        prosp = data.get("prospector", {})
        config.prospector = ProspectorConfig(
            niches=prosp.get("niches", []),
            locations=prosp.get("locations", []),
            max_prospects_per_search=prosp.get("max_prospects_per_search", 20),
            google_api_key=prosp.get("google_api_key", ""),
            google_cse_id=prosp.get("google_cse_id", ""),
            serpapi_key=prosp.get("serpapi_key", ""),
        )

        # Outreach
        out = data.get("outreach", {})
        config.outreach = OutreachConfig(
            enabled=out.get("enabled", False),
            dry_run=out.get("dry_run", True),
            delay_between_emails_seconds=out.get("delay_between_emails_seconds", 30.0),
            max_emails_per_run=out.get("max_emails_per_run", 10),
            subject_template=out.get("subject_template", config.outreach.subject_template),
            follow_up_days=out.get("follow_up_days", 3),
        )

        # Pipeline
        pipe = data.get("pipeline", {})
        config.pipeline = PipelineConfig(
            output_dir=pipe.get("output_dir", "output"),
            reports_dir=pipe.get("reports_dir", "output/reports"),
            data_dir=pipe.get("data_dir", "output/data"),
            screenshots_dir=pipe.get("screenshots_dir", "output/screenshots"),
            log_dir=pipe.get("log_dir", "output/logs"),
            schedule_interval_hours=pipe.get("schedule_interval_hours", 24.0),
        )

    # Environment variable overrides
    config.smtp.host = os.getenv("SMTP_HOST", config.smtp.host)
    config.smtp.port = int(os.getenv("SMTP_PORT", str(config.smtp.port)))
    config.smtp.username = os.getenv("SMTP_USERNAME", config.smtp.username)
    config.smtp.password = os.getenv("SMTP_PASSWORD", config.smtp.password)
    config.smtp.from_email = os.getenv("SMTP_FROM_EMAIL", config.smtp.from_email)
    config.prospector.google_api_key = os.getenv("GOOGLE_API_KEY", config.prospector.google_api_key)
    config.prospector.google_cse_id = os.getenv("GOOGLE_CSE_ID", config.prospector.google_cse_id)
    config.prospector.serpapi_key = os.getenv("SERPAPI_KEY", config.prospector.serpapi_key)

    return config


def generate_default_config(path: str | Path = CONFIG_PATH) -> None:
    """Generate a default config.yaml file."""
    default = """\
# LeakEngine Configuration
# ========================

# SMTP settings for sending outreach emails
smtp:
  host: "smtp.gmail.com"
  port: 587
  username: ""           # Your email
  password: ""           # App password (not your real password)
  from_email: ""
  from_name: "LeakEngine"
  use_tls: true

# Scanner settings
scan:
  max_pages: 15
  timeout_seconds: 15
  check_external_links: true
  capture_screenshots: false
  concurrent_scans: 3
  delay_between_scans_seconds: 2.0

# Prospect discovery settings
prospector:
  niches:
    - "plumber"
    - "dentist"
    - "hvac"
    - "roofing"
    - "lawyer"
  locations:
    - "Austin TX"
    - "Denver CO"
    - "Phoenix AZ"
  max_prospects_per_search: 20
  # Google Custom Search API (free tier: 100 queries/day)
  google_api_key: ""
  google_cse_id: ""
  # Or use SerpAPI
  serpapi_key: ""

# Outreach settings
outreach:
  enabled: false
  dry_run: true          # Set to false to actually send emails
  delay_between_emails_seconds: 30
  max_emails_per_run: 10
  subject_template: "I found {leak_count} issues costing your business money"
  follow_up_days: 3

# Pipeline settings
pipeline:
  output_dir: "output"
  reports_dir: "output/reports"
  data_dir: "output/data"
  screenshots_dir: "output/screenshots"
  log_dir: "output/logs"
  schedule_interval_hours: 24
"""
    with open(path, "w") as f:
        f.write(default)
