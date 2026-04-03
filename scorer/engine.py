"""Scoring engine — converts raw page data into actionable leak reports.

Each leak gets a severity, description, recommendation, and estimated monthly impact.
"""

from __future__ import annotations

from models import Leak, LeakType, PageResult, Severity, SiteAudit


def _is_key_page(url: str) -> bool:
    """Check if a URL is likely a key conversion page."""
    key_slugs = [
        "contact", "quote", "pricing", "book", "schedule", "demo",
        "signup", "sign-up", "register", "get-started", "free-trial",
        "appointment", "consultation", "estimate", "call", "landing",
    ]
    lower = url.lower()
    return any(slug in lower for slug in key_slugs) or url.rstrip("/").count("/") <= 3


def score_page(page: PageResult) -> list[Leak]:
    """Analyze a single page and return detected leaks."""
    leaks: list[Leak] = []
    is_key = _is_key_page(page.url)

    # 1. Page is down or erroring
    if page.status_code and page.status_code >= 400:
        severity = Severity.CRITICAL if is_key else Severity.HIGH
        leaks.append(Leak(
            leak_type=LeakType.DEAD_LINK,
            severity=severity,
            page_url=page.url,
            description=f"Page returns HTTP {page.status_code}. Visitors hitting this page bounce immediately.",
            recommendation="Fix or redirect this URL. If this is a landing page for ads, you are burning ad spend on a dead page.",
            estimated_monthly_impact="$200-2,000+ if receiving ad traffic",
            evidence=f"HTTP status {page.status_code}",
        ))
        return leaks  # No point analyzing further

    # 2. Slow page
    if page.load_time_ms > 4000:
        leaks.append(Leak(
            leak_type=LeakType.SLOW_PAGE,
            severity=Severity.HIGH if is_key else Severity.MEDIUM,
            page_url=page.url,
            description=f"Page takes {page.load_time_ms/1000:.1f}s to load. Every second above 3s drops conversion by ~7%.",
            recommendation="Optimize images, enable caching, reduce scripts. Consider a CDN.",
            estimated_monthly_impact="10-20% conversion loss on this page",
            evidence=f"Load time: {page.load_time_ms:.0f}ms",
        ))
    elif page.load_time_ms > 2500:
        leaks.append(Leak(
            leak_type=LeakType.SLOW_PAGE,
            severity=Severity.LOW,
            page_url=page.url,
            description=f"Page takes {page.load_time_ms/1000:.1f}s to load. Slightly above optimal.",
            recommendation="Minor optimization could help — compress images, lazy-load below-fold content.",
            estimated_monthly_impact="5-10% conversion impact",
            evidence=f"Load time: {page.load_time_ms:.0f}ms",
        ))

    # 3. No forms on key pages
    if is_key and not page.has_forms and page.status_code == 200:
        # If the page has CTAs and phone numbers, it likely uses JS-rendered forms
        # (Calendly, HubSpot, ServiceTitan, etc.) — downgrade severity
        if page.has_cta and page.has_phone:
            leaks.append(Leak(
                leak_type=LeakType.NO_LEAD_CAPTURE,
                severity=Severity.LOW,
                page_url=page.url,
                description="No HTML form detected (may use JavaScript-rendered forms). Verify forms work for visitors with JS disabled or slow connections.",
                recommendation="Ensure your lead capture form works reliably. Consider adding a simple HTML fallback form.",
                estimated_monthly_impact="Potential lost leads from slow/no-JS visitors",
            ))
        elif page.has_cta or page.has_phone:
            leaks.append(Leak(
                leak_type=LeakType.BROKEN_FORM,
                severity=Severity.MEDIUM,
                page_url=page.url,
                description="Key page has CTAs but no detectable lead capture form. Visitors may not be able to convert online.",
                recommendation="Add a lead capture form above the fold — name, email, phone at minimum.",
                estimated_monthly_impact="$300-2,000/mo in missed online leads",
            ))
        else:
            leaks.append(Leak(
                leak_type=LeakType.BROKEN_FORM,
                severity=Severity.CRITICAL,
                page_url=page.url,
                description="This key page has no contact form, no CTA, and no phone number. Visitors with intent have no way to convert.",
                recommendation="Add a lead capture form above the fold. Even a simple name + email + phone form will capture leads.",
                estimated_monthly_impact="$500-5,000+ in lost leads depending on traffic",
            ))

    # 5. No CTA on homepage or key pages
    if is_key and not page.has_cta and page.status_code == 200:
        leaks.append(Leak(
            leak_type=LeakType.MISSING_CTA,
            severity=Severity.HIGH,
            page_url=page.url,
            description="No clear call-to-action found. Visitors don't know what to do next.",
            recommendation='Add a prominent CTA button: "Get a Free Quote", "Book Now", "Schedule a Call", etc.',
            estimated_monthly_impact="20-40% fewer conversions on this page",
        ))

    # 6. No phone number visible
    if is_key and not page.has_phone:
        leaks.append(Leak(
            leak_type=LeakType.NO_PHONE,
            severity=Severity.MEDIUM,
            page_url=page.url,
            description="No phone number visible on this page. Many customers prefer to call, especially for local services.",
            recommendation="Add a clickable phone number in the header and near CTAs.",
            estimated_monthly_impact="10-30% of potential phone leads lost",
        ))

    # 7. No email capture
    if not page.has_email_capture and is_key:
        leaks.append(Leak(
            leak_type=LeakType.NO_EMAIL_CAPTURE,
            severity=Severity.MEDIUM,
            page_url=page.url,
            description="No email capture mechanism found. You're losing the ability to follow up with interested visitors.",
            recommendation="Add an email opt-in with a lead magnet (free guide, checklist, consultation offer).",
            estimated_monthly_impact="Losing 5-15% of visitors who would opt in",
        ))

    # 8. SSL issues
    if not page.has_ssl:
        leaks.append(Leak(
            leak_type=LeakType.SSL_ISSUE,
            severity=Severity.HIGH,
            page_url=page.url,
            description='Site is not using HTTPS. Browsers show "Not Secure" warning, killing trust.',
            recommendation="Install an SSL certificate. Most hosts offer free SSL via Let's Encrypt.",
            estimated_monthly_impact="Significant trust and conversion impact",
        ))
    elif page.mixed_content:
        leaks.append(Leak(
            leak_type=LeakType.SSL_ISSUE,
            severity=Severity.MEDIUM,
            page_url=page.url,
            description="HTTPS is enabled but page loads some resources over HTTP (mixed content). This can trigger browser warnings.",
            recommendation="Update all resource URLs to use HTTPS.",
            estimated_monthly_impact="Minor trust signal degradation",
        ))

    # 9. Broken links
    if page.broken_links:
        severity = Severity.HIGH if len(page.broken_links) > 3 else Severity.MEDIUM
        leaks.append(Leak(
            leak_type=LeakType.DEAD_LINK,
            severity=severity,
            page_url=page.url,
            description=f"Found {len(page.broken_links)} broken link(s) on this page. Broken links signal neglect and hurt SEO.",
            recommendation="Fix or remove these broken links: " + ", ".join(page.broken_links[:5]),
            estimated_monthly_impact="SEO ranking impact + user trust loss",
            evidence=f"Broken: {', '.join(page.broken_links[:5])}",
        ))

    # 10. No social proof
    if is_key and not page.has_social_proof:
        leaks.append(Leak(
            leak_type=LeakType.NO_SOCIAL_PROOF,
            severity=Severity.MEDIUM,
            page_url=page.url,
            description="No testimonials, reviews, client counts, or trust badges found. Social proof is the #1 conversion driver.",
            recommendation="Add 2-3 customer testimonials, review scores, or 'trusted by X companies' near your CTA.",
            estimated_monthly_impact="15-30% conversion improvement possible",
        ))

    # 11. Missing meta description
    if not page.meta_description and is_key:
        leaks.append(Leak(
            leak_type=LeakType.MISSING_META,
            severity=Severity.LOW,
            page_url=page.url,
            description="No meta description set. Google will auto-generate one, often poorly.",
            recommendation="Write a compelling meta description with your key offer and a CTA.",
            estimated_monthly_impact="Lower click-through rate from search results",
        ))

    # 12. No clear offer
    if is_key and not page.has_clear_offer:
        leaks.append(Leak(
            leak_type=LeakType.NO_CLEAR_OFFER,
            severity=Severity.MEDIUM,
            page_url=page.url,
            description="No clear pricing, packages, or offer visible. Visitors can't evaluate if this is right for them.",
            recommendation='Add pricing or a clear offer statement ("Starting at $X", "Free consultation", etc.).',
            estimated_monthly_impact="Visitors leave to check competitors with clearer pricing",
        ))

    # 13. Weak/missing H1
    if is_key and not page.h1_text:
        leaks.append(Leak(
            leak_type=LeakType.WEAK_HEADLINE,
            severity=Severity.MEDIUM,
            page_url=page.url,
            description="No H1 headline found. The headline is the first thing visitors read — it must communicate value instantly.",
            recommendation="Add a clear H1 that states who you help, what you do, and why they should care.",
            estimated_monthly_impact="Poor first impressions = higher bounce rate",
        ))

    return leaks


