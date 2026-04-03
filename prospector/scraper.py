"""Web scraping-based prospect discovery.

Uses DuckDuckGo HTML search (no API key needed) and business
directory scraping to find prospects automatically.
"""

from __future__ import annotations

import asyncio
import re
from urllib.parse import urljoin, urlparse, quote_plus

import httpx
from bs4 import BeautifulSoup

from models import Prospect

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Domains to skip (aggregators, not actual businesses)
_SKIP_DOMAINS = {
    # Social / aggregators
    "yelp.com", "yellowpages.com", "bbb.org", "facebook.com",
    "instagram.com", "twitter.com", "linkedin.com", "mapquest.com",
    "google.com", "angieslist.com", "homeadvisor.com", "thumbtack.com",
    "nextdoor.com", "manta.com", "superpages.com", "whitepages.com",
    "tripadvisor.com", "foursquare.com", "wikipedia.org",
    "youtube.com", "pinterest.com", "tiktok.com", "reddit.com",
    "amazon.com", "ebay.com", "craigslist.org", "apple.com",
    "microsoft.com", "bing.com", "duckduckgo.com",
    # Review / directory / listicle sites (not actual businesses)
    "healthgrades.com", "webmd.com", "opencare.com", "zocdoc.com",
    "vitals.com", "ratemds.com", "doctoralia.com",
    "bestprosintown.com", "threebestrated.com", "expertise.com",
    "plumbersup.com", "todayshomeowner.com", "angi.com",
    "bark.com", "porch.com", "houzz.com", "buildzoom.com",
    "fixr.com", "therealreview.com", "carwise.com",
    "statesman.com", "axios.com", "nytimes.com", "wsj.com",
    "forbes.com", "businessinsider.com", "medium.com",
    "quora.com", "stackexchange.com", "stackoverflow.com",
}


def _is_skip_domain(url: str) -> bool:
    domain = urlparse(url).netloc.lower().replace("www.", "")
    return any(domain == d or domain.endswith("." + d) for d in _SKIP_DOMAINS)


def _extract_contact_email(html: str) -> str:
    """Try to extract a contact email from page HTML."""
    emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", html)
    # Filter out common non-contact emails
    skip = {"example.com", "sentry.io", "google.com", "facebook.com", "email.com"}
    for email in emails:
        domain = email.split("@")[1].lower()
        if domain not in skip and not email.startswith(("noreply", "no-reply", "donotreply")):
            return email
    return ""


async def search_duckduckgo(
    query: str,
    max_results: int = 20,
) -> list[dict]:
    """Search DuckDuckGo HTML version (no API key needed).

    Returns list of dicts with 'title', 'url', 'snippet'.
    """
    results = []
    encoded_query = quote_plus(query)

    async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True) as client:
        # DuckDuckGo HTML search
        resp = await client.get(
            f"https://html.duckduckgo.com/html/?q={encoded_query}",
            timeout=15,
        )
        if resp.status_code != 200:
            return results

        soup = BeautifulSoup(resp.text, "lxml")
        links = soup.find_all("a", class_="result__a")

        for link in links[:max_results]:
            href = link.get("href", "")
            title = link.get_text(strip=True)

            # DuckDuckGo wraps URLs in a redirect — extract the actual URL
            if "uddg=" in href:
                from urllib.parse import parse_qs, urlparse as _urlparse
                parsed = _urlparse(href)
                qs = parse_qs(parsed.query)
                actual_urls = qs.get("uddg", [])
                if actual_urls:
                    href = actual_urls[0]

            if href.startswith(("http://", "https://")) and not _is_skip_domain(href):
                # Get snippet
                snippet_el = link.find_parent("div")
                snippet = ""
                if snippet_el:
                    snippet_text = snippet_el.find("a", class_="result__snippet")
                    if snippet_text:
                        snippet = snippet_text.get_text(strip=True)

                results.append({
                    "title": title,
                    "url": href,
                    "snippet": snippet,
                })

    return results


async def discover_via_search(
    niche: str,
    location: str,
    max_results: int = 20,
) -> list[Prospect]:
    """Discover business prospects using DuckDuckGo search.

    Runs multiple search queries to maximize coverage.
    """
    queries = [
        f"{niche} {location}",
        f"{niche} near {location}",
        f"best {niche} in {location}",
        f"{niche} {location} free quote",
        f"{niche} {location} reviews",
    ]

    all_results: list[dict] = []
    seen_domains: set[str] = set()

    for query in queries:
        try:
            results = await search_duckduckgo(query, max_results=10)
            for r in results:
                domain = urlparse(r["url"]).netloc.lower().replace("www.", "")
                if domain not in seen_domains:
                    seen_domains.add(domain)
                    all_results.append(r)
        except Exception:
            pass

        await asyncio.sleep(2)  # Be polite between searches

        if len(all_results) >= max_results:
            break

    prospects = []
    for r in all_results[:max_results]:
        prospects.append(Prospect(
            name=r["title"],
            url=r["url"],
            niche=niche,
            location=location,
            source="duckduckgo",
        ))

    return prospects


async def extract_business_info(url: str) -> dict:
    """Visit a business website and extract contact info.

    Returns dict with 'email', 'phone', 'address' if found.
    """
    info = {"email": "", "phone": "", "name": ""}

    async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True) as client:
        try:
            resp = await client.get(url, timeout=15)
            if resp.status_code != 200:
                return info

            html = resp.text
            text = BeautifulSoup(html, "lxml").get_text(separator=" ", strip=True)

            # Email
            info["email"] = _extract_contact_email(html)

            # Phone
            phone_match = re.search(
                r"(\+?1?\s?[-.]?\s?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})",
                text,
            )
            if phone_match:
                info["phone"] = phone_match.group(1).strip()

            # Business name from title
            soup = BeautifulSoup(html, "lxml")
            title = soup.find("title")
            if title:
                name = title.get_text(strip=True)
                # Clean up common suffixes
                for sep in [" | ", " - ", " – ", " — ", " :: "]:
                    if sep in name:
                        name = name.split(sep)[0].strip()
                info["name"] = name

        except Exception:
            pass

    return info


async def enrich_prospects(prospects: list[Prospect]) -> list[Prospect]:
    """Visit each prospect's website to extract contact info and clean up names."""
    enriched = []
    for p in prospects:
        try:
            info = await extract_business_info(p.url)
            if info["name"] and (not p.name or len(info["name"]) < len(p.name)):
                p.name = info["name"]
            enriched.append(p)
        except Exception:
            enriched.append(p)
        await asyncio.sleep(1)
    return enriched


if __name__ == "__main__":
    import sys

    niche = sys.argv[1] if len(sys.argv) > 1 else "plumber"
    location = sys.argv[2] if len(sys.argv) > 2 else "Austin TX"

    async def main():
        print(f"Searching for {niche} in {location}...")
        prospects = await discover_via_search(niche, location, max_results=10)
        print(f"Found {len(prospects)} prospects:\n")
        for p in prospects:
            print(f"  {p.name}")
            print(f"  {p.url}\n")

    asyncio.run(main())
