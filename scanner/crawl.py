"""Website crawler and page analyzer.

Crawls a target site, screenshots pages, checks forms, detects broken elements.
"""

from __future__ import annotations

import re
import time
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from models import PageResult


# Patterns that indicate a CTA
CTA_PATTERNS = [
    r"get\s+(a\s+)?quote",
    r"free\s+(consultation|estimate|trial|demo)",
    r"book\s+(now|a\s+call|appointment|online)",
    r"schedule\s+(a\s+)?(call|demo|consultation|appointment)",
    r"contact\s+us",
    r"get\s+started",
    r"sign\s+up",
    r"request\s+(a\s+)?(demo|quote|proposal|callback)",
    r"call\s+(us\s+)?(now|today)",
    r"buy\s+now",
    r"start\s+(your\s+)?(free\s+)?trial",
    r"learn\s+more",
    r"subscribe",
    r"download",
    r"claim\s+your",
    r"reserve",
    r"apply\s+now",
]

# Patterns for phone numbers
PHONE_PATTERN = re.compile(
    r"(\+?1?\s?[-.]?\s?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})"
    r"|"
    r"(tel:[\d+\-]+)"
)

# Social proof indicators
SOCIAL_PROOF_PATTERNS = [
    r"\d+\+?\s*(customers?|clients?|users?|businesses|companies)",
    r"trusted\s+by",
    r"rated\s+\d",
    r"\d+\s*star",
    r"testimonial",
    r"review",
    r"as\s+seen\s+(in|on)",
    r"featured\s+(in|on)",
    r"case\s+stud",
]


async def fetch_page(client: httpx.AsyncClient, url: str) -> tuple[str, int, float]:
    """Fetch a page and return (html, status_code, load_time_ms)."""
    start = time.monotonic()
    try:
        resp = await client.get(url, follow_redirects=True, timeout=15)
        load_time = (time.monotonic() - start) * 1000
        return resp.text, resp.status_code, load_time
    except httpx.HTTPError:
        load_time = (time.monotonic() - start) * 1000
        return "", 0, load_time


def extract_links(html: str, base_url: str) -> list[str]:
    """Extract all internal links from a page."""
    soup = BeautifulSoup(html, "lxml")
    base_domain = urlparse(base_url).netloc
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        if parsed.netloc == base_domain and parsed.scheme in ("http", "https"):
            # Strip fragment
            clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if parsed.query:
                clean += f"?{parsed.query}"
            links.add(clean)
    return list(links)


def analyze_page(html: str, url: str, status_code: int, load_time_ms: float) -> PageResult:
    """Analyze a page for revenue leak signals."""
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator=" ", strip=True).lower()

    # Title
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    # H1
    h1_tag = soup.find("h1")
    h1_text = h1_tag.get_text(strip=True) if h1_tag else ""

    # Meta description
    meta = soup.find("meta", attrs={"name": "description"})
    meta_desc = meta.get("content", "") if meta else ""

    # Forms
    forms = soup.find_all("form")
    form_count = len(forms)

    # CTA detection
    has_cta = False
    buttons = soup.find_all(["button", "a", "input"])
    for el in buttons:
        el_text = el.get_text(strip=True).lower()
        el_value = (el.get("value") or "").lower()
        combined = el_text + " " + el_value
        for pattern in CTA_PATTERNS:
            if re.search(pattern, combined):
                has_cta = True
                break
        if has_cta:
            break

    # Phone number
    has_phone = bool(PHONE_PATTERN.search(html))

    # Email capture (newsletter forms, email inputs)
    email_inputs = soup.find_all("input", attrs={"type": "email"})
    has_email_capture = len(email_inputs) > 0

    # Chat widget detection
    chat_indicators = [
        "intercom", "drift", "crisp", "tawk", "zendesk", "livechat",
        "hubspot-messages", "tidio", "olark", "freshchat", "chatwoot",
    ]
    has_chat = any(indicator in html.lower() for indicator in chat_indicators)

    # Social proof
    has_social_proof = any(
        re.search(pattern, text) for pattern in SOCIAL_PROOF_PATTERNS
    )

    # Clear offer (pricing, packages, "starting at")
    offer_patterns = [
        r"\$\d+", r"starting\s+at", r"pricing", r"packages?",
        r"per\s+month", r"/mo", r"free\s+trial",
    ]
    has_clear_offer = any(re.search(p, text) for p in offer_patterns)

    # SSL check
    has_ssl = url.startswith("https")

    # Mixed content
    mixed_content = False
    if has_ssl:
        for tag in soup.find_all(["img", "script", "link", "iframe"]):
            src = tag.get("src") or tag.get("href") or ""
            if src.startswith("http://"):
                mixed_content = True
                break

    # Broken images (images with empty or suspicious src)
    broken_images = []
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if not src or src.startswith("data:"):
            continue
        # We'll check these in the full crawl with HTTP requests

    # Word count
    word_count = len(text.split())

    # External scripts
    external_scripts = []
    for script in soup.find_all("script", src=True):
        src = script["src"]
        full = urljoin(url, src)
        if urlparse(full).netloc != urlparse(url).netloc:
            external_scripts.append(full)

    return PageResult(
        url=url,
        status_code=status_code,
        title=title,
        load_time_ms=load_time_ms,
        has_forms=form_count > 0,
        form_count=form_count,
        has_cta=has_cta,
        has_phone=has_phone,
        has_email_capture=has_email_capture,
        has_chat_widget=has_chat,
        has_social_proof=has_social_proof,
        has_clear_offer=has_clear_offer,
        has_ssl=has_ssl,
        mixed_content=mixed_content,
        broken_images=broken_images,
        meta_description=meta_desc,
        h1_text=h1_text,
        word_count=word_count,
        external_scripts=external_scripts,
    )