def score_site(pages: list[PageResult], url: str) -> SiteAudit:
    """Score an entire site and produce a SiteAudit."""
    all_leaks: list[Leak] = []

    for page in pages:
        page_leaks = score_page(page)
        all_leaks.extend(page_leaks)

    # Deduplicate: keep only the worst instance of each leak type
    # This prevents "no email capture" showing up 8 times across pages
    best_per_type: dict[str, Leak] = {}
    severity_rank = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3, Severity.INFO: 4}
    for leak in all_leaks:
        key = leak.leak_type.value
        if key not in best_per_type or severity_rank.get(leak.severity, 5) < severity_rank.get(best_per_type[key].severity, 5):
            best_per_type[key] = leak
    # Exception: broken links and dead pages can legitimately appear multiple times
    multi_types = {LeakType.DEAD_LINK.value, LeakType.SLOW_PAGE.value}
    deduped = list(best_per_type.values())
    for leak in all_leaks:
        if leak.leak_type.value in multi_types and leak != best_per_type.get(leak.leak_type.value):
            deduped.append(leak)
    all_leaks = deduped

    # Calculate overall score (100 = perfect, 0 = disaster)
    # Deduct points per leak by severity
    deductions = {
        Severity.CRITICAL: 20,
        Severity.HIGH: 12,
        Severity.MEDIUM: 6,
        Severity.LOW: 3,
        Severity.INFO: 1,
    }

    total_deduction = sum(deductions.get(leak.severity, 0) for leak in all_leaks)
    overall_score = max(0, 100 - total_deduction)

    # Estimate monthly waste
    critical_count = sum(1 for l in all_leaks if l.severity == Severity.CRITICAL)
    high_count = sum(1 for l in all_leaks if l.severity == Severity.HIGH)

    if critical_count >= 2:
        waste = "$2,000-10,000+/mo in lost revenue"
    elif critical_count >= 1 or high_count >= 3:
        waste = "$1,000-5,000/mo in lost revenue"
    elif high_count >= 1:
        waste = "$500-2,000/mo in lost revenue"
    else:
        waste = "$100-500/mo in missed opportunities"

    return SiteAudit(
        url=url,
        pages_scanned=pages,
        leaks=all_leaks,
        overall_score=overall_score,
        estimated_monthly_waste=waste,
    )
