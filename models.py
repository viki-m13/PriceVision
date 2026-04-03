"""Core data models for LeakEngine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class LeakType(str, Enum):
    BROKEN_FORM = "broken_form"
    DEAD_LINK = "dead_link"
    MISSING_CTA = "missing_cta"
    NO_LEAD_CAPTURE = "no_lead_capture"
    SSL_ISSUE = "ssl_issue"
    MOBILE_BROKEN = "mobile_broken"
    SLOW_PAGE = "slow_page"
    NO_PHONE = "no_phone"
    NO_EMAIL_CAPTURE = "no_email_capture"
    BROKEN_CHAT_WIDGET = "broken_chat_widget"
    AD_WASTE = "ad_waste"
    MISSING_META = "missing_meta"
    NO_SOCIAL_PROOF = "no_social_proof"
    WEAK_HEADLINE = "weak_headline"
    NO_CLEAR_OFFER = "no_clear_offer"


@dataclass
class PageResult:
    """Result of scanning a single page."""

    url: str
    status_code: int | None = None
    title: str = ""
    load_time_ms: float = 0
    screenshot_path: str = ""
    has_forms: bool = False
    forms_working: bool | None = None
    form_count: int = 0
    has_cta: bool = False
    has_phone: bool = False
    has_email_capture: bool = False
    has_chat_widget: bool = False
    has_social_proof: bool = False
    has_clear_offer: bool = False
    has_ssl: bool = False
    mixed_content: bool = False
    mobile_friendly: bool = True
    broken_links: list[str] = field(default_factory=list)
    broken_images: list[str] = field(default_factory=list)
    meta_description: str = ""
    h1_text: str = ""
    word_count: int = 0
    external_scripts: list[str] = field(default_factory=list)


@dataclass
class Leak:
    """A detected revenue leak."""

    leak_type: LeakType
    severity: Severity
    page_url: str
    description: str
    recommendation: str
    estimated_monthly_impact: str = ""
    screenshot_path: str = ""
    evidence: str = ""


@dataclass
class SiteAudit:
    """Complete audit of a business website."""

    url: str
    business_name: str = ""
    pages_scanned: list[PageResult] = field(default_factory=list)
    leaks: list[Leak] = field(default_factory=list)
    overall_score: int = 0  # 0-100, 100 = no leaks
    estimated_monthly_waste: str = ""
    scan_duration_seconds: float = 0
    scanned_at: str = ""


@dataclass
class Prospect:
    """A business prospect to audit."""

    name: str
    url: str
    niche: str = ""
    location: str = ""
    has_ads: bool = False
    source: str = ""