async def check_links(client: httpx.AsyncClient, urls: list[str]) -> list[str]:
    """Check a list of URLs and return the broken ones."""
    broken = []
    for url in urls:
        try:
            resp = await client.head(url, follow_redirects=True, timeout=10)
            if resp.status_code >= 400:
                broken.append(url)
        except httpx.HTTPError:
            broken.append(url)
    return broken


async def crawl_site(
    url: str,
    max_pages: int = 20,
    check_external_links: bool = True,
) -> list[PageResult]:
    """Crawl a website and analyze each page.

    Returns a list of PageResult objects for each page found.
    """
    # Normalize URL
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    visited: set[str] = set()
    to_visit: list[str] = [url]
    results: list[PageResult] = []

    async with httpx.AsyncClient(
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        },
    ) as client:
        while to_visit and len(visited) < max_pages:
            current_url = to_visit.pop(0)
            if current_url in visited:
                continue
            visited.add(current_url)

            html, status_code, load_time = await fetch_page(client, current_url)
            if not html:
                results.append(PageResult(url=current_url, status_code=status_code))
                continue

            page = analyze_page(html, current_url, status_code, load_time)

            # Find internal links to crawl
            links = extract_links(html, current_url)
            for link in links:
                if link not in visited:
                    to_visit.append(link)

            # Check for broken links on this page
            if check_external_links:
                all_links = []
                soup = BeautifulSoup(html, "lxml")
                for a in soup.find_all("a", href=True):
                    full = urljoin(current_url, a["href"])
                    if full.startswith(("http://", "https://")):
                        all_links.append(full)

                # Only check a sample to avoid hammering
                sample = all_links[:30]
                page.broken_links = await check_links(client, sample)

            results.append(page)

    return results


async def quick_scan(url: str) -> PageResult:
    """Quick scan of a single page — no crawling, just analyze the homepage."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    async with httpx.AsyncClient(
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        },
    ) as client:
        html, status_code, load_time = await fetch_page(client, url)
        if not html:
            return PageResult(url=url, status_code=status_code)
        return analyze_page(html, url, status_code, load_time)


if __name__ == "__main__":
    import asyncio
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    pages = asyncio.run(crawl_site(target, max_pages=10))
    for p in pages:
        print(f"\n{'='*60}")
        print(f"URL: {p.url}")
        print(f"Status: {p.status_code} | Load: {p.load_time_ms:.0f}ms")
        print(f"Title: {p.title}")
        print(f"Forms: {p.form_count} | CTA: {p.has_cta} | Phone: {p.has_phone}")
        print(f"Email capture: {p.has_email_capture} | Chat: {p.has_chat_widget}")
        print(f"Social proof: {p.has_social_proof} | Clear offer: {p.has_clear_offer}")
        print(f"SSL: {p.has_ssl} | Mixed content: {p.mixed_content}")
        print(f"Broken links: {len(p.broken_links)}")
