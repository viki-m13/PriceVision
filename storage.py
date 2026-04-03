"""Simple JSON-based storage for prospects and audit results.

No database needed — stores everything in JSON files on disk.
Fast enough for thousands of prospects.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from models import Leak, LeakType, PageResult, Prospect, Severity, SiteAudit


DATA_DIR = Path(os.environ.get("LEAKENGINE_DATA_DIR", "output/data"))


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _prospects_path() -> Path:
    return DATA_DIR / "prospects.json"


def _audits_path() -> Path:
    return DATA_DIR / "audits.json"


def _pipeline_log_path() -> Path:
    return DATA_DIR / "pipeline_log.json"


# ── Prospects ────────────────────────────────────────────────

def save_prospects(prospects: list[Prospect]) -> None:
    """Save prospects to disk, merging with existing ones (dedup by domain)."""
    _ensure_dirs()
    existing = load_prospects()

    # Dedup by domain
    seen = set()
    merged = []
    for p in existing + prospects:
        domain = p.url.split("//")[-1].split("/")[0].lower().replace("www.", "")
        if domain not in seen:
            seen.add(domain)
            merged.append(p)

    data = [asdict(p) for p in merged]
    with open(_prospects_path(), "w") as f:
        json.dump(data, f, indent=2)


def load_prospects() -> list[Prospect]:
    """Load all stored prospects."""
    path = _prospects_path()
    if not path.exists():
        return []
    with open(path) as f:
        data = json.load(f)
    return [Prospect(**item) for item in data]


def get_unscanned_prospects() -> list[Prospect]:
    """Get prospects that haven't been audited yet."""
    prospects = load_prospects()
    audits = load_audits()
    audited_domains = set()
    for a in audits:
        domain = a.url.split("//")[-1].split("/")[0].lower().replace("www.", "")
        audited_domains.add(domain)

    return [
        p for p in prospects
        if p.url.split("//")[-1].split("/")[0].lower().replace("www.", "") not in audited_domains
    ]


# ── Audits ───────────────────────────────────────────────────

def save_audit(audit: SiteAudit) -> None:
    """Save an audit result, appending to existing audits."""
    _ensure_dirs()
    audits = load_audits()

    # Replace existing audit for same domain, or append
    domain = audit.url.split("//")[-1].split("/")[0].lower().replace("www.", "")
    audits = [a for a in audits if a.url.split("//")[-1].split("/")[0].lower().replace("www.", "") != domain]
    audits.append(audit)

    data = [_audit_to_dict(a) for a in audits]
    with open(_audits_path(), "w") as f:
        json.dump(data, f, indent=2, default=str)


def load_audits() -> list[SiteAudit]:
    """Load all stored audits."""
    path = _audits_path()
    if not path.exists():
        return []
    with open(path) as f:
        data = json.load(f)
    return [_dict_to_audit(item) for item in data]


def _audit_to_dict(audit: SiteAudit) -> dict:
    """Convert a SiteAudit to a JSON-serializable dict."""
    return {
        "url": audit.url,
        "business_name": audit.business_name,
        "overall_score": audit.overall_score,
        "estimated_monthly_waste": audit.estimated_monthly_waste,
        "scan_duration_seconds": audit.scan_duration_seconds,
        "scanned_at": audit.scanned_at,
        "pages_scanned": [asdict(p) for p in audit.pages_scanned],
        "leaks": [
            {
                "leak_type": l.leak_type.value,
                "severity": l.severity.value,
                "page_url": l.page_url,
                "description": l.description,
                "recommendation": l.recommendation,
                "estimated_monthly_impact": l.estimated_monthly_impact,
                "screenshot_path": l.screenshot_path,
                "evidence": l.evidence,
            }
            for l in audit.leaks
        ],
    }


def _dict_to_audit(data: dict) -> SiteAudit:
    """Convert a dict back to a SiteAudit."""
    pages = [PageResult(**p) for p in data.get("pages_scanned", [])]
    leaks = [
        Leak(
            leak_type=LeakType(l["leak_type"]),
            severity=Severity(l["severity"]),
            page_url=l["page_url"],
            description=l["description"],
            recommendation=l["recommendation"],
            estimated_monthly_impact=l.get("estimated_monthly_impact", ""),
            screenshot_path=l.get("screenshot_path", ""),
            evidence=l.get("evidence", ""),
        )
        for l in data.get("leaks", [])
    ]
    return SiteAudit(
        url=data["url"],
        business_name=data.get("business_name", ""),
        pages_scanned=pages,
        leaks=leaks,
        overall_score=data.get("overall_score", 0),
        estimated_monthly_waste=data.get("estimated_monthly_waste", ""),
        scan_duration_seconds=data.get("scan_duration_seconds", 0),
        scanned_at=data.get("scanned_at", ""),
    )


# ── Pipeline Log ─────────────────────────────────────────────

def log_pipeline_run(
    niches_searched: list[str],
    locations_searched: list[str],
    prospects_found: int,
    audits_completed: int,
    errors: list[str],
) -> None:
    """Log a pipeline run for tracking."""
    _ensure_dirs()
    log = load_pipeline_log()
    log.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "niches": niches_searched,
        "locations": locations_searched,
        "prospects_found": prospects_found,
        "audits_completed": audits_completed,
        "errors": errors,
    })
    with open(_pipeline_log_path(), "w") as f:
        json.dump(log, f, indent=2)


def load_pipeline_log() -> list[dict]:
    """Load the pipeline run log."""
    path = _pipeline_log_path()
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)
