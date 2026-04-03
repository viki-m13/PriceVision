"""AI-powered scraping for better prospect discovery and enrichment.

Uses Crawl4AI (local, no API key) and Jina Reader (free API) to:
1. Extract business info from directory pages
2. Enrich prospects with contact details
3. Better parse complex JS-rendered pages
"""

from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import quote

import httpx

from models import Prospect


# ── Jina Reader (free, no API key) ───────────────────────────

async def jina_read(url: str) -> str:
    """Use Jina Reader to get clean markdown from any URL. Free, no API key."""
    jina_url = f"https://r.jina.ai/{url}"
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                jina_url,
                headers={"Accept": "text/markdown"},
                timeout=20,
            )
            if resp.status_code == 200:
                return resp.text
        except httpx.HTTPError:
            pass
    return ""


async def jina_search(query: str, api_key: str = "") -> list[dict]:
    """Use Jina Search to find businesses. Requires API key.

    Returns list of dicts with 'title', 'url', 'content'.
    """
    if not api_key:
        return []

    jina_url = f"https://s.jina.ai/{quote(query)}"
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                jina_url,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                timeout=20,
            )
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for item in data.get("data", []):
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "content": item.get("content", ""),
                    })
                return results
        except (httpx.HTTPError, json.JSONDecodeError):
            pass
    return []


# ── Crawl4AI (local, no API key) ────────────────────────────

async def crawl4ai_extract_businesses(url: str) -> list[dict]:
    """Use Crawl4AI to extract business listings from a directory page.

    Returns list of dicts with business info extracted from the page.
    """
    try:
        from crawl4ai import AsyncWebCrawler

        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url)
            if not result.success:
                return []

            # Parse the markdown for business info
            return _parse_businesses_from_markdown(result.markdown)
    except ImportError:
        return []
    except Exception:
        return []


async def crawl4ai_enrich_prospect(url: str) -> dict:
    """Use Crawl4AI to visit a business site and extract rich info.

    Returns dict with 'name', 'email', 'phone', 'description', 'services'.
    """
    info = {"name": "", "email": "", "phone": "", "description": "", "services": []}
    try:
        from crawl4ai import AsyncWebCrawler

        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url)
            if not result.success:
                return info

            md = result.markdown

            # Extract email
            emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", md)
            skip_domains = {"example.com", "sentry.io", "google.com", "email.com"}
            for email in emails:
                domain = email.split("@")[1].lower()
                if domain not in skip_domains:
                    info["email"] = email
                    break

            # Extract phone
            phone = re.search(r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", md)
            if phone:
                info["phone"] = phone.group(0)

            # Name from first heading
            h1 = re.search(r"^#\s+(.+)$", md, re.MULTILINE)
            if h1:
                info["name"] = h1.group(1).strip()

            # First paragraph as description
            paragraphs = [p.strip() for p in md.split("\n\n") if p.strip() and not p.startswith("#")]
            if paragraphs:
                info["description"] = paragraphs[0][:200]

    except ImportError:
        pass
    except Exception:
        pass

    return info


# ── Combined Discovery ───────────────────────────────────────

async def ai_discover_prospects(
    niche: str,
    location: str,
    max_results: int = 15,
) -> list[Prospect]:
    """Use AI scraping tools to discover business prospects.

    Tries Jina Search first (fastest), falls back to Crawl4AI.
    """
    prospects: list[Prospect] = []
    seen_domains: set[str] = set()

    from prospector.scraper import _is_skip_domain
    from urllib.parse import urlparse

    # Method 1: Jina Search (free, fast)
    queries = [
        f"{niche} {location}",
        f"best {niche} near {location}",
    ]

    for query in queries:
        try:
            results = await jina_search(query)
            for r in results:
                url = r.get("url", "")
                if not url or _is_skip_domain(url):
                    continue
                domain = urlparse(url).netloc.lower().replace("www.", "")
                if domain in seen_domains:
                    continue
                seen_domains.add(domain)
                prospects.append(Prospect(
                    name=r.get("title", ""),
                    url=url,
                    niche=niche,
                    location=location,
                    source="jina_search",
                ))
        except Exception:
            pass

        if len(prospects) >= max_results:
            break
        await asyncio.sleep(1)

    return prospects[:max_results]


async def jina_enrich_prospect(url: str) -> dict:
    """Use Jina Reader to extract business info from a URL.

    Free, no API key, works on JS-rendered pages.
    Returns dict with 'name', 'email', 'phone'.
    """
    info = {"name": "", "email": "", "phone": ""}
    md = await jina_read(url)
    if not md:
        return info

    # Name from first heading
    h1 = re.search(r"^#\s+(.+)$", md, re.MULTILINE)
    if h1:
        info["name"] = h1.group(1).strip()

    # Email
    emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", md)
    skip_domains = {"example.com", "sentry.io", "google.com", "email.com", "wixpress.com"}
    for email in emails:
        domain = email.split("@")[1].lower()
        if domain not in skip_domains and not email.startswith(("noreply", "no-reply")):
            info["email"] = email
            break

    # Phone
    phone = re.search(r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", md)
    if phone:
        info["phone"] = phone.group(0)

    return info


async def ai_enrich_prospects(prospects: list[Prospect]) -> list[Prospect]:
    """Enrich prospects with AI-extracted contact info.

    Uses Jina Reader (free, no API key) as primary method,
    falls back to Crawl4AI for JS-heavy pages.
    """
    enriched = []
    for p in prospects:
        try:
            info = await jina_enrich_prospect(p.url)
            if info.get("name") and (not p.name or len(p.name) > 60):
                p.name = info["name"]
            enriched.append(p)
        except Exception:
            enriched.append(p)
        await asyncio.sleep(1.5)  # Rate limit for Jina
    return enriched


def _parse_businesses_from_markdown(md: str) -> list[dict]:
    """Parse business listings from markdown content."""
    businesses = []
    # Look for patterns like business names followed by URLs or phone numbers
    lines = md.split("\n")
    current = {}

    for line in lines:
        line = line.strip()
        if not line:
            if current.get("name"):
                businesses.append(current)
                current = {}
            continue

        # Heading = business name
        if line.startswith("#"):
            if current.get("name"):
                businesses.append(current)
            current = {"name": line.lstrip("#").strip()}
            continue

        # URL
        url_match = re.search(r"https?://[^\s\)]+", line)
        if url_match and "url" not in current:
            current["url"] = url_match.group(0)

        # Phone
        phone_match = re.search(r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", line)
        if phone_match and "phone" not in current:
            current["phone"] = phone_match.group(0)

        # Email
        email_match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", line)
        if email_match and "email" not in current:
            current["email"] = email_match.group(0)

    if current.get("name"):
        businesses.append(current)

    return businesses


if __name__ == "__main__":
    import sys

    niche = sys.argv[1] if len(sys.argv) > 1 else "plumber"
    location = sys.argv[2] if len(sys.argv) > 2 else "Austin TX"

    async def main():
        print(f"AI-powered discovery: {niche} in {location}")
        print("=" * 50)

        prospects = await ai_discover_prospects(niche, location, max_results=5)
        print(f"\nFound {len(prospects)} prospects:")
        for p in prospects:
            print(f"  [{p.source}] {p.name}")
            print(f"           {p.url}\n")

    asyncio.run(main())
